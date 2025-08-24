from typing import TYPE_CHECKING, List, Type

from src.common.logger import get_logger
from src.plugin_system.base.component_types import EventType, MaiMessages

if TYPE_CHECKING:
    from .base_events_handler import BaseEventHandler

logger = get_logger("base_event")
    
class BaseEvent:
    def __init__(self, event_type: EventType | str) -> None:
        self.event_type = event_type
        self.subscribers: List["BaseEventHandler"] = []

    def register_handler_to_event(self, handler: "BaseEventHandler") -> bool:
        if handler not in self.subscribers:
            self.subscribers.append(handler)
            return True
        logger.warning(f"Handler {handler.handler_name} 已经注册，不可多次注册")
        return False
    
    def remove_handler_from_event(self, handler_class: Type["BaseEventHandler"]) -> bool:
        for handler in self.subscribers:
            if isinstance(handler, handler_class):
                self.subscribers.remove(handler)
                return True
        logger.warning(f"Handler {handler_class.__name__} 未注册，无法移除")
        return False
    
    def trigger_event(self, message: MaiMessages):
        copied_message = message.deepcopy()
        for handler in self.subscribers:
            result = handler.execute(copied_message)
    
    # TODO: Unfinished Events Handler
            
        