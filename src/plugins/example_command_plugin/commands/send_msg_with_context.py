from src.common.logger_manager import get_logger
from src.chat.command.command_handler import BaseCommand, register_command
from src.chat.actions.plugin_api.message_api import MessageAPI
from typing import Tuple, Optional
import time

logger = get_logger("send_msg_with_context")


@register_command
class ContextAwareSendCommand(BaseCommand, MessageAPI):
    """上下文感知的发送消息命令，展示如何利用原始消息信息"""

    command_name = "csend"
    command_description = "带上下文感知的发送消息命令"
    command_pattern = (
        r"^/csend\s+(?P<target_type>group|user|here|reply)\s+(?P<target_id_or_content>.*?)(?:\s+(?P<content>.*))?$"
    )
    command_help = "使用方法: /csend <target_type> <参数> [内容]"
    command_examples = [
        "/csend group 123456789 大家好！",
        "/csend user 987654321 私聊消息",
        "/csend here 在当前聊天发送",
        "/csend reply 回复当前群/私聊",
    ]
    enable_command = True

    # 管理员用户ID列表（示例）
    ADMIN_USERS = ["123456789", "987654321"]  # 可以从配置文件读取

    def __init__(self, message):
        super().__init__(message)
        self._services = {}
        self.log_prefix = f"[Command:{self.command_name}]"

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行上下文感知的发送命令"""
        try:
            # 获取命令发送者信息
            sender = self.message.message_info.user_info
            current_group = self.message.message_info.group_info

            # 权限检查
            if not self._check_permission(sender.user_id):
                return False, f"❌ 权限不足，只有管理员可以使用此命令\n你的ID: {sender.user_id}"

            # 解析命令参数
            target_type = self.matched_groups.get("target_type")
            target_id_or_content = self.matched_groups.get("target_id_or_content", "")
            content = self.matched_groups.get("content", "")

            # 根据目标类型处理不同情况
            if target_type == "here":
                # 发送到当前聊天
                return await self._send_to_current_chat(target_id_or_content, sender, current_group)

            elif target_type == "reply":
                # 回复到当前聊天，带发送者信息
                return await self._send_reply_with_context(target_id_or_content, sender, current_group)

            elif target_type in ["group", "user"]:
                # 发送到指定目标
                if not content:
                    return False, "指定群聊或用户时需要提供消息内容"
                return await self._send_to_target(target_type, target_id_or_content, content, sender)

            else:
                return False, f"不支持的目标类型: {target_type}"

        except Exception as e:
            logger.error(f"{self.log_prefix} 执行上下文感知发送命令时出错: {e}")
            return False, f"命令执行出错: {str(e)}"

    def _check_permission(self, user_id: str) -> bool:
        """检查用户权限"""
        return user_id in self.ADMIN_USERS

    async def _send_to_current_chat(self, content: str, sender, current_group) -> Tuple[bool, str]:
        """发送到当前聊天"""
        if not content:
            return False, "消息内容不能为空"

        # 构建带发送者信息的消息
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        if current_group:
            # 群聊
            formatted_content = f"[管理员转发 {timestamp}] {sender.user_nickname}({sender.user_id}): {content}"
            success = await self.send_text_to_group(
                text=formatted_content, group_id=current_group.group_id, platform="qq"
            )
            target_desc = f"当前群聊 {current_group.group_name}({current_group.group_id})"
        else:
            # 私聊
            formatted_content = f"[管理员消息 {timestamp}]: {content}"
            success = await self.send_text_to_user(text=formatted_content, user_id=sender.user_id, platform="qq")
            target_desc = "当前私聊"

        if success:
            return True, f"✅ 消息已发送到{target_desc}"
        else:
            return False, f"❌ 发送到{target_desc}失败"

    async def _send_reply_with_context(self, content: str, sender, current_group) -> Tuple[bool, str]:
        """发送回复，带完整上下文信息"""
        if not content:
            return False, "回复内容不能为空"

        # 获取当前时间和环境信息
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        # 构建上下文信息
        context_info = [
            f"📢 管理员回复 [{timestamp}]",
            f"👤 发送者: {sender.user_nickname}({sender.user_id})",
        ]

        if current_group:
            context_info.append(f"👥 当前群聊: {current_group.group_name}({current_group.group_id})")
            target_desc = f"群聊 {current_group.group_name}"
        else:
            context_info.append("💬 当前环境: 私聊")
            target_desc = "私聊"

        context_info.extend([f"📝 回复内容: {content}", "─" * 30])

        formatted_content = "\n".join(context_info)

        # 发送消息
        if current_group:
            success = await self.send_text_to_group(
                text=formatted_content, group_id=current_group.group_id, platform="qq"
            )
        else:
            success = await self.send_text_to_user(text=formatted_content, user_id=sender.user_id, platform="qq")

        if success:
            return True, f"✅ 带上下文的回复已发送到{target_desc}"
        else:
            return False, f"❌ 发送上下文回复到{target_desc}失败"

    async def _send_to_target(self, target_type: str, target_id: str, content: str, sender) -> Tuple[bool, str]:
        """发送到指定目标，带发送者追踪信息"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        # 构建带追踪信息的消息
        tracking_info = f"[管理转发 {timestamp}] 来自 {sender.user_nickname}({sender.user_id})"
        formatted_content = f"{tracking_info}\n{content}"

        if target_type == "group":
            success = await self.send_text_to_group(text=formatted_content, group_id=target_id, platform="qq")
            target_desc = f"群聊 {target_id}"
        else:  # user
            success = await self.send_text_to_user(text=formatted_content, user_id=target_id, platform="qq")
            target_desc = f"用户 {target_id}"

        if success:
            return True, f"✅ 带追踪信息的消息已发送到{target_desc}"
        else:
            return False, f"❌ 发送到{target_desc}失败"


@register_command
class MessageContextCommand(BaseCommand):
    """消息上下文命令，展示如何获取和利用上下文信息"""

    command_name = "context"
    command_description = "显示当前消息的完整上下文信息"
    command_pattern = r"^/context$"
    command_help = "使用方法: /context - 显示当前环境的上下文信息"
    command_examples = ["/context"]
    enable_command = True

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """显示上下文信息"""
        try:
            message = self.message
            user = message.message_info.user_info
            group = message.message_info.group_info

            # 构建上下文信息
            context_lines = [
                "🌐 当前上下文信息",
                "=" * 30,
                "",
                "⏰ 时间信息:",
                f"  消息时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(message.message_info.time))}",
                f"  时间戳: {message.message_info.time}",
                "",
                "👤 发送者:",
                f"  用户ID: {user.user_id}",
                f"  昵称: {user.user_nickname}",
                f"  群名片: {user.user_cardname or '无'}",
                f"  平台: {user.platform}",
            ]

            if group:
                context_lines.extend(
                    [
                        "",
                        "👥 群聊环境:",
                        f"  群ID: {group.group_id}",
                        f"  群名: {group.group_name or '未知'}",
                        f"  平台: {group.platform}",
                    ]
                )
            else:
                context_lines.extend(
                    [
                        "",
                        "💬 私聊环境",
                    ]
                )

            # 添加聊天流信息
            if hasattr(message, "chat_stream") and message.chat_stream:
                chat_stream = message.chat_stream
                context_lines.extend(
                    [
                        "",
                        "🔄 聊天流:",
                        f"  流ID: {chat_stream.stream_id}",
                    ]
                )

            # 添加消息内容信息
            context_lines.extend(
                [
                    "",
                    "📝 消息内容:",
                    f"  原始内容: {message.processed_plain_text}",
                    f"  消息长度: {len(message.processed_plain_text)} 字符",
                    f"  消息ID: {message.message_info.message_id}",
                ]
            )

            return True, "\n".join(context_lines)

        except Exception as e:
            logger.error(f"{self.log_prefix} 获取上下文信息时出错: {e}")
            return False, f"获取上下文失败: {str(e)}"
