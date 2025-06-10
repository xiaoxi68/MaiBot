import traceback
import time
from typing import List, Dict, Any
from src.common.logger_manager import get_logger
from src.chat.focus_chat.hfc_utils import create_empty_anchor_message

# 以下为类型注解需要
from src.chat.message_receive.chat_stream import ChatStream, chat_manager
from src.chat.focus_chat.info.obs_info import ObsInfo

# 新增导入
from src.chat.focus_chat.heartFC_sender import HeartFCSender
from src.chat.message_receive.message import MessageSending
from maim_message import Seg, UserInfo
from src.config.config import global_config

logger = get_logger("message_api")


class MessageAPI:
    """消息API模块

    提供了发送消息、获取消息历史等功能
    """

    async def send_message_to_target(
        self,
        message_type: str,
        content: str,
        platform: str,
        target_id: str,
        is_group: bool = True,
        display_message: str = "",
    ) -> bool:
        """直接向指定目标发送消息

        Args:
            message_type: 消息类型，如"text"、"image"、"emoji"等
            content: 消息内容
            platform: 目标平台，如"qq"
            target_id: 目标ID（群ID或用户ID）
            is_group: 是否为群聊，True为群聊，False为私聊
            display_message: 显示消息（可选）

        Returns:
            bool: 是否发送成功
        """
        try:
            # 构建目标聊天流ID
            if is_group:
                # 群聊：从数据库查找对应的聊天流
                target_stream = None
                for _, stream in chat_manager.streams.items():
                    if (
                        stream.group_info
                        and str(stream.group_info.group_id) == str(target_id)
                        and stream.platform == platform
                    ):
                        target_stream = stream
                        break

                if not target_stream:
                    logger.error(f"{getattr(self, 'log_prefix', '')} 未找到群ID为 {target_id} 的聊天流")
                    return False
            else:
                # 私聊：从数据库查找对应的聊天流
                target_stream = None
                for _, stream in chat_manager.streams.items():
                    if (
                        not stream.group_info
                        and str(stream.user_info.user_id) == str(target_id)
                        and stream.platform == platform
                    ):
                        target_stream = stream
                        break

                if not target_stream:
                    logger.error(f"{getattr(self, 'log_prefix', '')} 未找到用户ID为 {target_id} 的私聊流")
                    return False

            # 创建HeartFCSender实例
            heart_fc_sender = HeartFCSender()

            # 生成消息ID和thinking_id
            current_time = time.time()
            message_id = f"plugin_msg_{int(current_time * 1000)}"

            # 构建机器人用户信息
            bot_user_info = UserInfo(
                user_id=global_config.bot.qq_account,
                user_nickname=global_config.bot.nickname,
                platform=platform,
            )

            # 创建消息段
            message_segment = Seg(type=message_type, data=content)

            # 创建空锚点消息（用于回复）
            anchor_message = await create_empty_anchor_message(platform, target_stream.group_info, target_stream)

            # 构建发送消息对象
            bot_message = MessageSending(
                message_id=message_id,
                chat_stream=target_stream,
                bot_user_info=bot_user_info,
                sender_info=target_stream.user_info,  # 目标用户信息
                message_segment=message_segment,
                display_message=display_message,
                reply=anchor_message,
                is_head=True,
                is_emoji=(message_type == "emoji"),
                thinking_start_time=current_time,
            )

            # 发送消息
            sent_msg = await heart_fc_sender.send_message(bot_message, has_thinking=True, typing=False, set_reply=False)

            if sent_msg:
                logger.info(f"{getattr(self, 'log_prefix', '')} 成功发送消息到 {platform}:{target_id}")
                return True
            else:
                logger.error(f"{getattr(self, 'log_prefix', '')} 发送消息失败")
                return False

        except Exception as e:
            logger.error(f"{getattr(self, 'log_prefix', '')} 向目标发送消息时出错: {e}")
            traceback.print_exc()
            return False

    async def send_text_to_group(self, text: str, group_id: str, platform: str = "qq") -> bool:
        """便捷方法：向指定群聊发送文本消息

        Args:
            text: 要发送的文本内容
            group_id: 群聊ID
            platform: 平台，默认为"qq"

        Returns:
            bool: 是否发送成功
        """
        return await self.send_message_to_target(
            message_type="text", content=text, platform=platform, target_id=group_id, is_group=True
        )

    async def send_text_to_user(self, text: str, user_id: str, platform: str = "qq") -> bool:
        """便捷方法：向指定用户发送私聊文本消息

        Args:
            text: 要发送的文本内容
            user_id: 用户ID
            platform: 平台，默认为"qq"

        Returns:
            bool: 是否发送成功
        """
        return await self.send_message_to_target(
            message_type="text", content=text, platform=platform, target_id=user_id, is_group=False
        )



    def get_chat_type(self) -> str:
        """获取当前聊天类型

        Returns:
            str: 聊天类型 ("group" 或 "private")
        """
        services = getattr(self, "_services", {})
        chat_stream: ChatStream = services.get("chat_stream")
        if chat_stream and hasattr(chat_stream, "group_info"):
            return "group" if chat_stream.group_info else "private"
        return "unknown"

    def get_recent_messages(self, count: int = 5) -> List[Dict[str, Any]]:
        """获取最近的消息

        Args:
            count: 要获取的消息数量

        Returns:
            List[Dict]: 消息列表，每个消息包含发送者、内容等信息
        """
        messages = []
        services = getattr(self, "_services", {})
        observations = services.get("observations", [])

        if observations and len(observations) > 0:
            obs = observations[0]
            if hasattr(obs, "get_talking_message"):
                obs: ObsInfo
                raw_messages = obs.get_talking_message()
                # 转换为简化格式
                for msg in raw_messages[-count:]:
                    simple_msg = {
                        "sender": msg.get("sender", "未知"),
                        "content": msg.get("content", ""),
                        "timestamp": msg.get("timestamp", 0),
                    }
                    messages.append(simple_msg)

        return messages
