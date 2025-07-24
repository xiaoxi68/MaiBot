import traceback
from typing import Any, Optional, Dict

from src.common.logger import get_logger
from src.chat.heart_flow.sub_heartflow import SubHeartflow
from src.chat.message_receive.chat_stream import get_chat_manager

logger = get_logger("heartflow")


class Heartflow:
    """主心流协调器，负责初始化并协调聊天"""

    def __init__(self):
        self.subheartflows: Dict[Any, "SubHeartflow"] = {}

    async def get_or_create_subheartflow(self, subheartflow_id: Any) -> Optional["SubHeartflow"]:
        """获取或创建一个新的SubHeartflow实例"""
        if subheartflow_id in self.subheartflows:
            if subflow := self.subheartflows.get(subheartflow_id):
                return subflow

        try:
            new_subflow = SubHeartflow(subheartflow_id)

            await new_subflow.initialize()

            # 注册子心流
            self.subheartflows[subheartflow_id] = new_subflow
            heartflow_name = get_chat_manager().get_stream_name(subheartflow_id) or subheartflow_id
            logger.info(f"[{heartflow_name}] 开始接收消息")

            return new_subflow
        except Exception as e:
            logger.error(f"创建子心流 {subheartflow_id} 失败: {e}", exc_info=True)
            traceback.print_exc()
            return None


heartflow = Heartflow()
