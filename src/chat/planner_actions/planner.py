import json
import time
import traceback
from typing import Dict, Any, Optional
from rich.traceback import install
from datetime import datetime
from json_repair import repair_json

from src.llm_models.utils_model import LLMRequest
from src.config.config import global_config
from src.common.logger import get_logger
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.chat.utils.chat_message_builder import build_readable_messages, get_raw_msg_before_timestamp_with_chat
from src.chat.utils.utils import get_chat_type_and_target_info
from src.chat.planner_actions.action_manager import ActionManager
from src.chat.message_receive.chat_stream import get_chat_manager
from src.plugin_system.base.component_types import ChatMode


logger = get_logger("planner")

install(extra_lines=3)


def init_prompt():
    Prompt(
        """
{time_block}
{indentify_block}
你现在需要根据聊天内容，选择的合适的action来参与聊天。
{chat_context_description}，以下是具体的聊天内容：
{chat_content_block}
{moderation_prompt}

现在请你根据{by_what}选择合适的action:
{no_action_block}
{action_options_text}

你必须从上面列出的可用action中选择一个，并说明原因。

请根据动作示例，以严格的 JSON 格式输出，且仅包含 JSON 内容：
""",
        "planner_prompt",
    )

    Prompt(
        """
动作：{action_name}
动作描述：{action_description}
{action_require}
{{
    "action": "{action_name}",{action_parameters}
}}
""",
        "action_prompt",
    )


class ActionPlanner:
    def __init__(self, chat_id: str, action_manager: ActionManager, mode: ChatMode = ChatMode.FOCUS):
        self.chat_id = chat_id
        self.log_prefix = f"[{get_chat_manager().get_stream_name(chat_id) or chat_id}]"
        self.mode = mode
        self.action_manager = action_manager
        # LLM规划器配置
        self.planner_llm = LLMRequest(
            model=global_config.model.planner,
            request_type=f"{self.mode.value}.planner",  # 用于动作规划
        )

        self.last_obs_time_mark = 0.0

    async def plan(self) -> Dict[str, Any]:
        """
        规划器 (Planner): 使用LLM根据上下文决定做出什么动作。
        """

        action = "no_reply"  # 默认动作
        reasoning = "规划器初始化默认"
        action_data = {}

        try:
            is_group_chat = True

            is_group_chat, chat_target_info = get_chat_type_and_target_info(self.chat_id)
            logger.debug(f"{self.log_prefix}获取到聊天信息 - 群聊: {is_group_chat}, 目标信息: {chat_target_info}")

            current_available_actions_dict = self.action_manager.get_using_actions_for_mode(self.mode)

            # 获取完整的动作信息
            all_registered_actions = self.action_manager.get_registered_actions()
            current_available_actions = {}
            for action_name in current_available_actions_dict.keys():
                if action_name in all_registered_actions:
                    current_available_actions[action_name] = all_registered_actions[action_name]
                else:
                    logger.warning(f"{self.log_prefix}使用中的动作 {action_name} 未在已注册动作中找到")

            # 如果没有可用动作或只有no_reply动作，直接返回no_reply
            if not current_available_actions or (
                len(current_available_actions) == 1 and "no_reply" in current_available_actions
            ):
                action = "no_reply"
                reasoning = "没有可用的动作" if not current_available_actions else "只有no_reply动作可用，跳过规划"
                logger.info(f"{self.log_prefix}{reasoning}")
                logger.debug(
                    f"{self.log_prefix}[focus]沉默后恢复到默认动作集, 当前可用: {list(self.action_manager.get_using_actions().keys())}"
                )
                return {
                    "action_result": {"action_type": action, "action_data": action_data, "reasoning": reasoning},
                }

            # --- 构建提示词 (调用修改后的 PromptBuilder 方法) ---
            prompt = await self.build_planner_prompt(
                is_group_chat=is_group_chat,  # <-- Pass HFC state
                chat_target_info=chat_target_info,  # <-- 传递获取到的聊天目标信息
                current_available_actions=current_available_actions,  # <-- Pass determined actions
            )

            # --- 调用 LLM (普通文本生成) ---
            llm_content = None
            try:
                llm_content, (reasoning_content, _) = await self.planner_llm.generate_response_async(prompt=prompt)

                if global_config.debug.show_prompt:
                    logger.info(f"{self.log_prefix}规划器原始提示词: {prompt}")
                    logger.info(f"{self.log_prefix}规划器原始响应: {llm_content}")
                    if reasoning_content:
                        logger.info(f"{self.log_prefix}规划器推理: {reasoning_content}")
                else:
                    logger.debug(f"{self.log_prefix}规划器原始提示词: {prompt}")
                    logger.debug(f"{self.log_prefix}规划器原始响应: {llm_content}")
                    if reasoning_content:
                        logger.debug(f"{self.log_prefix}规划器推理: {reasoning_content}")

            except Exception as req_e:
                logger.error(f"{self.log_prefix}LLM 请求执行失败: {req_e}")
                reasoning = f"LLM 请求失败，你的模型出现问题: {req_e}"
                action = "no_reply"

            if llm_content:
                try:
                    parsed_json = json.loads(repair_json(llm_content))

                    if isinstance(parsed_json, list):
                        if parsed_json:
                            parsed_json = parsed_json[-1]
                            logger.warning(f"{self.log_prefix}LLM返回了多个JSON对象，使用最后一个: {parsed_json}")
                        else:
                            parsed_json = {}

                    if not isinstance(parsed_json, dict):
                        logger.error(f"{self.log_prefix}解析后的JSON不是字典类型: {type(parsed_json)}")
                        parsed_json = {}

                    action = parsed_json.get("action", "no_reply")
                    reasoning = parsed_json.get("reasoning", "未提供原因")

                    # 将所有其他属性添加到action_data
                    action_data = {}
                    for key, value in parsed_json.items():
                        if key not in ["action", "reasoning"]:
                            action_data[key] = value

                    if action == "no_action":
                        reasoning = "normal决定不使用额外动作"
                    elif action not in current_available_actions:
                        logger.warning(
                            f"{self.log_prefix}LLM 返回了当前不可用或无效的动作: '{action}' (可用: {list(current_available_actions.keys())})，将强制使用 'no_reply'"
                        )
                        action = "no_reply"
                        reasoning = f"LLM 返回了当前不可用的动作 '{action}' (可用: {list(current_available_actions.keys())})。原始理由: {reasoning}"

                except Exception as json_e:
                    logger.warning(f"{self.log_prefix}解析LLM响应JSON失败 {json_e}. LLM原始输出: '{llm_content}'")
                    traceback.print_exc()
                    reasoning = f"解析LLM响应JSON失败: {json_e}. 将使用默认动作 'no_reply'."
                    action = "no_reply"

        except Exception as outer_e:
            logger.error(f"{self.log_prefix}Planner 处理过程中发生意外错误，规划失败，将执行 no_reply: {outer_e}")
            traceback.print_exc()
            action = "no_reply"
            reasoning = f"Planner 内部处理错误: {outer_e}"

        is_parallel = False
        if action in current_available_actions:
            action_info = current_available_actions[action]
            is_parallel = action_info.get("parallel_action", False)

        action_result = {
            "action_type": action,
            "action_data": action_data,
            "reasoning": reasoning,
            "timestamp": time.time(),
            "is_parallel": is_parallel,
        }

        plan_result = {
            "action_result": action_result,
            "action_prompt": prompt,
        }

        return plan_result

    async def build_planner_prompt(
        self,
        is_group_chat: bool,  # Now passed as argument
        chat_target_info: Optional[dict],  # Now passed as argument
        current_available_actions,
    ) -> str:
        """构建 Planner LLM 的提示词 (获取模板并填充数据)"""
        try:
            message_list_before_now = get_raw_msg_before_timestamp_with_chat(
                chat_id=self.chat_id,
                timestamp=time.time(),
                limit=global_config.chat.max_context_size,
            )

            chat_content_block = build_readable_messages(
                messages=message_list_before_now,
                timestamp_mode="normal_no_YMD",
                read_mark=self.last_obs_time_mark,
                truncate=True,
                show_actions=True,
            )

            self.last_obs_time_mark = time.time()

            if self.mode == ChatMode.FOCUS:
                by_what = "聊天内容"
                no_action_block = ""
            else:
                by_what = "聊天内容和用户的最新消息"
                no_action_block = """重要说明：
- 'no_action' 表示只进行普通聊天回复，不执行任何额外动作
- 其他action表示在普通回复的基础上，执行相应的额外动作"""

            chat_context_description = "你现在正在一个群聊中"
            chat_target_name = None  # Only relevant for private
            if not is_group_chat and chat_target_info:
                chat_target_name = (
                    chat_target_info.get("person_name") or chat_target_info.get("user_nickname") or "对方"
                )
                chat_context_description = f"你正在和 {chat_target_name} 私聊"

            action_options_block = ""

            for using_actions_name, using_actions_info in current_available_actions.items():
                if using_actions_info["parameters"]:
                    param_text = "\n"
                    for param_name, param_description in using_actions_info["parameters"].items():
                        param_text += f'    "{param_name}":"{param_description}"\n'
                    param_text = param_text.rstrip("\n")
                else:
                    param_text = ""

                require_text = ""
                for require_item in using_actions_info["require"]:
                    require_text += f"- {require_item}\n"
                require_text = require_text.rstrip("\n")

                using_action_prompt = await global_prompt_manager.get_prompt_async("action_prompt")
                using_action_prompt = using_action_prompt.format(
                    action_name=using_actions_name,
                    action_description=using_actions_info["description"],
                    action_parameters=param_text,
                    action_require=require_text,
                )

                action_options_block += using_action_prompt

            moderation_prompt_block = "请不要输出违法违规内容，不要输出色情，暴力，政治相关内容，如有敏感内容，请规避。"

            time_block = f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            bot_name = global_config.bot.nickname
            if global_config.bot.alias_names:
                bot_nickname = f",也有人叫你{','.join(global_config.bot.alias_names)}"
            else:
                bot_nickname = ""
            bot_core_personality = global_config.personality.personality_core
            indentify_block = f"你的名字是{bot_name}{bot_nickname}，你{bot_core_personality}："

            planner_prompt_template = await global_prompt_manager.get_prompt_async("planner_prompt")
            prompt = planner_prompt_template.format(
                time_block=time_block,
                by_what=by_what,
                chat_context_description=chat_context_description,
                chat_content_block=chat_content_block,
                no_action_block=no_action_block,
                action_options_text=action_options_block,
                moderation_prompt=moderation_prompt_block,
                indentify_block=indentify_block,
            )
            return prompt

        except Exception as e:
            logger.error(f"构建 Planner 提示词时出错: {e}")
            logger.error(traceback.format_exc())
            return "构建 Planner Prompt 时出错"


init_prompt()
