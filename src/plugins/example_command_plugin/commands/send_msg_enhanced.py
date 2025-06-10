from src.common.logger_manager import get_logger
from src.chat.command.command_handler import BaseCommand, register_command
from src.chat.actions.plugin_api.message_api import MessageAPI
from typing import Tuple, Optional

logger = get_logger("send_msg_enhanced")


@register_command
class SendMessageEnhancedCommand(BaseCommand, MessageAPI):
    """增强版发送消息命令，支持多种消息类型和平台"""

    command_name = "sendfull"
    command_description = "增强版消息发送命令，支持多种类型和平台"
    command_pattern = r"^/sendfull\s+(?P<msg_type>text|image|emoji)\s+(?P<target_type>group|user)\s+(?P<target_id>\d+)(?:\s+(?P<platform>\w+))?\s+(?P<content>.+)$"
    command_help = "使用方法: /sendfull <消息类型> <目标类型> <ID> [平台] <内容>"
    command_examples = [
        "/sendfull text group 123456789 qq 大家好！这是文本消息",
        "/sendfull image user 987654321 https://example.com/image.jpg",
        "/sendfull emoji group 123456789 😄",
        "/sendfull text user 987654321 qq 私聊消息",
    ]
    enable_command = True

    def __init__(self, message):
        super().__init__(message)
        self._services = {}
        self.log_prefix = f"[Command:{self.command_name}]"

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行增强版发送消息命令"""
        try:
            # 获取匹配参数
            msg_type = self.matched_groups.get("msg_type")  # 消息类型: text/image/emoji
            target_type = self.matched_groups.get("target_type")  # 目标类型: group/user
            target_id = self.matched_groups.get("target_id")  # 目标ID
            platform = self.matched_groups.get("platform") or "qq"  # 平台，默认qq
            content = self.matched_groups.get("content")  # 内容

            if not all([msg_type, target_type, target_id, content]):
                return False, "命令参数不完整，请检查格式"

            # 验证消息类型
            valid_types = ["text", "image", "emoji"]
            if msg_type not in valid_types:
                return False, f"不支持的消息类型: {msg_type}，支持的类型: {', '.join(valid_types)}"

            # 验证目标类型
            if target_type not in ["group", "user"]:
                return False, "目标类型只能是 group 或 user"

            logger.info(f"{self.log_prefix} 执行发送命令: {msg_type} -> {target_type}:{target_id} (平台:{platform})")

            # 根据消息类型和目标类型发送消息
            is_group = target_type == "group"
            success = await self.send_message_to_target(
                message_type=msg_type, content=content, platform=platform, target_id=target_id, is_group=is_group
            )

            # 构建结果消息
            target_desc = f"{'群聊' if is_group else '用户'} {target_id} (平台: {platform})"
            msg_type_desc = {"text": "文本", "image": "图片", "emoji": "表情"}.get(msg_type, msg_type)

            if success:
                return True, f"✅ {msg_type_desc}消息已成功发送到 {target_desc}"
            else:
                return False, f"❌ {msg_type_desc}消息发送失败，可能是目标 {target_desc} 不存在或没有权限"

        except Exception as e:
            logger.error(f"{self.log_prefix} 执行增强发送命令时出错: {e}")
            return False, f"命令执行出错: {str(e)}"


@register_command
class SendQuickCommand(BaseCommand, MessageAPI):
    """快速发送文本消息命令"""

    command_name = "msg"
    command_description = "快速发送文本消息到群聊"
    command_pattern = r"^/msg\s+(?P<group_id>\d+)\s+(?P<content>.+)$"
    command_help = "使用方法: /msg <群ID> <消息内容> - 快速发送文本到指定群聊"
    command_examples = ["/msg 123456789 大家好！", "/msg 987654321 这是一条快速消息"]
    enable_command = True

    def __init__(self, message):
        super().__init__(message)
        self._services = {}
        self.log_prefix = f"[Command:{self.command_name}]"

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行快速发送消息命令"""
        try:
            group_id = self.matched_groups.get("group_id")
            content = self.matched_groups.get("content")

            if not all([group_id, content]):
                return False, "命令参数不完整"

            logger.info(f"{self.log_prefix} 快速发送到群 {group_id}: {content[:50]}...")

            success = await self.send_text_to_group(text=content, group_id=group_id, platform="qq")

            if success:
                return True, f"✅ 消息已发送到群 {group_id}"
            else:
                return False, f"❌ 发送到群 {group_id} 失败"

        except Exception as e:
            logger.error(f"{self.log_prefix} 快速发送命令出错: {e}")
            return False, f"发送失败: {str(e)}"


@register_command
class SendPrivateCommand(BaseCommand, MessageAPI):
    """发送私聊消息命令"""

    command_name = "pm"
    command_description = "发送私聊消息到指定用户"
    command_pattern = r"^/pm\s+(?P<user_id>\d+)\s+(?P<content>.+)$"
    command_help = "使用方法: /pm <用户ID> <消息内容> - 发送私聊消息"
    command_examples = ["/pm 123456789 你好！", "/pm 987654321 这是私聊消息"]
    enable_command = True

    def __init__(self, message):
        super().__init__(message)
        self._services = {}
        self.log_prefix = f"[Command:{self.command_name}]"

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行私聊发送命令"""
        try:
            user_id = self.matched_groups.get("user_id")
            content = self.matched_groups.get("content")

            if not all([user_id, content]):
                return False, "命令参数不完整"

            logger.info(f"{self.log_prefix} 发送私聊到用户 {user_id}: {content[:50]}...")

            success = await self.send_text_to_user(text=content, user_id=user_id, platform="qq")

            if success:
                return True, f"✅ 私聊消息已发送到用户 {user_id}"
            else:
                return False, f"❌ 发送私聊到用户 {user_id} 失败"

        except Exception as e:
            logger.error(f"{self.log_prefix} 私聊发送命令出错: {e}")
            return False, f"私聊发送失败: {str(e)}"
