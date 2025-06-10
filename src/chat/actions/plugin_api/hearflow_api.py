from typing import Optional, List, Any
from src.common.logger_manager import get_logger
from src.chat.heart_flow.heartflow import heartflow
from src.chat.heart_flow.sub_heartflow import SubHeartflow, ChatState

logger = get_logger("hearflow_api")


class HearflowAPI:
    """心流API模块

    提供与心流和子心流相关的操作接口
    """

    async def get_sub_hearflow_by_chat_id(self, chat_id: str) -> Optional[SubHeartflow]:
        """根据chat_id获取指定的sub_hearflow实例

        Args:
            chat_id: 聊天ID，与sub_hearflow的subheartflow_id相同

        Returns:
            Optional[SubHeartflow]: sub_hearflow实例，如果不存在则返回None
        """
        try:
            # 直接从subheartflow_manager获取已存在的子心流
            # 使用锁来确保线程安全
            async with heartflow.subheartflow_manager._lock:
                subflow = heartflow.subheartflow_manager.subheartflows.get(chat_id)
                if subflow and not subflow.should_stop:
                    logger.debug(f"{self.log_prefix} 成功获取子心流实例: {chat_id}")
                    return subflow
                else:
                    logger.debug(f"{self.log_prefix} 子心流不存在或已停止: {chat_id}")
                    return None
        except Exception as e:
            logger.error(f"{self.log_prefix} 获取子心流实例时出错: {e}")
            return None

    def get_all_sub_hearflow_ids(self) -> List[str]:
        """获取所有子心流的ID列表

        Returns:
            List[str]: 所有子心流的ID列表
        """
        try:
            all_subflows = heartflow.subheartflow_manager.get_all_subheartflows()
            chat_ids = [subflow.chat_id for subflow in all_subflows if not subflow.should_stop]
            logger.debug(f"{self.log_prefix} 获取到 {len(chat_ids)} 个活跃的子心流ID")
            return chat_ids
        except Exception as e:
            logger.error(f"{self.log_prefix} 获取子心流ID列表时出错: {e}")
            return []

    def get_all_sub_hearflows(self) -> List[SubHeartflow]:
        """获取所有子心流实例

        Returns:
            List[SubHeartflow]: 所有活跃的子心流实例列表
        """
        try:
            all_subflows = heartflow.subheartflow_manager.get_all_subheartflows()
            active_subflows = [subflow for subflow in all_subflows if not subflow.should_stop]
            logger.debug(f"{self.log_prefix} 获取到 {len(active_subflows)} 个活跃的子心流实例")
            return active_subflows
        except Exception as e:
            logger.error(f"{self.log_prefix} 获取子心流实例列表时出错: {e}")
            return []

    async def get_sub_hearflow_chat_state(self, chat_id: str) -> Optional[ChatState]:
        """获取指定子心流的聊天状态

        Args:
            chat_id: 聊天ID

        Returns:
            Optional[ChatState]: 聊天状态，如果子心流不存在则返回None
        """
        try:
            subflow = await self.get_sub_hearflow_by_chat_id(chat_id)
            if subflow:
                return subflow.chat_state.chat_status
            return None
        except Exception as e:
            logger.error(f"{self.log_prefix} 获取子心流聊天状态时出错: {e}")
            return None

    async def set_sub_hearflow_chat_state(self, chat_id: str, target_state: ChatState) -> bool:
        """设置指定子心流的聊天状态

        Args:
            chat_id: 聊天ID
            target_state: 目标状态

        Returns:
            bool: 是否设置成功
        """
        try:
            return await heartflow.subheartflow_manager.force_change_state(chat_id, target_state)
        except Exception as e:
            logger.error(f"{self.log_prefix} 设置子心流聊天状态时出错: {e}")
            return False

    async def get_sub_hearflow_replyer(self, chat_id: str) -> Optional[Any]:
        """根据chat_id获取指定子心流的replyer实例

        Args:
            chat_id: 聊天ID

        Returns:
            Optional[Any]: replyer实例，如果不存在则返回None
        """
        try:
            replyer, _ = await self.get_sub_hearflow_replyer_and_expressor(chat_id)
            return replyer
        except Exception as e:
            logger.error(f"{self.log_prefix} 获取子心流replyer时出错: {e}")
            return None

    async def get_sub_hearflow_expressor(self, chat_id: str) -> Optional[Any]:
        """根据chat_id获取指定子心流的expressor实例

        Args:
            chat_id: 聊天ID

        Returns:
            Optional[Any]: expressor实例，如果不存在则返回None
        """
        try:
            _, expressor = await self.get_sub_hearflow_replyer_and_expressor(chat_id)
            return expressor
        except Exception as e:
            logger.error(f"{self.log_prefix} 获取子心流expressor时出错: {e}")
            return None
