"""
聊天API模块

专门负责聊天信息的查询和管理，采用标准Python包设计模式
使用方式：
    from src.plugin_system.apis import chat_api
    streams = chat_api.get_all_group_streams()
    chat_type = chat_api.get_stream_type(stream)

或者：
    from src.plugin_system.apis.chat_api import ChatManager as chat
    streams = chat.get_all_group_streams()
"""

from typing import List, Dict, Any, Optional
from src.common.logger import get_logger

# 导入依赖
from src.chat.message_receive.chat_stream import ChatStream, get_chat_manager
from src.chat.focus_chat.info.obs_info import ObsInfo

logger = get_logger("chat_api")


class ChatManager:
    """聊天管理器 - 专门负责聊天信息的查询和管理"""

    @staticmethod
    def get_all_streams(platform: str = "qq") -> List[ChatStream]:
        """获取所有聊天流

        Args:
            platform: 平台筛选，默认为"qq"

        Returns:
            List[ChatStream]: 聊天流列表
        """
        streams = []
        try:
            for _, stream in get_chat_manager().streams.items():
                if stream.platform == platform:
                    streams.append(stream)
            logger.debug(f"[ChatAPI] 获取到 {len(streams)} 个 {platform} 平台的聊天流")
        except Exception as e:
            logger.error(f"[ChatAPI] 获取聊天流失败: {e}")
        return streams

    @staticmethod
    def get_group_streams(platform: str = "qq") -> List[ChatStream]:
        """获取所有群聊聊天流

        Args:
            platform: 平台筛选，默认为"qq"

        Returns:
            List[ChatStream]: 群聊聊天流列表
        """
        streams = []
        try:
            for _, stream in get_chat_manager().streams.items():
                if stream.platform == platform and stream.group_info:
                    streams.append(stream)
            logger.debug(f"[ChatAPI] 获取到 {len(streams)} 个 {platform} 平台的群聊流")
        except Exception as e:
            logger.error(f"[ChatAPI] 获取群聊流失败: {e}")
        return streams

    @staticmethod
    def get_private_streams(platform: str = "qq") -> List[ChatStream]:
        """获取所有私聊聊天流

        Args:
            platform: 平台筛选，默认为"qq"

        Returns:
            List[ChatStream]: 私聊聊天流列表
        """
        streams = []
        try:
            for _, stream in get_chat_manager().streams.items():
                if stream.platform == platform and not stream.group_info:
                    streams.append(stream)
            logger.debug(f"[ChatAPI] 获取到 {len(streams)} 个 {platform} 平台的私聊流")
        except Exception as e:
            logger.error(f"[ChatAPI] 获取私聊流失败: {e}")
        return streams

    @staticmethod
    def get_stream_by_group_id(group_id: str, platform: str = "qq") -> Optional[ChatStream]:
        """根据群ID获取聊天流

        Args:
            group_id: 群聊ID
            platform: 平台，默认为"qq"

        Returns:
            Optional[ChatStream]: 聊天流对象，如果未找到返回None
        """
        try:
            for _, stream in get_chat_manager().streams.items():
                if (
                    stream.group_info
                    and str(stream.group_info.group_id) == str(group_id)
                    and stream.platform == platform
                ):
                    logger.debug(f"[ChatAPI] 找到群ID {group_id} 的聊天流")
                    return stream
            logger.warning(f"[ChatAPI] 未找到群ID {group_id} 的聊天流")
        except Exception as e:
            logger.error(f"[ChatAPI] 查找群聊流失败: {e}")
        return None

    @staticmethod
    def get_stream_by_user_id(user_id: str, platform: str = "qq") -> Optional[ChatStream]:
        """根据用户ID获取私聊流

        Args:
            user_id: 用户ID
            platform: 平台，默认为"qq"

        Returns:
            Optional[ChatStream]: 聊天流对象，如果未找到返回None
        """
        try:
            for _, stream in get_chat_manager().streams.items():
                if (
                    not stream.group_info
                    and str(stream.user_info.user_id) == str(user_id)
                    and stream.platform == platform
                ):
                    logger.debug(f"[ChatAPI] 找到用户ID {user_id} 的私聊流")
                    return stream
            logger.warning(f"[ChatAPI] 未找到用户ID {user_id} 的私聊流")
        except Exception as e:
            logger.error(f"[ChatAPI] 查找私聊流失败: {e}")
        return None

    @staticmethod
    def get_stream_type(chat_stream: ChatStream) -> str:
        """获取聊天流类型

        Args:
            chat_stream: 聊天流对象

        Returns:
            str: 聊天类型 ("group", "private", "unknown")
        """
        if not chat_stream:
            return "unknown"

        if hasattr(chat_stream, "group_info"):
            return "group" if chat_stream.group_info else "private"
        return "unknown"

    @staticmethod
    def get_stream_info(chat_stream: ChatStream) -> Dict[str, Any]:
        """获取聊天流详细信息

        Args:
            chat_stream: 聊天流对象

        Returns:
            Dict[str, Any]: 聊天流信息字典
        """
        if not chat_stream:
            return {}

        try:
            info = {
                "stream_id": chat_stream.stream_id,
                "platform": chat_stream.platform,
                "type": ChatManager.get_stream_type(chat_stream),
            }

            if chat_stream.group_info:
                info.update(
                    {
                        "group_id": chat_stream.group_info.group_id,
                        "group_name": getattr(chat_stream.group_info, "group_name", "未知群聊"),
                    }
                )

            if chat_stream.user_info:
                info.update(
                    {
                        "user_id": chat_stream.user_info.user_id,
                        "user_name": chat_stream.user_info.user_nickname,
                    }
                )

            return info
        except Exception as e:
            logger.error(f"[ChatAPI] 获取聊天流信息失败: {e}")
            return {}

    @staticmethod
    def get_recent_messages_from_obs(observations: List[Any], count: int = 5) -> List[Dict[str, Any]]:
        """从观察对象获取最近的消息

        Args:
            observations: 观察对象列表
            count: 要获取的消息数量

        Returns:
            List[Dict]: 消息列表，每个消息包含发送者、内容等信息
        """
        messages = []

        try:
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
            logger.debug(f"[ChatAPI] 获取到 {len(messages)} 条最近消息")
        except Exception as e:
            logger.error(f"[ChatAPI] 获取最近消息失败: {e}")

        return messages

    @staticmethod
    def get_streams_summary() -> Dict[str, int]:
        """获取聊天流统计摘要

        Returns:
            Dict[str, int]: 包含各种统计信息的字典
        """
        try:
            all_streams = ChatManager.get_all_streams()
            group_streams = ChatManager.get_group_streams()
            private_streams = ChatManager.get_private_streams()

            summary = {
                "total_streams": len(all_streams),
                "group_streams": len(group_streams),
                "private_streams": len(private_streams),
                "qq_streams": len([s for s in all_streams if s.platform == "qq"]),
            }

            logger.debug(f"[ChatAPI] 聊天流统计: {summary}")
            return summary
        except Exception as e:
            logger.error(f"[ChatAPI] 获取聊天流统计失败: {e}")
            return {"total_streams": 0, "group_streams": 0, "private_streams": 0, "qq_streams": 0}


# =============================================================================
# 模块级别的便捷函数 - 类似 requests.get(), requests.post() 的设计
# =============================================================================


def get_all_streams(platform: str = "qq") -> List[ChatStream]:
    """获取所有聊天流的便捷函数"""
    return ChatManager.get_all_streams(platform)


def get_group_streams(platform: str = "qq") -> List[ChatStream]:
    """获取群聊聊天流的便捷函数"""
    return ChatManager.get_group_streams(platform)


def get_private_streams(platform: str = "qq") -> List[ChatStream]:
    """获取私聊聊天流的便捷函数"""
    return ChatManager.get_private_streams(platform)


def get_stream_by_group_id(group_id: str, platform: str = "qq") -> Optional[ChatStream]:
    """根据群ID获取聊天流的便捷函数"""
    return ChatManager.get_stream_by_group_id(group_id, platform)


def get_stream_by_user_id(user_id: str, platform: str = "qq") -> Optional[ChatStream]:
    """根据用户ID获取私聊流的便捷函数"""
    return ChatManager.get_stream_by_user_id(user_id, platform)


def get_stream_type(chat_stream: ChatStream) -> str:
    """获取聊天流类型的便捷函数"""
    return ChatManager.get_stream_type(chat_stream)


def get_stream_info(chat_stream: ChatStream) -> Dict[str, Any]:
    """获取聊天流信息的便捷函数"""
    return ChatManager.get_stream_info(chat_stream)


def get_streams_summary() -> Dict[str, int]:
    """获取聊天流统计摘要的便捷函数"""
    return ChatManager.get_streams_summary()
