from typing import List, Optional, Any
from src.heart_flow.info.obs_info import ObsInfo
from src.heart_flow.observation.observation import Observation
from src.heart_flow.info.info_base import InfoBase
from .base_processor import BaseProcessor
from src.common.logger_manager import get_logger
from src.heart_flow.observation.chatting_observation import ChattingObservation
from src.heart_flow.observation.hfcloop_observation import HFCloopObservation
from src.heart_flow.info.cycle_info import CycleInfo

logger = get_logger("observation")


class ChattingInfoProcessor(BaseProcessor):
    """观察处理器

    用于处理Observation对象，将其转换为ObsInfo对象。
    """

    def __init__(self):
        """初始化观察处理器"""
        super().__init__()

    async def process_info(self, observations: Optional[List[Observation]] = None, **kwargs: Any) -> List[InfoBase]:
        """处理Observation对象

        Args:
            infos: InfoBase对象列表
            observations: 可选的Observation对象列表
            **kwargs: 其他可选参数

        Returns:
            List[InfoBase]: 处理后的ObsInfo实例列表
        """
        print(f"observations: {observations}")
        processed_infos = []

        # 处理Observation对象
        if observations:
            for obs in observations:
                print(f"obs: {obs}")
                if isinstance(obs, ChattingObservation):
                    obs_info = ObsInfo()

                    # 设置说话消息
                    if hasattr(obs, "talking_message_str"):
                        obs_info.set_talking_message(obs.talking_message_str)

                    # 设置截断后的说话消息
                    if hasattr(obs, "talking_message_str_truncate"):
                        obs_info.set_talking_message_str_truncate(obs.talking_message_str_truncate)

                    # 设置聊天类型
                    is_group_chat = obs.is_group_chat
                    if is_group_chat:
                        chat_type = "group"
                    else:
                        chat_type = "private"
                        obs_info.set_chat_target(obs.chat_target_info.get("person_name", "某人"))
                    obs_info.set_chat_type(chat_type)

                    logger.debug(f"聊天信息处理器处理后的信息: {obs_info}")

                    processed_infos.append(obs_info)
                if isinstance(obs, HFCloopObservation):
                    obs_info = CycleInfo()
                    obs_info.set_observe_info(obs.observe_info)
                    processed_infos.append(obs_info)

        return processed_infos
