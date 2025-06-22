"""
核心动作插件

将系统核心动作（reply、no_reply、emoji）转换为新插件系统格式
这是系统的内置插件，提供基础的聊天交互功能
"""

import time
from typing import List, Tuple, Type

# 导入新插件系统
from src.plugin_system import BasePlugin, register_plugin, BaseAction, ComponentInfo, ActionActivationType, ChatMode
from src.plugin_system.base.config_types import ConfigField

# 导入依赖的系统组件
from src.common.logger import get_logger

# 导入API模块 - 标准Python包方式
from src.plugin_system.apis import emoji_api, generator_api, message_api, llm_api
from src.config.config import global_config
from datetime import datetime

logger = get_logger("core_actions")

# 常量定义
WAITING_TIME_THRESHOLD = 1200  # 等待新消息时间阈值，单位秒


class ReplyAction(BaseAction):
    """回复动作 - 参与聊天回复"""

    # 激活设置
    focus_activation_type = ActionActivationType.ALWAYS
    normal_activation_type = ActionActivationType.NEVER
    mode_enable = ChatMode.FOCUS
    parallel_action = False

    # 动作基本信息
    action_name = "reply"
    action_description = "参与聊天回复，发送文本进行表达"

    # 动作参数定义
    action_parameters = {
        "reply_to": "你要回复的对方的发言内容，格式：（用户名:发言内容），可以为none",
        "reason": "回复的原因",
    }

    # 动作使用场景
    action_require = ["你想要闲聊或者随便附和", "有人提到你", "如果你刚刚进行了回复，不要对同一个话题重复回应"]

    # 关联类型
    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        """执行回复动作"""
        logger.info(f"{self.log_prefix} 决定回复: {self.reasoning}")

        start_time = self.action_data.get("loop_start_time", time.time())
        


        try:
            success, reply_set = await generator_api.generate_reply(
                chat_stream=self.chat_stream,
                action_data=self.action_data,
                platform=self.platform,
                chat_id=self.chat_id,
                is_group=self.is_group,
            )


            # 检查从start_time以来的新消息数量
            # 获取动作触发时间或使用默认值
            current_time = time.time()
            new_message_count = message_api.count_new_messages(
                chat_id=self.chat_id, start_time=start_time, end_time=current_time
            )

            # 根据新消息数量决定是否使用reply_to
            need_reply = new_message_count >= 4
            logger.info(
                f"{self.log_prefix} 从{start_time}到{current_time}共有{new_message_count}条新消息，{'使用' if need_reply else '不使用'}reply_to"
            )

            # 构建回复文本
            reply_text = ""
            first_replyed = False
            for reply_seg in reply_set:
                data = reply_seg[1]
                if not first_replyed:
                    if need_reply:
                        await self.send_text(content=data, reply_to=self.action_data.get("reply_to", ""),typing=False)
                        first_replyed = True
                    else:
                        await self.send_text(content=data,typing=False)
                        first_replyed = True
                else:
                    await self.send_text(content=data,typing=True)
                reply_text += data
                

            # 存储动作记录
            await self.store_action_info(
                action_build_into_prompt=False,
                action_prompt_display=reply_text,
                action_done=True,
            )

            # 重置NoReplyAction的连续计数器
            NoReplyAction.reset_consecutive_count()

            return success, reply_text

        except Exception as e:
            logger.error(f"{self.log_prefix} 回复动作执行失败: {e}")
            return False, f"回复失败: {str(e)}"


class NoReplyAction(BaseAction):
    """不回复动作，使用智能判断机制决定何时结束等待
    
    新的等待逻辑：
    - 每0.2秒检查是否有新消息（提高响应性）
    - 如果累计消息数量达到阈值（默认20条），直接结束等待
    - 有新消息时进行LLM判断，但最快1秒一次（防止过于频繁）
    - 如果判断需要回复，则结束等待；否则继续等待
    - 达到最大超时时间后强制结束
    """

    focus_activation_type = ActionActivationType.ALWAYS
    # focus_activation_type = ActionActivationType.RANDOM
    normal_activation_type = ActionActivationType.NEVER
    mode_enable = ChatMode.FOCUS
    parallel_action = False

    # 动作基本信息
    action_name = "no_reply"
    action_description = "暂时不回复消息"

    # 连续no_reply计数器
    _consecutive_count = 0
    
    # LLM判断的最小间隔时间
    _min_judge_interval = 1.0  # 最快1秒一次LLM判断
    
    # 自动结束的消息数量阈值
    _auto_exit_message_count = 20  # 累计20条消息自动结束
    
    # 最大等待超时时间
    _max_timeout = 1200  # 1200秒

    # 动作参数定义
    action_parameters = {"reason": "不回复的原因"}

    # 动作使用场景
    action_require = ["你发送了消息，目前无人回复"]

    # 关联类型
    associated_types = []

    async def execute(self) -> Tuple[bool, str]:
        """执行不回复动作，有新消息时进行判断，但最快1秒一次"""
        import asyncio
        
        try:
            # 增加连续计数
            NoReplyAction._consecutive_count += 1
            count = NoReplyAction._consecutive_count

            reason = self.action_data.get("reason", "")
            start_time = time.time()
            last_judge_time = 0  # 上次进行LLM判断的时间
            min_judge_interval = self._min_judge_interval  # 最小判断间隔，从配置获取
            check_interval = 0.2  # 检查新消息的间隔，设为0.2秒提高响应性
            
            # 获取no_reply开始时的上下文消息（5条），用于后续记录
            context_messages = message_api.get_messages_by_time_in_chat(
                chat_id=self.chat_id,
                start_time=start_time - 300,  # 获取开始前5分钟内的消息
                end_time=start_time,
                limit=5,
                limit_mode="latest"
            )
            
            # 构建上下文字符串
            context_str = ""
            if context_messages:
                context_str = message_api.build_readable_messages(
                    messages=context_messages,
                    timestamp_mode="normal_no_YMD",
                    truncate=False,
                    show_actions=False
                )
                context_str = f"当时选择no_reply前的聊天上下文：\n{context_str}\n"
            
            logger.info(f"{self.log_prefix} 选择不回复(第{count}次)，开始智能等待，原因: {reason}")

            while True:
                current_time = time.time()
                elapsed_time = current_time - start_time
                
                # 检查是否超时
                if elapsed_time >= self._max_timeout:
                    logger.info(f"{self.log_prefix} 达到最大等待时间{self._max_timeout}秒，结束等待")
                    exit_reason = f"达到最大等待时间{self._max_timeout}秒，超时结束"
                    full_prompt = f"{context_str}{exit_reason}，你思考是否要进行回复"
                    await self.store_action_info(
                        action_build_into_prompt=True,
                        action_prompt_display=full_prompt,
                        action_done=True,
                    )
                    return True, exit_reason
                
                # 检查是否有新消息
                new_message_count = message_api.count_new_messages(
                    chat_id=self.chat_id, start_time=start_time, end_time=current_time
                )
                
                # 如果累计消息数量达到阈值，直接结束等待
                if new_message_count >= self._auto_exit_message_count:
                    logger.info(f"{self.log_prefix} 累计消息数量达到{new_message_count}条，直接结束等待")
                    exit_reason = f"累计消息数量达到{new_message_count}条，自动结束不回复状态"
                    full_prompt = f"{context_str}{exit_reason}，你思考是否要进行回复"
                    await self.store_action_info(
                        action_build_into_prompt=True,
                        action_prompt_display=full_prompt,
                        action_done=True,
                    )
                    return True, f"累计消息数量达到{new_message_count}条，直接结束等待 (等待时间: {elapsed_time:.1f}秒)"
                
                # 如果有新消息且距离上次判断>=1秒，进行LLM判断
                if new_message_count > 0 and (current_time - last_judge_time) >= min_judge_interval:
                    logger.info(f"{self.log_prefix} 检测到{new_message_count}条新消息，进行智能判断...")
                    
                    # 获取最近的消息内容用于判断
                    recent_messages = message_api.get_messages_by_time_in_chat(
                        chat_id=self.chat_id, 
                        start_time=start_time,
                        end_time=current_time,
                    )
                    
                    if recent_messages:
                        # 使用message_api构建可读的消息字符串
                        messages_text = message_api.build_readable_messages(
                            messages=recent_messages,
                            timestamp_mode="normal_no_YMD",
                            truncate=False,
                            show_actions=False
                        )
                        
                        # 参考simple_planner构建更完整的判断信息
                        # 获取时间信息
                        time_block = f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        
                        # 获取身份信息
                        bot_name = global_config.bot.nickname
                        bot_nickname = ""
                        if global_config.bot.alias_names:
                            bot_nickname = f",也有人叫你{','.join(global_config.bot.alias_names)}"
                        bot_core_personality = global_config.personality.personality_core
                        identity_block = f"你的名字是{bot_name}{bot_nickname}，你{bot_core_personality}"
                        
                        # 构建判断上下文
                        judge_prompt = f"""
{time_block}
{identity_block}

{context_str}
在以上的聊天中，你选择了暂时不回复，现在，你看到了新的聊天消息如下：
{messages_text}

请你判断，是否要结束不回复的状态，重新加入聊天讨论。

判断标准：
1. 如果有人直接@你、提到你的名字或明确向你询问，应该回复
2. 如果话题发生重要变化，需要你参与讨论，应该回复
3. 如果出现了紧急或重要的情况，应该回复
4. 如果只是普通闲聊、重复内容或与你无关的讨论，不需要回复
5. 如果消息内容过于简单（如单纯的表情、"哈哈"等），不需要回复

请按以下格式输出你的判断：
判断：需要回复/不需要回复
理由：[说明你的判断理由]
"""
                        
                        try:
                            # 获取可用的模型配置
                            available_models = llm_api.get_available_models()
                            
                            # 使用 utils_small 模型
                            small_model = getattr(available_models, 'utils_small', None)
                            
                            if small_model:
                                # 使用小模型进行判断
                                success, response, reasoning, model_name = await llm_api.generate_with_model(
                                    prompt=judge_prompt,
                                    model_config=small_model,
                                    request_type="plugin.no_reply_judge",
                                    temperature=0.7  # 降低温度，提高判断的一致性
                                )
                                
                                # 更新上次判断时间
                                last_judge_time = time.time()
                                
                                if success and response:
                                    response = response.strip()
                                    logger.info(f"{self.log_prefix} 模型({model_name})原始判断结果: {response}")
                                    
                                    # 解析LLM响应，提取判断结果和理由
                                    judge_result, reason = self._parse_llm_judge_response(response)
                                    
                                    logger.info(f"{self.log_prefix} 解析结果 - 判断: {judge_result}, 理由: {reason}")
                                    
                                    if judge_result == "需要回复":
                                        logger.info(f"{self.log_prefix} 模型判断需要回复，结束等待")
                                        full_prompt = f"你的想法是：{reason}，你思考是否要进行回复"
                                        await self.store_action_info(
                                            action_build_into_prompt=True,
                                            action_prompt_display=full_prompt,
                                            action_done=True,
                                        )
                                        return True, f"检测到需要回复的消息，结束等待 (等待时间: {elapsed_time:.1f}秒)"
                                    else:
                                        logger.info(f"{self.log_prefix} 模型判断不需要回复，理由: {reason}，继续等待")
                                        # 更新开始时间，避免重复判断同样的消息
                                        start_time = current_time
                                else:
                                    logger.warning(f"{self.log_prefix} 模型判断失败，继续等待")
                            else:
                                logger.warning(f"{self.log_prefix} 未找到可用的模型配置，继续等待")
                                last_judge_time = time.time()  # 即使失败也更新时间，避免频繁重试
                                
                        except Exception as e:
                            logger.error(f"{self.log_prefix} 模型判断异常: {e}，继续等待")
                            last_judge_time = time.time()  # 异常时也更新时间，避免频繁重试
                
                # 每10秒输出一次等待状态
                if int(elapsed_time) % 10 == 0 and int(elapsed_time) > 0:
                    logger.info(f"{self.log_prefix} 已等待{elapsed_time:.0f}秒，继续监听...")
                
                # 短暂等待后继续检查
                await asyncio.sleep(check_interval)

        except Exception as e:
            logger.error(f"{self.log_prefix} 不回复动作执行失败: {e}")
            # 即使执行失败也要记录
            exit_reason = f"执行异常: {str(e)}"
            full_prompt = f"{context_str}{exit_reason}，你思考是否要进行回复"
            await self.store_action_info(
                action_build_into_prompt=True,
                action_prompt_display=full_prompt,
                action_done=True,
            )
            return False, f"不回复动作执行失败: {e}"

        # 如果到达这里说明超时了（正常情况不会到这里，因为while True循环）
        logger.info(f"{self.log_prefix} 达到最大等待时间，结束等待")
        exit_reason = f"达到最大等待时间{self._max_timeout}秒，超时结束"
        full_prompt = f"{context_str}{exit_reason}，你思考是否要进行回复"
        await self.store_action_info(
            action_build_into_prompt=True,
            action_prompt_display=full_prompt,
            action_done=True,
        )
        return True, exit_reason

    def _parse_llm_judge_response(self, response: str) -> tuple[str, str]:
        """解析LLM判断响应，提取判断结果和理由
        
        Args:
            response: LLM的原始响应
            
        Returns:
            tuple: (判断结果, 理由)
        """
        try:
            lines = response.strip().split('\n')
            judge_result = "不需要回复"  # 默认值
            reason = "解析失败，使用默认判断"
            
            for line in lines:
                line = line.strip()
                if line.startswith('判断：') or line.startswith('判断:'):
                    # 提取判断结果
                    result_part = line.split('：', 1)[-1] if '：' in line else line.split(':', 1)[-1]
                    result_part = result_part.strip()
                    
                    if "需要回复" in result_part:
                        judge_result = "需要回复"
                    elif "不需要回复" in result_part:
                        judge_result = "不需要回复"
                        
                elif line.startswith('理由：') or line.startswith('理由:'):
                    # 提取理由
                    reason_part = line.split('：', 1)[-1] if '：' in line else line.split(':', 1)[-1]
                    reason = reason_part.strip()
            
            # 如果没有找到标准格式，尝试简单的关键词匹配
            if reason == "解析失败，使用默认判断":
                if "需要回复" in response:
                    judge_result = "需要回复"
                    reason = "检测到'需要回复'关键词"
                elif "不需要回复" in response:
                    judge_result = "不需要回复" 
                    reason = "检测到'不需要回复'关键词"
                else:
                    reason = f"无法解析响应格式，原文: {response[:50]}..."
            
            logger.debug(f"{self.log_prefix} 解析LLM响应 - 判断: {judge_result}, 理由: {reason}")
            return judge_result, reason
            
        except Exception as e:
            logger.error(f"{self.log_prefix} 解析LLM响应时出错: {e}")
            return "不需要回复", f"解析异常: {str(e)}"

    @classmethod
    def reset_consecutive_count(cls):
        """重置连续计数器"""
        cls._consecutive_count = 0
        logger.debug("NoReplyAction连续计数器已重置")


class EmojiAction(BaseAction):
    """表情动作 - 发送表情包"""

    # 激活设置
    focus_activation_type = ActionActivationType.LLM_JUDGE
    normal_activation_type = ActionActivationType.RANDOM
    mode_enable = ChatMode.ALL
    parallel_action = True
    random_activation_probability = 0.1  # 默认值，可通过配置覆盖

    # 动作基本信息
    action_name = "emoji"
    action_description = "发送表情包辅助表达情绪"

    # LLM判断提示词
    llm_judge_prompt = """
    判定是否需要使用表情动作的条件：
    1. 用户明确要求使用表情包
    2. 这是一个适合表达强烈情绪的场合
    3. 不要发送太多表情包，如果你已经发送过多个表情包则回答"否"
    
    请回答"是"或"否"。
    """

    # 动作参数定义
    action_parameters = {"description": "文字描述你想要发送的表情包内容"}

    # 动作使用场景
    action_require = ["表达情绪时可以选择使用", "重点：不要连续发，如果你已经发过[表情包]，就不要选择此动作"]

    # 关联类型
    associated_types = ["emoji"]

    async def execute(self) -> Tuple[bool, str]:
        """执行表情动作"""
        logger.info(f"{self.log_prefix} 决定发送表情")

        try:
            # 1. 根据描述选择表情包
            description = self.action_data.get("description", "")
            emoji_result = await emoji_api.get_by_description(description)

            if not emoji_result:
                logger.warning(f"{self.log_prefix} 未找到匹配描述 '{description}' 的表情包")
                return False, f"未找到匹配 '{description}' 的表情包"

            emoji_base64, emoji_description, matched_emotion = emoji_result
            logger.info(f"{self.log_prefix} 找到表情包: {emoji_description}, 匹配情感: {matched_emotion}")

            # 使用BaseAction的便捷方法发送表情包
            success = await self.send_emoji(emoji_base64)

            if not success:
                logger.error(f"{self.log_prefix} 表情包发送失败")
                return False, "表情包发送失败"

            # 重置NoReplyAction的连续计数器
            NoReplyAction.reset_consecutive_count()

            return True, f"发送表情包: {emoji_description}"

        except Exception as e:
            logger.error(f"{self.log_prefix} 表情动作执行失败: {e}")
            return False, f"表情发送失败: {str(e)}"



class ExitFocusChatAction(BaseAction):
    """退出专注聊天动作 - 从专注模式切换到普通模式"""

    # 激活设置
    focus_activation_type = ActionActivationType.NEVER
    normal_activation_type = ActionActivationType.NEVER
    mode_enable = ChatMode.FOCUS
    parallel_action = False

    # 动作基本信息
    action_name = "exit_focus_chat"
    action_description = "退出专注聊天，从专注模式切换到普通模式"

    # LLM判断提示词
    llm_judge_prompt = """
    判定是否需要退出专注聊天的条件：
    1. 很长时间没有回复，应该退出专注聊天
    2. 当前内容不需要持续专注关注
    3. 聊天内容已经完成，话题结束
    
    请回答"是"或"否"。
    """

    # 动作参数定义
    action_parameters = {}

    # 动作使用场景
    action_require = [
        "很长时间没有回复，你决定退出专注聊天",
        "当前内容不需要持续专注关注，你决定退出专注聊天",
        "聊天内容已经完成，你决定退出专注聊天",
    ]

    # 关联类型
    associated_types = []

    async def execute(self) -> Tuple[bool, str]:
        """执行退出专注聊天动作"""
        logger.info(f"{self.log_prefix} 决定退出专注聊天: {self.reasoning}")

        try:
            # 标记状态切换请求
            self._mark_state_change()

            # 重置NoReplyAction的连续计数器
            NoReplyAction.reset_consecutive_count()

            status_message = "决定退出专注聊天模式"
            return True, status_message

        except Exception as e:
            logger.error(f"{self.log_prefix} 退出专注聊天动作执行失败: {e}")
            return False, f"退出专注聊天失败: {str(e)}"

    def _mark_state_change(self):
        """标记状态切换请求"""
        # 通过action_data传递状态切换命令
        self.action_data["_system_command"] = "stop_focus_chat"
        logger.info(f"{self.log_prefix} 已标记状态切换命令: stop_focus_chat")


@register_plugin
class CoreActionsPlugin(BasePlugin):
    """核心动作插件

    系统内置插件，提供基础的聊天交互功能：
    - Reply: 回复动作
    - NoReply: 不回复动作
    - Emoji: 表情动作

    注意：插件基本信息优先从_manifest.json文件中读取
    """

    # 插件基本信息
    plugin_name = "core_actions"  # 内部标识符
    enable_plugin = True
    config_file_name = "config.toml"

    # 配置节描述
    config_section_descriptions = {
        "plugin": "插件启用配置",
        "components": "核心组件启用配置",
        "no_reply": "不回复动作配置（智能等待机制）",
        "emoji": "表情动作配置",
    }

    # 配置Schema定义
    config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
            "config_version": ConfigField(type=str, default="0.0.8", description="配置文件版本"),
        },
        "components": {
            "enable_reply": ConfigField(type=bool, default=True, description="是否启用'回复'动作"),
            "enable_no_reply": ConfigField(type=bool, default=True, description="是否启用'不回复'动作"),
            "enable_emoji": ConfigField(type=bool, default=True, description="是否启用'表情'动作"),
            "enable_change_to_focus": ConfigField(type=bool, default=True, description="是否启用'切换到专注模式'动作"),
            "enable_exit_focus": ConfigField(type=bool, default=True, description="是否启用'退出专注模式'动作"),
        },
        "no_reply": {
            "max_timeout": ConfigField(type=int, default=1200, description="最大等待超时时间（秒）"),
            "min_judge_interval": ConfigField(type=float, default=1.0, description="LLM判断的最小间隔时间（秒），防止过于频繁"),
            "auto_exit_message_count": ConfigField(type=int, default=20, description="累计消息数量达到此阈值时自动结束等待"),
            "random_probability": ConfigField(
                type=float, default=0.8, description="Focus模式下，随机选择不回复的概率（0.0到1.0）", example=0.8
            ),
        },
        "emoji": {
            "random_probability": ConfigField(
                type=float, default=0.1, description="Normal模式下，随机发送表情的概率（0.0到1.0）", example=0.15
            )
        },
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""

        # --- 从配置动态设置Action/Command ---
        emoji_chance = self.get_config("emoji.random_probability", 0.1)
        EmojiAction.random_activation_probability = emoji_chance

        no_reply_probability = self.get_config("no_reply.random_probability", 0.8)
        NoReplyAction.random_activation_probability = no_reply_probability

        min_judge_interval = self.get_config("no_reply.min_judge_interval", 1.0)
        NoReplyAction._min_judge_interval = min_judge_interval

        auto_exit_message_count = self.get_config("no_reply.auto_exit_message_count", 20)
        NoReplyAction._auto_exit_message_count = auto_exit_message_count

        max_timeout = self.get_config("no_reply.max_timeout", 1200)
        NoReplyAction._max_timeout = max_timeout

        # --- 根据配置注册组件 ---
        components = []
        if self.get_config("components.enable_reply", True):
            components.append((ReplyAction.get_action_info(), ReplyAction))
        if self.get_config("components.enable_no_reply", True):
            components.append((NoReplyAction.get_action_info(), NoReplyAction))
        if self.get_config("components.enable_emoji", True):
            components.append((EmojiAction.get_action_info(), EmojiAction))
        if self.get_config("components.enable_exit_focus", True):
            components.append((ExitFocusChatAction.get_action_info(), ExitFocusChatAction))

        # components.append((DeepReplyAction.get_action_info(), DeepReplyAction))

        return components


# class DeepReplyAction(BaseAction):
#     """回复动作 - 参与聊天回复"""

#     # 激活设置
#     focus_activation_type = ActionActivationType.ALWAYS
#     normal_activation_type = ActionActivationType.NEVER
#     mode_enable = ChatMode.FOCUS
#     parallel_action = False

#     # 动作基本信息
#     action_name = "deep_reply"
#     action_description = "参与聊天回复，关注某个话题，对聊天内容进行深度思考，给出回复"

#     # 动作参数定义
#     action_parameters = {
#         "topic": "想要思考的话题"
#     }

#     # 动作使用场景
#     action_require = ["有些问题需要深度思考", "某个问题可能涉及多个方面", "某个问题涉及专业领域或者需要专业知识","这个问题讨论的很激烈，需要深度思考"]

#     # 关联类型
#     associated_types = ["text"]

#     async def execute(self) -> Tuple[bool, str]:
#         """执行回复动作"""
#         logger.info(f"{self.log_prefix} 决定深度思考")

#         try:
#             # 获取聊天观察
#             chatting_observation = self._get_chatting_observation()
#             if not chatting_observation:
#                 return False, "未找到聊天观察"

#             talking_message_str = chatting_observation.talking_message_str

#             # 处理回复目标
#             chat_stream = self.api.get_service("chat_stream")
#             anchor_message = await create_empty_anchor_message(chat_stream.platform, chat_stream.group_info, chat_stream)


#             llm_model = self.api.get_available_models().replyer_1

#             prompt = f"""
#             {talking_message_str}

#             在上面的聊天中，你对{self.action_data.get("topic", "")}感兴趣，形成深刻观点，请你思考,总结成一份学术论文,APA标准格式
#             """

#             success, response, reasoning, model_name = await self.api.generate_with_model(prompt, llm_model)

#             print(prompt)
#             print(f"DeepReplyAction: {response}")

#             # prompt = f"""
#             # {talking_message_str}

#             # 在上面的聊天中，你对{self.action_data.get("topic", "")}感兴趣，请你思考
#             # """

#             extra_info_block = self.action_data.get("extra_info_block", "")
#             extra_info_block += response
#             # extra_info_block += f"\n--------------------------------\n注意，这是最重要的内容！！！！！你现在可以用比较长的篇幅来表达你的观点，不要只回复一个字或者几个字\n由于你进入了深度思考模式，所以下方聊天记录的回复要求不再适用，请你自由的表达，不论字数长短限制\n\n--------------------------------\n注意，你现在可以用比较长的篇幅来表达你的观点，不要只回复一个字或者几个字\n由于你进入了深度思考模式，所以下方聊天记录的回复要求不再适用，请你自由的表达，不论字数长短限制\n"
#             # extra_info_block += f"\n--------------------------------\n注意，优先关注这句！！！！你现在可以用比较长的篇幅来表达你的观点，不要只回复一个字或者几个字\n由于你进入了深度思考模式，所以下方聊天记录的回复要求不再适用，请你自由的表达，不论字数长短限制\n\n--------------------------------\n注意，你现在可以用比较长的篇幅来表达你的观点，不要只回复一个字或者几个字\n由于你进入了深度思考模式，所以其他的回复要求不再适用，请你自由的表达，不论字数长短限制\n"
#             self.action_data["extra_info_block"] = extra_info_block


#             # 获取回复器服务
#             # replyer = self.api.get_service("replyer")
#             # if not replyer:
#                 # logger.error(f"{self.log_prefix} 未找到回复器服务")
#                 # return False, "回复器服务不可用"

#             # await self.send_message_by_expressor(extra_info_block)
#             await self.send_text(extra_info_block)
#             # 执行回复
#             # success, reply_set = await replyer.deal_reply(
#             #     cycle_timers=self.cycle_timers,
#             #     action_data=self.action_data,
#             #     anchor_message=anchor_message,
#             #     reasoning=self.reasoning,
#             #     thinking_id=self.thinking_id,
#             # )

#             # 构建回复文本
#             reply_text = "self._build_reply_text(reply_set)"

#             # 存储动作记录
#             await self.api.store_action_info(
#                 action_build_into_prompt=False,
#                 action_prompt_display=reply_text,
#                 action_done=True,
#                 thinking_id=self.thinking_id,
#                 action_data=self.action_data,
#             )

#             # 重置NoReplyAction的连续计数器
#             NoReplyAction.reset_consecutive_count()

#             return success, reply_text

#         except Exception as e:
#             logger.error(f"{self.log_prefix} 回复动作执行失败: {e}")
#             return False, f"回复失败: {str(e)}"

#     def _get_chatting_observation(self) -> Optional[ChattingObservation]:
#         """获取聊天观察对象"""
#         observations = self.api.get_service("observations") or []
#         for obs in observations:
#             if isinstance(obs, ChattingObservation):
#                 return obs
#         return None


#     def _build_reply_text(self, reply_set) -> str:
#         """构建回复文本"""
#         reply_text = ""
#         if reply_set:
#             for reply in reply_set:
#                 data = reply[1]
#                 reply_text += data
#         return reply_text
