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
from src.plugin_system.apis import emoji_api, generator_api, message_api

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
    action_parameters = {"reply_to": "你要回复的对方的发言内容，格式：（用户名:发言内容），可以为none"}

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
            first_reply = False
            for reply_seg in reply_set:
                data = reply_seg[1]
                if not first_reply and need_reply:
                    await self.send_text(content=data, reply_to=self.action_data.get("reply_to", ""))
                else:
                    await self.send_text(content=data)
                    first_reply = True
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
    """不回复动作，继承时会等待新消息或超时"""

    # focus_activation_type = ActionActivationType.ALWAYS
    focus_activation_type = ActionActivationType.RANDOM
    normal_activation_type = ActionActivationType.NEVER
    mode_enable = ChatMode.FOCUS
    parallel_action = False

    # 动作基本信息
    action_name = "no_reply"
    action_description = "暂时不回复消息"

    # 默认超时时间，将由插件在注册时设置
    waiting_timeout = 1200

    # 连续no_reply计数器
    _consecutive_count = 0

    random_activation_probability = 0.2

    # 分级等待时间
    _waiting_stages = [10, 60, 600]  # 第1、2、3次的等待时间

    # 动作参数定义
    action_parameters = {"reason": "不回复的原因"}

    # 动作使用场景
    action_require = ["你发送了消息，目前无人回复"]

    # 关联类型
    associated_types = []

    async def execute(self) -> Tuple[bool, str]:
        """执行不回复动作，等待新消息或超时"""
        try:
            # 增加连续计数
            NoReplyAction._consecutive_count += 1
            count = NoReplyAction._consecutive_count

            reason = self.action_data.get("reason", "")

            # 计算本次等待时间
            if count <= len(self._waiting_stages):
                # 前3次使用预设时间
                stage_time = self._waiting_stages[count - 1]
                # 如果WAITING_TIME_THRESHOLD更小，则使用它
                timeout = min(stage_time, self.waiting_timeout)
            else:
                # 第4次及以后使用WAITING_TIME_THRESHOLD
                timeout = self.waiting_timeout

            logger.info(
                f"{self.log_prefix} 选择不回复(第{count}次连续)，等待新消息中... (超时: {timeout}秒)，原因: {reason}"
            )

            # 等待新消息或达到时间上限
            result = await self.wait_for_new_message(timeout)

            # 如果有新消息或者超时，都不重置计数器，因为可能还会继续no_reply
            return result

        except Exception as e:
            logger.error(f"{self.log_prefix} 不回复动作执行失败: {e}")
            return False, f"不回复动作执行失败: {e}"

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


class ChangeToFocusChatAction(BaseAction):
    """切换到专注聊天动作 - 从普通模式切换到专注模式"""

    focus_activation_type = ActionActivationType.NEVER
    normal_activation_type = ActionActivationType.NEVER
    mode_enable = ChatMode.NORMAL
    parallel_action = False

    # 动作基本信息
    action_name = "change_to_focus_chat"
    action_description = "切换到专注聊天，从普通模式切换到专注模式"

    # 动作参数定义
    action_parameters = {}

    apex = 111
    # 动作使用场景
    action_require = [
        "你想要进入专注聊天模式",
        "聊天上下文中自己的回复条数较多（超过3-4条）",
        "对话进行得非常热烈活跃",
        "用户表现出深入交流的意图",
        "话题需要更专注和深入的讨论",
    ]

    async def execute(self) -> Tuple[bool, str]:
        """执行切换到专注聊天动作"""
        logger.info(f"{self.log_prefix} 决定切换到专注聊天: {self.reasoning}")

        # 重置NoReplyAction的连续计数器
        NoReplyAction.reset_consecutive_count()

        # 这里只做决策标记，具体切换逻辑由上层管理器处理
        return True, "决定切换到专注聊天模式"


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
        "no_reply": "不回复动作配置",
        "emoji": "表情动作配置",
    }

    # 配置Schema定义
    config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
            "config_version": ConfigField(type=str, default="0.0.2", description="配置文件版本"),
        },
        "components": {
            "enable_reply": ConfigField(type=bool, default=True, description="是否启用'回复'动作"),
            "enable_no_reply": ConfigField(type=bool, default=True, description="是否启用'不回复'动作"),
            "enable_emoji": ConfigField(type=bool, default=True, description="是否启用'表情'动作"),
            "enable_change_to_focus": ConfigField(type=bool, default=True, description="是否启用'切换到专注模式'动作"),
            "enable_exit_focus": ConfigField(type=bool, default=True, description="是否启用'退出专注模式'动作"),
        },
        "no_reply": {
            "waiting_timeout": ConfigField(
                type=int, default=1200, description="连续不回复时，最长的等待超时时间（秒）"
            ),
            "stage_1_wait": ConfigField(type=int, default=10, description="第1次连续不回复的等待时间（秒）"),
            "stage_2_wait": ConfigField(type=int, default=60, description="第2次连续不回复的等待时间（秒）"),
            "stage_3_wait": ConfigField(type=int, default=600, description="第3次连续不回复的等待时间（秒）"),
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

        no_reply_timeout = self.get_config("no_reply.waiting_timeout", 1200)
        NoReplyAction.waiting_timeout = no_reply_timeout

        stage1 = self.get_config("no_reply.stage_1_wait", 10)
        stage2 = self.get_config("no_reply.stage_2_wait", 60)
        stage3 = self.get_config("no_reply.stage_3_wait", 600)
        NoReplyAction._waiting_stages = [stage1, stage2, stage3]

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
        if self.get_config("components.enable_change_to_focus", True):
            components.append((ChangeToFocusChatAction.get_action_info(), ChangeToFocusChatAction))
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
