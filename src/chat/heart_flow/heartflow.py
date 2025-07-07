from src.chat.heart_flow.sub_heartflow import SubHeartflow, ChatState
from src.common.logger import get_logger
from typing import Any, Optional
from typing import Dict
from src.chat.message_receive.chat_stream import get_chat_manager

logger = get_logger("heartflow")


class Heartflow:
    """主心流协调器，负责初始化并协调聊天"""

    def __init__(self):
        self.subheartflows: Dict[Any, "SubHeartflow"] = {}

    async def get_or_create_subheartflow(self, subheartflow_id: Any) -> Optional["SubHeartflow"]:
        """获取或创建一个新的SubHeartflow实例"""
        if subheartflow_id in self.subheartflows:
            subflow = self.subheartflows.get(subheartflow_id)
            if subflow:
                return subflow

        try:
            new_subflow = SubHeartflow(
                subheartflow_id,
            )

            await new_subflow.initialize()

            # 注册子心流
            self.subheartflows[subheartflow_id] = new_subflow
            heartflow_name = get_chat_manager().get_stream_name(subheartflow_id) or subheartflow_id
            logger.info(f"[{heartflow_name}] 开始接收消息")

            return new_subflow
        except Exception as e:
            logger.error(f"创建子心流 {subheartflow_id} 失败: {e}", exc_info=True)
            return None

    async def force_change_subheartflow_status(self, subheartflow_id: str, status: ChatState) -> None:
        """强制改变子心流的状态"""
        # 这里的 message 是可选的，可能是一个消息对象，也可能是其他类型的数据
        return await self.force_change_state(subheartflow_id, status)

    async def force_change_state(self, subflow_id: Any, target_state: ChatState) -> bool:
        """强制改变指定子心流的状态"""
        subflow = self.subheartflows.get(subflow_id)
        if not subflow:
            logger.warning(f"[强制状态转换]尝试转换不存在的子心流{subflow_id} 到 {target_state.value}")
            return False
        await subflow.change_chat_state(target_state)
        logger.info(f"[强制状态转换]子心流 {subflow_id} 已转换到 {target_state.value}")
        return True


heartflow = Heartflow()
