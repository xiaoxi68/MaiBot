import json  # <--- 确保导入 json
import traceback
from typing import List, Dict, Any
from rich.traceback import install
from src.chat.models.utils_model import LLMRequest
from src.config.config import global_config
from src.chat.focus_chat.heartflow_prompt_builder import prompt_builder
from src.chat.focus_chat.info.info_base import InfoBase
from src.chat.focus_chat.info.obs_info import ObsInfo
from src.chat.focus_chat.info.cycle_info import CycleInfo
from src.chat.focus_chat.info.mind_info import MindInfo
from src.chat.focus_chat.info.structured_info import StructuredInfo
from src.chat.focus_chat.planners.action_factory import ActionFactory
from src.common.logger_manager import get_logger

logger = get_logger("planner")

install(extra_lines=3)


class ActionPlanner:
    def __init__(self, log_prefix: str):
        self.log_prefix = log_prefix
        # LLM规划器配置
        self.planner_llm = LLMRequest(
            model=global_config.llm_plan,
            max_tokens=1000,
            request_type="action_planning",  # 用于动作规划
        )

    async def plan(self, all_plan_info: List[InfoBase], cycle_timers: dict) -> Dict[str, Any]:
        """
        规划器 (Planner): 使用LLM根据上下文决定做出什么动作。

        参数:
            all_plan_info: 所有计划信息
            cycle_timers: 计时器字典
        """

        action = "no_reply"  # 默认动作
        reasoning = "规划器初始化默认"

        try:
            # 获取观察信息
            for info in all_plan_info:
                if isinstance(info, ObsInfo):
                    logger.debug(f"{self.log_prefix} 观察信息: {info}")
                    observed_messages = info.get_talking_message()
                    observed_messages_str = info.get_talking_message_str_truncate()
                    chat_type = info.get_chat_type()
                    if chat_type == "group":
                        is_group_chat = True
                    else:
                        is_group_chat = False
                elif isinstance(info, MindInfo):
                    logger.debug(f"{self.log_prefix} 思维信息: {info}")
                    current_mind = info.get_current_mind()
                elif isinstance(info, CycleInfo):
                    logger.debug(f"{self.log_prefix} 循环信息: {info}")
                    cycle_info = info.get_observe_info()
                elif isinstance(info, StructuredInfo):
                    logger.debug(f"{self.log_prefix} 结构化信息: {info}")
                    structured_info = info.get_data()

            # 获取我们将传递给 prompt 构建器和用于验证的当前可用动作
            current_available_actions = ActionFactory.get_available_actions()

            # --- 构建提示词 (调用修改后的 PromptBuilder 方法) ---
            prompt = await prompt_builder.build_planner_prompt(
                is_group_chat=is_group_chat,  # <-- Pass HFC state
                chat_target_info=None,
                observed_messages_str=observed_messages_str,  # <-- Pass local variable
                current_mind=current_mind,  # <-- Pass argument
                structured_info=structured_info,  # <-- Pass SubMind info
                current_available_actions=current_available_actions,  # <-- Pass determined actions
                cycle_info=cycle_info,  # <-- Pass cycle info
            )

            # --- 调用 LLM (普通文本生成) ---
            llm_content = None
            try:
                llm_content, _, _ = await self.planner_llm.generate_response(prompt=prompt)
                logger.debug(f"{self.log_prefix}[Planner] LLM 原始 JSON 响应 (预期): {llm_content}")
            except Exception as req_e:
                logger.error(f"{self.log_prefix}[Planner] LLM 请求执行失败: {req_e}")
                reasoning = f"LLM 请求失败，你的模型出现问题: {req_e}"
                action = "no_reply"

            if llm_content:
                try:
                    # 尝试去除可能的 markdown 代码块标记
                    cleaned_content = (
                        llm_content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                    )
                    if not cleaned_content:
                        raise json.JSONDecodeError("Cleaned content is empty", cleaned_content, 0)
                    parsed_json = json.loads(cleaned_content)

                    # 提取决策，提供默认值
                    extracted_action = parsed_json.get("action", "no_reply")
                    extracted_reasoning = parsed_json.get("reasoning", "LLM未提供理由")

                    # 新的reply格式
                    if extracted_action == "reply":
                        action_data = {
                            "text": parsed_json.get("text", []),
                            "emojis": parsed_json.get("emojis", []),
                            "target": parsed_json.get("target", ""),
                        }
                    else:
                        action_data = {}  # 其他动作可能不需要额外数据

                    if extracted_action not in current_available_actions:
                        logger.warning(
                            f"{self.log_prefix}LLM 返回了当前不可用或无效的动作: '{extracted_action}' (可用: {list(current_available_actions.keys())})，将强制使用 'no_reply'"
                        )
                        action = "no_reply"
                        reasoning = f"LLM 返回了当前不可用的动作 '{extracted_action}' (可用: {list(current_available_actions.keys())})。原始理由: {extracted_reasoning}"
                    else:
                        # 动作有效且可用
                        action = extracted_action
                        reasoning = extracted_reasoning

                except Exception as json_e:
                    logger.warning(
                        f"{self.log_prefix}解析LLM响应JSON失败，模型返回不标准: {json_e}. LLM原始输出: '{llm_content}'"
                    )
                    reasoning = f"解析LLM响应JSON失败: {json_e}. 将使用默认动作 'no_reply'."
                    action = "no_reply"

        except Exception as outer_e:
            logger.error(f"{self.log_prefix}Planner 处理过程中发生意外错误，规划失败，将执行 no_reply: {outer_e}")
            traceback.print_exc()
            action = "no_reply"  # 发生未知错误，标记为 error 动作
            reasoning = f"Planner 内部处理错误: {outer_e}"

        logger.debug(
            f"{self.log_prefix}规划器Prompt:\n{prompt}\n\n决策动作:{action},\n动作信息: '{action_data}'\n理由: {reasoning}"
        )

        # 恢复原始动作集
        ActionFactory.restore_actions()
        logger.debug(
            f"{self.log_prefix}恢复了原始动作集, 当前可用: {list(ActionFactory.get_available_actions().keys())}"
        )

        action_result = {"action_type": action, "action_data": action_data, "reasoning": reasoning}

        plan_result = {
            "action_result": action_result,
            "current_mind": current_mind,
            "observed_messages": observed_messages,
        }

        # 返回结果字典
        return plan_result
