import enum
import time
from typing import List, Tuple, Optional
from src.common.logger_manager import get_logger
from src.plugins.moods.moods import MoodManager

logger = get_logger("mai_state")


# -- 状态定义 --
class MaiState(enum.Enum):
    """
    聊天状态:
    NORMAL_CHAT: 正常看手机：回复概率较高，会进行一些普通聊天和少量的专注水群
    FOCUSED_CHAT: 专注水群：回复概率极高，会进行专注水群和少量的普通聊天
    """
    NORMAL_CHAT = "正常看手机"
    FOCUSED_CHAT = "专心看手机"


class MaiStateInfo:
    def __init__(self):
        self.mai_status: MaiState = MaiState.NORMAL_CHAT
        self.mai_status_history: List[Tuple[MaiState, float]] = []  # 历史状态，包含 状态，时间戳
        self.last_status_change_time: float = time.time()  # 状态最后改变时间

        # Mood management is now part of MaiStateInfo
        self.mood_manager = MoodManager.get_instance()  # Use singleton instance

    def update_mai_status(self, new_status: MaiState) -> bool:
        """
        更新聊天状态。始终返回False，因为状态永远固定为NORMAL_CHAT

        Args:
            new_status: 新的 MaiState 状态。

        Returns:
            bool: 始终返回False，表示状态不会改变。
        """
        # 不再允许状态变化，始终保持NORMAL_CHAT
        logger.debug(f"尝试将状态更新为: {new_status.value}，但状态已固定为 {self.mai_status.value}")
        return False

    def get_mood_prompt(self) -> str:
        """获取当前的心情提示词"""
        # Delegate to the internal mood manager
        return self.mood_manager.get_prompt()

    def get_current_state(self) -> MaiState:
        """获取当前的 MaiState"""
        return MaiState.NORMAL_CHAT  # 始终返回NORMAL_CHAT


class MaiStateManager:
    """管理 Mai 的整体状态转换逻辑"""

    def __init__(self):
        pass

    @staticmethod
    def check_and_decide_next_state(current_state_info: MaiStateInfo) -> Optional[MaiState]:
        """
        状态检查函数。由于状态已固定为NORMAL_CHAT，此函数始终返回None。

        Args:
            current_state_info: 当前的 MaiStateInfo 实例。

        Returns:
            Optional[MaiState]: 始终返回None，表示没有状态变化。
        """
        # 不再需要检查或决定状态变化，状态已固定为NORMAL_CHAT
        logger.debug("当前在[正常看手机]状态，状态已固定，不会变化")
        return None  # 没有状态转换发生
