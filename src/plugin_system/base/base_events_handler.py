from abc import ABC, abstractmethod
from typing import Tuple, Optional

from src.common.logger import get_logger
from .component_types import MaiMessages, EventType

logger = get_logger("base_event_handler")


class BaseEventHandler(ABC):
    """事件处理器基类

    所有事件处理器都应该继承这个基类，提供事件处理的基本接口
    """

    event_type: EventType = EventType.UNKNOWN  # 事件类型，默认为未知
    handler_name: str = ""
    handler_description: str = ""
    weight: int = 0  # 权重，数值越大优先级越高
    intercept_message: bool = False  # 是否拦截消息，默认为否

    def __init__(self):
        self.log_prefix = "[EventHandler]"
        if self.event_type == EventType.UNKNOWN:
            raise NotImplementedError("事件处理器必须指定 event_type")

    @abstractmethod
    async def execute(self, message: MaiMessages) -> Tuple[bool, Optional[str]]:
        """执行事件处理的抽象方法，子类必须实现

        Returns:
            Tuple[bool, Optional[str]]: (是否执行成功, 可选的返回消息)
        """
        raise NotImplementedError("子类必须实现 execute 方法")
