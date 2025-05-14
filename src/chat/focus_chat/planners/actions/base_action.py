from abc import ABC, abstractmethod
from typing import Tuple
from src.common.logger_manager import get_logger

logger = get_logger("base_action")


class BaseAction(ABC):
    """动作处理基类接口

    所有具体的动作处理类都应该继承这个基类，并实现handle_action方法。
    """

    def __init__(self, action_name: str, action_data: dict, reasoning: str, cycle_timers: dict, thinking_id: str):
        """初始化动作处理器

        Args:
            action_name: 动作名称
            action_data: 动作数据
            reasoning: 执行该动作的理由
            cycle_timers: 计时器字典
            thinking_id: 思考ID
        """
        self.action_name = action_name
        self.action_data = action_data
        self.reasoning = reasoning
        self.cycle_timers = cycle_timers
        self.thinking_id = thinking_id

    @abstractmethod
    async def handle_action(self) -> Tuple[bool, str]:
        """处理动作的抽象方法，需要被子类实现

        Returns:
            Tuple[bool, str]: (是否执行成功, 回复文本)
        """
        pass
