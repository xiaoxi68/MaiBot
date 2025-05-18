from typing import List, Optional, Any
from src.chat.focus_chat.info.obs_info import ObsInfo
from src.chat.heart_flow.observation.observation import Observation
from src.chat.focus_chat.info.info_base import InfoBase
from src.chat.focus_chat.info.action_info import ActionInfo
from .base_processor import BaseProcessor
from src.common.logger_manager import get_logger
from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
from src.chat.heart_flow.observation.hfcloop_observation import HFCloopObservation
from src.chat.focus_chat.info.cycle_info import CycleInfo
from datetime import datetime
from typing import Dict
from src.chat.models.utils_model import LLMRequest
from src.config.config import global_config
import random

logger = get_logger("processor")


class ActionProcessor(BaseProcessor):
    """动作处理器

    用于处理Observation对象，将其转换为ObsInfo对象。
    """

    log_prefix = "聊天信息处理"

    def __init__(self):
        """初始化观察处理器"""
        super().__init__()
        # TODO: API-Adapter修改标记
        self.model_summary = LLMRequest(
            model=global_config.model.observation, temperature=0.7, max_tokens=300, request_type="chat_observation"
        )

    async def process_info(
        self,
        observations: Optional[List[Observation]] = None,
        running_memorys: Optional[List[Dict]] = None,
        **kwargs: Any,
    ) -> List[InfoBase]:
        """处理Observation对象

        Args:
            infos: InfoBase对象列表
            observations: 可选的Observation对象列表
            **kwargs: 其他可选参数

        Returns:
            List[InfoBase]: 处理后的ObsInfo实例列表
        """
        # print(f"observations: {observations}")
        processed_infos = []

        # 处理Observation对象
        if observations:
            for obs in observations:

                if isinstance(obs, HFCloopObservation):


                    # 创建动作信息
                    action_info = ActionInfo()
                    action_changes = await self.analyze_loop_actions(obs)
                    if action_changes["add"] or action_changes["remove"]:
                        action_info.set_action_changes(action_changes)
                        # 设置变更原因
                        reasons = []
                        if action_changes["add"]:
                            reasons.append(f"添加动作{action_changes['add']}因为检测到大量无回复")
                        if action_changes["remove"]:
                            reasons.append(f"移除动作{action_changes['remove']}因为检测到连续回复")
                        action_info.set_reason(" | ".join(reasons))
                        processed_infos.append(action_info)

        return processed_infos


    async def analyze_loop_actions(self, obs: HFCloopObservation) -> Dict[str, List[str]]:
        """分析最近的循环内容并决定动作的增减

        Returns:
            Dict[str, List[str]]: 包含要增加和删除的动作
                {
                    "add": ["action1", "action2"],
                    "remove": ["action3"]
                }
        """
        result = {"add": [], "remove": []}
        
        # 获取最近10次循环
        recent_cycles = obs.history_loop[-10:] if len(obs.history_loop) > 10 else obs.history_loop
        if not recent_cycles:
            return result
            
        # 统计no_reply的数量
        no_reply_count = 0
        reply_sequence = []  # 记录最近的动作序列
        
        for cycle in recent_cycles:
            action_type = cycle.loop_plan_info["action_result"]["action_type"]
            if action_type == "no_reply":
                no_reply_count += 1
            reply_sequence.append(action_type == "reply")
            
        # 检查no_reply比例
        if len(recent_cycles) >= 5 and (no_reply_count / len(recent_cycles)) >= 0.8:
            result["add"].append("exit_focus_chat")
            
        # 获取最近三次的reply状态
        last_three = reply_sequence[-3:] if len(reply_sequence) >= 3 else reply_sequence
        
        # 根据最近的reply情况决定是否移除reply动作
        if len(last_three) >= 3 and all(last_three):
            # 如果最近三次都是reply，直接移除
            result["remove"].append("reply")
        elif len(last_three) >= 2 and all(last_three[-2:]):
            # 如果最近两次都是reply，40%概率移除
            if random.random() < 0.4:
                result["remove"].append("reply")
        elif last_three and last_three[-1]:
            # 如果最近一次是reply，20%概率移除
            if random.random() < 0.2:
                result["remove"].append("reply")
                
        return result
