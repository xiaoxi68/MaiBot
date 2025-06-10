from src.common.logger_manager import get_logger
from src.chat.command.command_handler import BaseCommand, register_command
from typing import Tuple, Optional

logger = get_logger("message_info_command")


@register_command
class MessageInfoCommand(BaseCommand):
    """消息信息查看命令，展示发送命令的原始消息和相关信息"""

    command_name = "msginfo"
    command_description = "查看发送命令的原始消息信息"
    command_pattern = r"^/msginfo(?:\s+(?P<detail>full|simple))?$"
    command_help = "使用方法: /msginfo [full|simple] - 查看当前消息的详细信息"
    command_examples = ["/msginfo", "/msginfo full", "/msginfo simple"]
    enable_command = True

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行消息信息查看命令"""
        try:
            detail_level = self.matched_groups.get("detail", "simple")

            logger.info(f"{self.log_prefix} 查看消息信息，详细级别: {detail_level}")

            if detail_level == "full":
                info_text = self._get_full_message_info()
            else:
                info_text = self._get_simple_message_info()

            return True, info_text

        except Exception as e:
            logger.error(f"{self.log_prefix} 获取消息信息时出错: {e}")
            return False, f"获取消息信息失败: {str(e)}"

    def _get_simple_message_info(self) -> str:
        """获取简化的消息信息"""
        message = self.message

        # 基础信息
        info_lines = [
            "📨 消息信息概览",
            f"🆔 消息ID: {message.message_info.message_id}",
            f"⏰ 时间: {message.message_info.time}",
            f"🌐 平台: {message.message_info.platform}",
        ]

        # 发送者信息
        user = message.message_info.user_info
        info_lines.extend(
            [
                "",
                "👤 发送者信息:",
                f"  用户ID: {user.user_id}",
                f"  昵称: {user.user_nickname}",
                f"  群名片: {user.user_cardname or '无'}",
            ]
        )

        # 群聊信息（如果是群聊）
        if message.message_info.group_info:
            group = message.message_info.group_info
            info_lines.extend(
                [
                    "",
                    "👥 群聊信息:",
                    f"  群ID: {group.group_id}",
                    f"  群名: {group.group_name or '未知'}",
                ]
            )
        else:
            info_lines.extend(
                [
                    "",
                    "💬 消息类型: 私聊消息",
                ]
            )

        # 消息内容
        info_lines.extend(
            [
                "",
                "📝 消息内容:",
                f"  原始文本: {message.processed_plain_text}",
                f"  是否表情: {'是' if getattr(message, 'is_emoji', False) else '否'}",
            ]
        )

        # 聊天流信息
        if hasattr(message, "chat_stream") and message.chat_stream:
            chat_stream = message.chat_stream
            info_lines.extend(
                [
                    "",
                    "🔄 聊天流信息:",
                    f"  流ID: {chat_stream.stream_id}",
                    f"  是否激活: {'是' if chat_stream.is_active else '否'}",
                ]
            )

        return "\n".join(info_lines)

    def _get_full_message_info(self) -> str:
        """获取完整的消息信息（包含技术细节）"""
        message = self.message

        info_lines = [
            "📨 完整消息信息",
            "=" * 40,
        ]

        # 消息基础信息
        info_lines.extend(
            [
                "",
                "🔍 基础消息信息:",
                f"  消息ID: {message.message_info.message_id}",
                f"  时间戳: {message.message_info.time}",
                f"  平台: {message.message_info.platform}",
                f"  处理后文本: {message.processed_plain_text}",
                f"  详细文本: {message.detailed_plain_text[:100]}{'...' if len(message.detailed_plain_text) > 100 else ''}",
            ]
        )

        # 用户详细信息
        user = message.message_info.user_info
        info_lines.extend(
            [
                "",
                "👤 发送者详细信息:",
                f"  用户ID: {user.user_id}",
                f"  昵称: {user.user_nickname}",
                f"  群名片: {user.user_cardname or '无'}",
                f"  平台: {user.platform}",
            ]
        )

        # 群聊详细信息
        if message.message_info.group_info:
            group = message.message_info.group_info
            info_lines.extend(
                [
                    "",
                    "👥 群聊详细信息:",
                    f"  群ID: {group.group_id}",
                    f"  群名: {group.group_name or '未知'}",
                    f"  平台: {group.platform}",
                ]
            )
        else:
            info_lines.append("\n💬 消息类型: 私聊消息")

        # 消息段信息
        if message.message_segment:
            info_lines.extend(
                [
                    "",
                    "📦 消息段信息:",
                    f"  类型: {message.message_segment.type}",
                    f"  数据类型: {type(message.message_segment.data).__name__}",
                    f"  数据预览: {str(message.message_segment.data)[:200]}{'...' if len(str(message.message_segment.data)) > 200 else ''}",
                ]
            )

        # 聊天流详细信息
        if hasattr(message, "chat_stream") and message.chat_stream:
            chat_stream = message.chat_stream
            info_lines.extend(
                [
                    "",
                    "🔄 聊天流详细信息:",
                    f"  流ID: {chat_stream.stream_id}",
                    f"  平台: {chat_stream.platform}",
                    f"  是否激活: {'是' if chat_stream.is_active else '否'}",
                    f"  用户信息: {chat_stream.user_info.user_nickname} ({chat_stream.user_info.user_id})",
                    f"  群信息: {getattr(chat_stream.group_info, 'group_name', '私聊') if chat_stream.group_info else '私聊'}",
                ]
            )

        # 回复信息
        if hasattr(message, "reply") and message.reply:
            info_lines.extend(
                [
                    "",
                    "↩️ 回复信息:",
                    f"  回复消息ID: {message.reply.message_info.message_id}",
                    f"  回复内容: {message.reply.processed_plain_text[:100]}{'...' if len(message.reply.processed_plain_text) > 100 else ''}",
                ]
            )

        # 原始消息数据（如果存在）
        if hasattr(message, "raw_message") and message.raw_message:
            info_lines.extend(
                [
                    "",
                    "🗂️ 原始消息数据:",
                    f"  数据类型: {type(message.raw_message).__name__}",
                    f"  数据大小: {len(str(message.raw_message))} 字符",
                ]
            )

        return "\n".join(info_lines)


@register_command
class SenderInfoCommand(BaseCommand):
    """发送者信息命令，快速查看发送者信息"""

    command_name = "whoami"
    command_description = "查看发送命令的用户信息"
    command_pattern = r"^/whoami$"
    command_help = "使用方法: /whoami - 查看你的用户信息"
    command_examples = ["/whoami"]
    enable_command = True

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行发送者信息查看命令"""
        try:
            user = self.message.message_info.user_info
            group = self.message.message_info.group_info

            info_lines = [
                "👤 你的身份信息",
                f"🆔 用户ID: {user.user_id}",
                f"📝 昵称: {user.user_nickname}",
                f"🏷️ 群名片: {user.user_cardname or '无'}",
                f"🌐 平台: {user.platform}",
            ]

            if group:
                info_lines.extend(
                    [
                        "",
                        "👥 当前群聊:",
                        f"🆔 群ID: {group.group_id}",
                        f"📝 群名: {group.group_name or '未知'}",
                    ]
                )
            else:
                info_lines.append("\n💬 当前在私聊中")

            return True, "\n".join(info_lines)

        except Exception as e:
            logger.error(f"{self.log_prefix} 获取发送者信息时出错: {e}")
            return False, f"获取发送者信息失败: {str(e)}"


@register_command
class ChatStreamInfoCommand(BaseCommand):
    """聊天流信息命令"""

    command_name = "streaminfo"
    command_description = "查看当前聊天流的详细信息"
    command_pattern = r"^/streaminfo$"
    command_help = "使用方法: /streaminfo - 查看当前聊天流信息"
    command_examples = ["/streaminfo"]
    enable_command = True

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行聊天流信息查看命令"""
        try:
            if not hasattr(self.message, "chat_stream") or not self.message.chat_stream:
                return False, "无法获取聊天流信息"

            chat_stream = self.message.chat_stream

            info_lines = [
                "🔄 聊天流信息",
                f"🆔 流ID: {chat_stream.stream_id}",
                f"🌐 平台: {chat_stream.platform}",
                f"⚡ 状态: {'激活' if chat_stream.is_active else '非激活'}",
            ]

            # 用户信息
            if chat_stream.user_info:
                info_lines.extend(
                    [
                        "",
                        "👤 关联用户:",
                        f"  ID: {chat_stream.user_info.user_id}",
                        f"  昵称: {chat_stream.user_info.user_nickname}",
                    ]
                )

            # 群信息
            if chat_stream.group_info:
                info_lines.extend(
                    [
                        "",
                        "👥 关联群聊:",
                        f"  群ID: {chat_stream.group_info.group_id}",
                        f"  群名: {chat_stream.group_info.group_name or '未知'}",
                    ]
                )
            else:
                info_lines.append("\n💬 类型: 私聊流")

            # 最近消息统计
            if hasattr(chat_stream, "last_messages"):
                msg_count = len(chat_stream.last_messages)
                info_lines.extend(
                    [
                        "",
                        f"📈 消息统计: 记录了 {msg_count} 条最近消息",
                    ]
                )

            return True, "\n".join(info_lines)

        except Exception as e:
            logger.error(f"{self.log_prefix} 获取聊天流信息时出错: {e}")
            return False, f"获取聊天流信息失败: {str(e)}"
