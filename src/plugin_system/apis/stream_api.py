from typing import Optional, List, Dict, Any, Tuple
from src.common.logger_manager import get_logger
from src.chat.message_receive.chat_stream import ChatManager, ChatStream
from src.chat.focus_chat.hfc_utils import parse_thinking_id_to_timestamp
import asyncio

logger = get_logger("stream_api")


class StreamAPI:
    """聊天流API模块

    提供了获取聊天流、通过群ID查找聊天流等功能
    """

    def get_chat_stream_by_group_id(self, group_id: str, platform: str = "qq") -> Optional[ChatStream]:
        """通过QQ群ID获取聊天流

        Args:
            group_id: QQ群ID
            platform: 平台标识，默认为"qq"

        Returns:
            Optional[ChatStream]: 找到的聊天流对象，如果未找到则返回None
        """
        try:
            chat_manager = ChatManager()

            # 遍历所有已加载的聊天流，查找匹配的群ID
            for stream_id, stream in chat_manager.streams.items():
                if (
                    stream.group_info
                    and str(stream.group_info.group_id) == str(group_id)
                    and stream.platform == platform
                ):
                    logger.info(f"{self.log_prefix} 通过群ID {group_id} 找到聊天流: {stream_id}")
                    return stream

            logger.warning(f"{self.log_prefix} 未找到群ID为 {group_id} 的聊天流")
            return None

        except Exception as e:
            logger.error(f"{self.log_prefix} 通过群ID获取聊天流时出错: {e}")
            return None

    def get_all_group_chat_streams(self, platform: str = "qq") -> List[ChatStream]:
        """获取所有群聊的聊天流

        Args:
            platform: 平台标识，默认为"qq"

        Returns:
            List[ChatStream]: 所有群聊的聊天流列表
        """
        try:
            chat_manager = ChatManager()
            group_streams = []

            for stream in chat_manager.streams.values():
                if stream.group_info and stream.platform == platform:
                    group_streams.append(stream)

            logger.info(f"{self.log_prefix} 找到 {len(group_streams)} 个群聊聊天流")
            return group_streams

        except Exception as e:
            logger.error(f"{self.log_prefix} 获取所有群聊聊天流时出错: {e}")
            return []

    def get_chat_stream_by_user_id(self, user_id: str, platform: str = "qq") -> Optional[ChatStream]:
        """通过用户ID获取私聊聊天流

        Args:
            user_id: 用户ID
            platform: 平台标识，默认为"qq"

        Returns:
            Optional[ChatStream]: 找到的私聊聊天流对象，如果未找到则返回None
        """
        try:
            chat_manager = ChatManager()

            # 遍历所有已加载的聊天流，查找匹配的用户ID（私聊）
            for stream_id, stream in chat_manager.streams.items():
                if (
                    not stream.group_info  # 私聊没有群信息
                    and stream.user_info
                    and str(stream.user_info.user_id) == str(user_id)
                    and stream.platform == platform
                ):
                    logger.info(f"{self.log_prefix} 通过用户ID {user_id} 找到私聊聊天流: {stream_id}")
                    return stream

            logger.warning(f"{self.log_prefix} 未找到用户ID为 {user_id} 的私聊聊天流")
            return None

        except Exception as e:
            logger.error(f"{self.log_prefix} 通过用户ID获取私聊聊天流时出错: {e}")
            return None

    def get_chat_streams_info(self) -> List[Dict[str, Any]]:
        """获取所有聊天流的基本信息

        Returns:
            List[Dict[str, Any]]: 包含聊天流基本信息的字典列表
        """
        try:
            chat_manager = ChatManager()
            streams_info = []

            for stream_id, stream in chat_manager.streams.items():
                info = {
                    "stream_id": stream_id,
                    "platform": stream.platform,
                    "chat_type": "group" if stream.group_info else "private",
                    "create_time": stream.create_time,
                    "last_active_time": stream.last_active_time,
                }

                if stream.group_info:
                    info.update({"group_id": stream.group_info.group_id, "group_name": stream.group_info.group_name})

                if stream.user_info:
                    info.update({"user_id": stream.user_info.user_id, "user_nickname": stream.user_info.user_nickname})

                streams_info.append(info)

            logger.info(f"{self.log_prefix} 获取到 {len(streams_info)} 个聊天流信息")
            return streams_info

        except Exception as e:
            logger.error(f"{self.log_prefix} 获取聊天流信息时出错: {e}")
            return []

    async def get_chat_stream_by_group_id_async(self, group_id: str, platform: str = "qq") -> Optional[ChatStream]:
        """异步通过QQ群ID获取聊天流（包括从数据库搜索）

        Args:
            group_id: QQ群ID
            platform: 平台标识，默认为"qq"

        Returns:
            Optional[ChatStream]: 找到的聊天流对象，如果未找到则返回None
        """
        try:
            # 首先尝试从内存中查找
            stream = self.get_chat_stream_by_group_id(group_id, platform)
            if stream:
                return stream

            # 如果内存中没有，尝试从数据库加载所有聊天流后再查找
            chat_manager = ChatManager()
            await chat_manager.load_all_streams()

            # 再次尝试从内存中查找
            stream = self.get_chat_stream_by_group_id(group_id, platform)
            return stream

        except Exception as e:
            logger.error(f"{self.log_prefix} 异步通过群ID获取聊天流时出错: {e}")
            return None

    async def wait_for_new_message(self, timeout: int = 1200) -> Tuple[bool, str]:
        """等待新消息或超时

        Args:
            timeout: 超时时间（秒），默认1200秒

        Returns:
            Tuple[bool, str]: (是否收到新消息, 空字符串)
        """
        try:
            # 获取必要的服务对象
            observations = self.get_service("observations")
            if not observations:
                logger.warning(f"{self.log_prefix} 无法获取observations服务，无法等待新消息")
                return False, ""

            # 获取第一个观察对象（通常是ChattingObservation）
            observation = observations[0] if observations else None
            if not observation:
                logger.warning(f"{self.log_prefix} 无观察对象，无法等待新消息")
                return False, ""

            # 从action上下文获取thinking_id
            thinking_id = self.get_action_context("thinking_id")
            if not thinking_id:
                logger.warning(f"{self.log_prefix} 无thinking_id，无法等待新消息")
                return False, ""

            logger.info(f"{self.log_prefix} 开始等待新消息... (超时: {timeout}秒)")

            wait_start_time = asyncio.get_event_loop().time()
            while True:
                # 检查关闭标志
                shutting_down = self.get_action_context("shutting_down", False)
                if shutting_down:
                    logger.info(f"{self.log_prefix} 等待新消息时检测到关闭信号，中断等待")
                    return False, ""

                # 检查新消息
                thinking_id_timestamp = parse_thinking_id_to_timestamp(thinking_id)
                if await observation.has_new_messages_since(thinking_id_timestamp):
                    logger.info(f"{self.log_prefix} 检测到新消息")
                    return True, ""

                # 检查超时
                if asyncio.get_event_loop().time() - wait_start_time > timeout:
                    logger.warning(f"{self.log_prefix} 等待新消息超时({timeout}秒)")
                    return False, ""

                # 短暂休眠
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info(f"{self.log_prefix} 等待新消息被中断 (CancelledError)")
            return False, ""
        except Exception as e:
            logger.error(f"{self.log_prefix} 等待新消息时发生错误: {e}")
            return False, f"等待新消息失败: {str(e)}"
