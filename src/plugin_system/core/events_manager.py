import asyncio
import contextlib
from typing import List, Dict, Optional, Type, Tuple

from src.chat.message_receive.message import MessageRecv
from src.common.logger import get_logger
from src.plugin_system.base.component_types import EventType, EventHandlerInfo, MaiMessages
from src.plugin_system.base.base_events_handler import BaseEventHandler
from .global_announcement_manager import global_announcement_manager

logger = get_logger("events_manager")


class EventsManager:
    def __init__(self):
        # 有权重的 events 订阅者注册表
        self._events_subscribers: Dict[EventType, List[BaseEventHandler]] = {event: [] for event in EventType}
        self._handler_mapping: Dict[str, Type[BaseEventHandler]] = {}  # 事件处理器映射表
        self._handler_tasks: Dict[str, List[asyncio.Task]] = {}  # 事件处理器正在处理的任务

    def register_event_subscriber(self, handler_info: EventHandlerInfo, handler_class: Type[BaseEventHandler]) -> bool:
        """注册事件处理器

        Args:
            handler_info (EventHandlerInfo): 事件处理器信息
            handler_class (Type[BaseEventHandler]): 事件处理器类

        Returns:
            bool: 是否注册成功
        """
        handler_name = handler_info.name

        if handler_name in self._handler_mapping:
            logger.warning(f"事件处理器 {handler_name} 已存在，跳过注册")
            return False

        if not issubclass(handler_class, BaseEventHandler):
            logger.error(f"类 {handler_class.__name__} 不是 BaseEventHandler 的子类")
            return False

        self._handler_mapping[handler_name] = handler_class
        return self._insert_event_handler(handler_class, handler_info)

    async def handle_mai_events(
        self,
        event_type: EventType,
        message: MessageRecv,
        llm_prompt: Optional[str] = None,
        llm_response: Optional[str] = None,
    ) -> bool:
        """处理 events"""
        from src.plugin_system.core import component_registry

        continue_flag = True
        transformed_message = self._transform_event_message(message, llm_prompt, llm_response)
        for handler in self._events_subscribers.get(event_type, []):
            if message.chat_stream and message.chat_stream.stream_id:
                stream_id = message.chat_stream.stream_id
                if handler.handler_name in global_announcement_manager.get_disabled_chat_event_handlers(stream_id):
                    continue
            handler.set_plugin_config(component_registry.get_plugin_config(handler.plugin_name) or {})
            if handler.intercept_message:
                try:
                    success, continue_processing, result = await handler.execute(transformed_message)
                    if not success:
                        logger.error(f"EventHandler {handler.handler_name} 执行失败: {result}")
                    else:
                        logger.debug(f"EventHandler {handler.handler_name} 执行成功: {result}")
                    continue_flag = continue_flag and continue_processing
                except Exception as e:
                    logger.error(f"EventHandler {handler.handler_name} 发生异常: {e}")
                    continue
            else:
                try:
                    handler_task = asyncio.create_task(handler.execute(transformed_message))
                    handler_task.add_done_callback(self._task_done_callback)
                    handler_task.set_name(f"{handler.plugin_name}-{handler.handler_name}")
                    if handler.handler_name not in self._handler_tasks:
                        self._handler_tasks[handler.handler_name] = []
                    self._handler_tasks[handler.handler_name].append(handler_task)
                except Exception as e:
                    logger.error(f"创建事件处理器任务 {handler.handler_name} 时发生异常: {e}")
                    continue
        return continue_flag

    def _insert_event_handler(self, handler_class: Type[BaseEventHandler], handler_info: EventHandlerInfo) -> bool:
        """插入事件处理器到对应的事件类型列表中并设置其插件配置"""
        if handler_class.event_type == EventType.UNKNOWN:
            logger.error(f"事件处理器 {handler_class.__name__} 的事件类型未知，无法注册")
            return False

        handler_instance = handler_class()
        handler_instance.set_plugin_name(handler_info.plugin_name or "unknown")
        self._events_subscribers[handler_class.event_type].append(handler_instance)
        self._events_subscribers[handler_class.event_type].sort(key=lambda x: x.weight, reverse=True)

        return True

    def _remove_event_handler_instance(self, handler_class: Type[BaseEventHandler]) -> bool:
        """从事件类型列表中移除事件处理器"""
        display_handler_name = handler_class.handler_name or handler_class.__name__
        if handler_class.event_type == EventType.UNKNOWN:
            logger.warning(f"事件处理器 {display_handler_name} 的事件类型未知，不存在于处理器列表中")
            return False

        handlers = self._events_subscribers[handler_class.event_type]
        for i, handler in enumerate(handlers):
            if isinstance(handler, handler_class):
                del handlers[i]
                logger.debug(f"事件处理器 {display_handler_name} 已移除")
                return True

        logger.warning(f"未找到事件处理器 {display_handler_name}，无法移除")
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
        if hasattr(message, "chat_stream") and message.chat_stream:
            transformed_message.stream_id = message.chat_stream.stream_id

        # 处理后文本
        transformed_message.plain_text = message.processed_plain_text

        # 基本信息
        if hasattr(message, "message_info") and message.message_info:
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

    def _task_done_callback(self, task: asyncio.Task[Tuple[bool, bool, str | None]]):
        """任务完成回调"""
        task_name = task.get_name() or "Unknown Task"
        try:
            success, _, result = task.result()  # 忽略是否继续的标志，因为消息本身未被拦截
            if success:
                logger.debug(f"事件处理任务 {task_name} 已成功完成: {result}")
            else:
                logger.error(f"事件处理任务 {task_name} 执行失败: {result}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"事件处理任务 {task_name} 发生异常: {e}")
        finally:
            with contextlib.suppress(ValueError, KeyError):
                self._handler_tasks[task_name].remove(task)

    async def cancel_handler_tasks(self, handler_name: str) -> None:
        tasks_to_be_cancelled = self._handler_tasks.get(handler_name, [])
        if remaining_tasks := [task for task in tasks_to_be_cancelled if not task.done()]:
            for task in remaining_tasks:
                task.cancel()
            try:
                await asyncio.wait_for(asyncio.gather(*remaining_tasks, return_exceptions=True), timeout=5)
                logger.info(f"已取消事件处理器 {handler_name} 的所有任务")
            except asyncio.TimeoutError:
                logger.warning(f"取消事件处理器 {handler_name} 的任务超时，开始强制取消")
            except Exception as e:
                logger.error(f"取消事件处理器 {handler_name} 的任务时发生异常: {e}")
        if handler_name in self._handler_tasks:
            del self._handler_tasks[handler_name]

    async def unregister_event_subscriber(self, handler_name: str) -> bool:
        """取消注册事件处理器"""
        if handler_name not in self._handler_mapping:
            logger.warning(f"事件处理器 {handler_name} 不存在，无法取消注册")
            return False

        await self.cancel_handler_tasks(handler_name)

        handler_class = self._handler_mapping.pop(handler_name)
        if not self._remove_event_handler_instance(handler_class):
            return False

        logger.info(f"事件处理器 {handler_name} 已成功取消注册")
        return True


events_manager = EventsManager()
