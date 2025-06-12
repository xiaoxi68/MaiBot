"""
核心动作插件

将系统核心动作（reply、no_reply、emoji）转换为新插件系统格式
这是系统的内置插件，提供基础的聊天交互功能
"""

import re
from typing import List, Tuple, Type, Optional

# 导入新插件系统
from src.plugin_system import BasePlugin, register_plugin, BaseAction, ComponentInfo, ActionActivationType, ChatMode
from src.plugin_system.base.base_command import BaseCommand

# 导入依赖的系统组件
from src.common.logger import get_logger
from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
from src.chat.focus_chat.hfc_utils import create_empty_anchor_message

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

    # 动作参数定义（旧系统格式）
    action_parameters = {
        "reply_to": "如果是明确回复某个人的发言，请在reply_to参数中指定，格式：（用户名:发言内容），如果不是，reply_to的值设为none"
    }

    # 动作使用场景（旧系统字段名）
    action_require = ["你想要闲聊或者随便附和", "有人提到你", "如果你刚刚进行了回复，不要对同一个话题重复回应"]

    # 关联类型
    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        """执行回复动作"""
        logger.info(f"{self.log_prefix} 决定回复: {self.reasoning}")

        try:
            # 获取聊天观察
            chatting_observation = self._get_chatting_observation()
            if not chatting_observation:
                return False, "未找到聊天观察"

            # 处理回复目标
            anchor_message = await self._resolve_reply_target(chatting_observation)

            # 获取回复器服务
            replyer = self.api.get_service("replyer")
            if not replyer:
                logger.error(f"{self.log_prefix} 未找到回复器服务")
                return False, "回复器服务不可用"

            # 执行回复
            success, reply_set = await replyer.deal_reply(
                cycle_timers=self.cycle_timers,
                action_data=self.action_data,
                anchor_message=anchor_message,
                reasoning=self.reasoning,
                thinking_id=self.thinking_id,
            )

            # 构建回复文本
            reply_text = self._build_reply_text(reply_set)

            # 存储动作记录
            await self.api.store_action_info(
                action_build_into_prompt=False,
                action_prompt_display=reply_text,
                action_done=True,
                thinking_id=self.thinking_id,
                action_data=self.action_data,
            )

            return success, reply_text

        except Exception as e:
            logger.error(f"{self.log_prefix} 回复动作执行失败: {e}")
            return False, f"回复失败: {str(e)}"

    def _get_chatting_observation(self) -> Optional[ChattingObservation]:
        """获取聊天观察对象"""
        observations = self.api.get_service("observations") or []
        for obs in observations:
            if isinstance(obs, ChattingObservation):
                return obs
        return None

    async def _resolve_reply_target(self, chatting_observation: ChattingObservation):
        """解析回复目标消息"""
        reply_to = self.action_data.get("reply_to", "none")

        if ":" in reply_to or "：" in reply_to:
            # 解析回复目标格式：用户名:消息内容
            parts = re.split(pattern=r"[:：]", string=reply_to, maxsplit=1)
            if len(parts) == 2:
                target = parts[1].strip()
                anchor_message = chatting_observation.search_message_by_text(target)
                if anchor_message:
                    chat_stream = self.api.get_service("chat_stream")
                    if chat_stream:
                        anchor_message.update_chat_stream(chat_stream)
                    return anchor_message

        # 创建空锚点消息
        logger.info(f"{self.log_prefix} 未找到锚点消息，创建占位符")
        chat_stream = self.api.get_service("chat_stream")
        if chat_stream:
            return await create_empty_anchor_message(chat_stream.platform, chat_stream.group_info, chat_stream)
        return None

    def _build_reply_text(self, reply_set) -> str:
        """构建回复文本"""
        reply_text = ""
        if reply_set:
            for reply in reply_set:
                reply_type = reply[0]
                data = reply[1]
                if reply_type in ["text", "emoji"]:
                    reply_text += data
        return reply_text


class NoReplyAction(BaseAction):
    """不回复动作，继承时会等待新消息或超时"""

    focus_activation_type = ActionActivationType.ALWAYS
    normal_activation_type = ActionActivationType.NEVER
    mode_enable = ChatMode.FOCUS
    parallel_action = False

    # 默认超时时间，将由插件在注册时设置
    waiting_timeout = 1200

    # 动作参数定义
    action_parameters = {}

    # 动作使用场景
    action_require = ["你连续发送了太多消息，且无人回复", "想要暂时不回复"]

    # 关联类型
    associated_types = []

    async def execute(self) -> Tuple[bool, str]:
        """执行不回复动作，等待新消息或超时"""
        try:
            # 使用类属性中的超时时间
            timeout = self.waiting_timeout

            logger.info(f"{self.log_prefix} 选择不回复，等待新消息中... (超时: {timeout}秒)")

            # 等待新消息或达到时间上限
            return await self.api.wait_for_new_message(timeout)

        except Exception as e:
            logger.error(f"{self.log_prefix} 不回复动作执行失败: {e}")
            return False, f"不回复动作执行失败: {e}"


class EmojiAction(BaseAction):
    """表情动作 - 发送表情包"""

    # 激活设置
    focus_activation_type = ActionActivationType.LLM_JUDGE
    normal_activation_type = ActionActivationType.RANDOM
    mode_enable = ChatMode.ALL
    parallel_action = True
    random_activation_probability = 0.1  # 默认值，可通过配置覆盖

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
            # 创建空锚点消息
            anchor_message = await self._create_anchor_message()
            if not anchor_message:
                return False, "无法创建锚点消息"

            # 获取回复器服务
            replyer = self.api.get_service("replyer")
            if not replyer:
                logger.error(f"{self.log_prefix} 未找到回复器服务")
                return False, "回复器服务不可用"

            # 执行表情处理
            success, reply_set = await replyer.deal_emoji(
                cycle_timers=self.cycle_timers,
                action_data=self.action_data,
                anchor_message=anchor_message,
                thinking_id=self.thinking_id,
            )

            # 构建回复文本
            reply_text = self._build_reply_text(reply_set)

            return success, reply_text

        except Exception as e:
            logger.error(f"{self.log_prefix} 表情动作执行失败: {e}")
            return False, f"表情发送失败: {str(e)}"

    async def _create_anchor_message(self):
        """创建锚点消息"""
        chat_stream = self.api.get_service("chat_stream")
        if chat_stream:
            logger.info(f"{self.log_prefix} 为表情包创建占位符")
            return await create_empty_anchor_message(chat_stream.platform, chat_stream.group_info, chat_stream)
        return None

    def _build_reply_text(self, reply_set) -> str:
        """构建回复文本"""
        reply_text = ""
        if reply_set:
            for reply in reply_set:
                reply_type = reply[0]
                data = reply[1]
                if reply_type in ["text", "emoji"]:
                    reply_text += data
        return reply_text


class ExitFocusChatAction(BaseAction):
    """退出专注聊天动作 - 从专注模式切换到普通模式"""

    # 激活设置
    focus_activation_type = ActionActivationType.LLM_JUDGE
    normal_activation_type = ActionActivationType.NEVER
    mode_enable = ChatMode.FOCUS
    parallel_action = False

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
    """

    # 插件基本信息
    plugin_name = "core_actions"
    plugin_description = "系统核心动作插件，提供基础聊天交互功能"
    plugin_version = "1.0.0"
    plugin_author = "MaiBot团队"
    enable_plugin = True
    config_file_name = "config.toml"

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""

        # 从配置获取表情动作的随机概率
        emoji_chance = self.get_config("emoji.random_probability", 0.1)

        # 动态设置EmojiAction的随机概率
        EmojiAction.random_activation_probability = emoji_chance

        # 从配置获取不回复动作的超时时间
        no_reply_timeout = self.get_config("no_reply.waiting_timeout", 1200)

        # 动态设置NoReplyAction的超时时间
        NoReplyAction.waiting_timeout = no_reply_timeout

        return [
            # 回复动作
            (ReplyAction.get_action_info(name="reply", description="参与聊天回复，处理文本和表情的发送"), ReplyAction),
            # 不回复动作
            (
                NoReplyAction.get_action_info(name="no_reply", description="暂时不回复消息，等待新消息或超时"),
                NoReplyAction,
            ),
            # 表情动作
            (EmojiAction.get_action_info(name="emoji", description="发送表情包辅助表达情绪"), EmojiAction),
            # 退出专注聊天动作
            (
                ExitFocusChatAction.get_action_info(
                    name="exit_focus_chat", description="退出专注聊天，从专注模式切换到普通模式"
                ),
                ExitFocusChatAction,
            ),
            # 示例Command - Ping命令
            (PingCommand.get_command_info(name="ping", description="测试机器人响应，拦截后续处理"), PingCommand),
            # 示例Command - Log命令
            (LogCommand.get_command_info(name="log", description="记录消息到日志，不拦截后续处理"), LogCommand),
        ]


# ===== 示例Command组件 =====


class PingCommand(BaseCommand):
    """Ping命令 - 测试响应，拦截消息处理"""

    command_pattern = r"^/ping(\s+(?P<message>.+))?$"
    command_help = "测试机器人响应 - 拦截后续处理"
    command_examples = ["/ping", "/ping 测试消息"]
    intercept_message = True  # 拦截消息，不继续处理

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行ping命令"""
        try:
            message = self.matched_groups.get("message", "")
            reply_text = f"🏓 Pong! {message}" if message else "🏓 Pong!"

            await self.send_reply(reply_text)
            return True, f"发送ping响应: {reply_text}"

        except Exception as e:
            logger.error(f"Ping命令执行失败: {e}")
            return False, f"执行失败: {str(e)}"


class LogCommand(BaseCommand):
    """日志命令 - 记录消息但不拦截后续处理"""

    command_pattern = r"^/log(\s+(?P<level>debug|info|warn|error))?$"
    command_help = "记录当前消息到日志 - 不拦截后续处理"
    command_examples = ["/log", "/log info", "/log debug"]
    intercept_message = False  # 不拦截消息，继续后续处理

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行日志命令"""
        try:
            level = self.matched_groups.get("level", "info")
            user_nickname = self.message.message_info.user_info.user_nickname
            content = self.message.processed_plain_text

            log_message = f"[{level.upper()}] 用户 {user_nickname}: {content}"

            # 根据级别记录日志
            if level == "debug":
                logger.debug(log_message)
            elif level == "warn":
                logger.warning(log_message)
            elif level == "error":
                logger.error(log_message)
            else:
                logger.info(log_message)

            # 不发送回复，让消息继续处理
            return True, f"已记录到{level}级别日志"

        except Exception as e:
            logger.error(f"Log命令执行失败: {e}")
            return False, f"执行失败: {str(e)}"
