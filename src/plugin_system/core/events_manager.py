import asyncio
from typing import List, Dict, Optional, Type

from src.chat.message_receive.message import MessageRecv
from src.common.logger import get_logger
from src.plugin_system.base.component_types import EventType, EventHandlerInfo, MaiMessages
from src.plugin_system.base.base_events_handler import BaseEventHandler

logger = get_logger("events_manager")


class EventsManager:
    def __init__(self):
        # 有权重的 events 订阅者注册表
        self.events_subscribers: Dict[EventType, List[BaseEventHandler]] = {event: [] for event in EventType}
        self.handler_mapping: Dict[str, Type[BaseEventHandler]] = {}  # 事件处理器映射表

    def register_event_subscriber(self, handler_info: EventHandlerInfo, handler_class: Type[BaseEventHandler]) -> bool:
        """注册事件处理器

        Args:
            handler_info (EventHandlerInfo): 事件处理器信息
            handler_class (Type[BaseEventHandler]): 事件处理器类

        Returns:
            bool: 是否注册成功
        """
        handler_name = handler_info.name
        plugin_name = getattr(handler_info, "plugin_name", "unknown")

        namespace_name = f"{plugin_name}.{handler_name}"
        if namespace_name in self.handler_mapping:
            logger.warning(f"事件处理器 {namespace_name} 已存在，跳过注册")
            return False

        if not issubclass(handler_class, BaseEventHandler):
            logger.error(f"类 {handler_class.__name__} 不是 BaseEventHandler 的子类")
            return False

        self.handler_mapping[namespace_name] = handler_class

        return self._insert_event_handler(handler_class)

    async def handler_mai_events(
        self,
        event_type: EventType,
        message: MessageRecv,
        llm_prompt: Optional[str] = None,
        llm_response: Optional[str] = None,
    ) -> None:
        """处理 events"""
        transformed_message = self._transform_event_message(message, llm_prompt, llm_response)
        for handler in self.events_subscribers.get(event_type, []):
            if handler.intercept_message:
                await handler.execute(transformed_message)
            else:
                asyncio.create_task(handler.execute(transformed_message))

    def _insert_event_handler(self, handler_class: Type[BaseEventHandler]) -> bool:
        """插入事件处理器到对应的事件类型列表中"""
        if handler_class.event_type == EventType.UNKNOWN:
            logger.error(f"事件处理器 {handler_class.__name__} 的事件类型未知，无法注册")
            return False

        self.events_subscribers[handler_class.event_type].append(handler_class())
        self.events_subscribers[handler_class.event_type].sort(key=lambda x: x.weight, reverse=True)

        return True

    def _remove_event_handler(self, handler_class: Type[BaseEventHandler]) -> bool:
        """从事件类型列表中移除事件处理器"""
        if handler_class.event_type == EventType.UNKNOWN:
            logger.warning(f"事件处理器 {handler_class.__name__} 的事件类型未知，不存在于处理器列表中")
            return False

        handlers = self.events_subscribers[handler_class.event_type]
        for i, handler in enumerate(handlers):
            if isinstance(handler, handler_class):
                del handlers[i]
                logger.debug(f"事件处理器 {handler_class.__name__} 已移除")
                return True

        logger.warning(f"未找到事件处理器 {handler_class.__name__}，无法移除")
        return False

    def _transform_event_message(
        self, message: MessageRecv, llm_prompt: Optional[str] = None, llm_response: Optional[str] = None
    ) -> MaiMessages:
        """转换事件消息格式"""
        # 直接赋值部分内容
        transformed_message = MaiMessages(
            llm_prompt=llm_prompt,
            llm_response=llm_response,
            raw_message=message.raw_message,
            additional_data=message.message_info.additional_config or {},
        )

        # 消息段处理
        if message.message_segment.type == "seglist":
            transformed_message.message_segments = list(message.message_segment.data)  # type: ignore
        else:
            transformed_message.message_segments = [message.message_segment]

        # stream_id 处理
        if hasattr(message, "chat_stream"):
            transformed_message.stream_id = message.chat_stream.stream_id

        # 处理后文本
        transformed_message.plain_text = message.processed_plain_text

        # 基本信息
        if message.message_info.platform:
            transformed_message.message_base_info["platform"] = message.message_info.platform
        if message.message_info.group_info:
            transformed_message.is_group_message = True
            transformed_message.message_base_info.update(
                {
                    "group_id": message.message_info.group_info.group_id,
                    "group_name": message.message_info.group_info.group_name,
                }
            )
        if message.message_info.user_info:
            if not transformed_message.is_group_message:
                transformed_message.is_private_message = True
            transformed_message.message_base_info.update(
                {
                    "user_id": message.message_info.user_info.user_id,
                    "user_cardname": message.message_info.user_info.user_cardname,  # 用户群昵称
                    "user_nickname": message.message_info.user_info.user_nickname,  # 用户昵称（用户名）
                }
            )

        return transformed_message


events_manager = EventsManager()
