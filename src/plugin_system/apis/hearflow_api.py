from typing import Optional, List, Any, Tuple
from src.common.logger import get_logger

logger = get_logger("hearflow_api")


def _get_heartflow():
    """获取heartflow实例的延迟导入函数"""
    from src.chat.heart_flow.heartflow import heartflow
    return heartflow


def _get_subheartflow_types():
    """获取SubHeartflow和ChatState类型的延迟导入函数"""
    from src.chat.heart_flow.sub_heartflow import SubHeartflow, ChatState
    return SubHeartflow, ChatState


class HearflowAPI:
    """心流API模块

    提供与心流和子心流相关的操作接口
    """

    def __init__(self):
        self.log_prefix = "[HearflowAPI]"

    async def get_sub_hearflow_by_chat_id(self, chat_id: str) -> Optional[Any]:
        """根据chat_id获取指定的sub_hearflow实例

        Args:
            chat_id: 聊天ID，与sub_hearflow的subheartflow_id相同

        Returns:
            Optional[SubHeartflow]: sub_hearflow实例，如果不存在则返回None
        """
        # 使用延迟导入
        heartflow = _get_heartflow()
        
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

    async def get_or_create_sub_hearflow_by_chat_id(self, chat_id: str) -> Optional[Any]:
        """根据chat_id获取或创建sub_hearflow实例

        Args:
            chat_id: 聊天ID

        Returns:
            Optional[SubHeartflow]: sub_hearflow实例，创建失败时返回None
        """
        heartflow = _get_heartflow()
        return await heartflow.get_or_create_subheartflow(chat_id)

    def get_all_sub_hearflow_ids(self) -> List[str]:
        """获取所有子心流的ID列表

        Returns:
            List[str]: 所有子心流的ID列表
        """
        heartflow = _get_heartflow()
        all_subflows = heartflow.subheartflow_manager.get_all_subheartflows()
        chat_ids = [subflow.chat_id for subflow in all_subflows if not subflow.should_stop]
        logger.debug(f"{self.log_prefix} 获取到 {len(chat_ids)} 个活跃的子心流ID")
        return chat_ids

    def get_all_sub_hearflows(self) -> List[Any]:
        """获取所有子心流实例

        Returns:
            List[SubHeartflow]: 所有活跃的子心流实例列表
        """
        heartflow = _get_heartflow()
        all_subflows = heartflow.subheartflow_manager.get_all_subheartflows()
        active_subflows = [subflow for subflow in all_subflows if not subflow.should_stop]
        logger.debug(f"{self.log_prefix} 获取到 {len(active_subflows)} 个活跃的子心流实例")
        return active_subflows

    async def get_sub_hearflow_chat_state(self, chat_id: str) -> Optional[Any]:
        """获取指定子心流的聊天状态

        Args:
            chat_id: 聊天ID

        Returns:
            Optional[ChatState]: 聊天状态，如果子心流不存在则返回None
        """
        subflow = await self.get_sub_hearflow_by_chat_id(chat_id)
        if subflow:
            return subflow.chat_state.chat_status
        return None

    async def set_sub_hearflow_chat_state(self, chat_id: str, target_state: Any) -> bool:
        """设置指定子心流的聊天状态

        Args:
            chat_id: 聊天ID
            target_state: 目标状态(ChatState枚举值)

        Returns:
            bool: 是否设置成功
        """
        heartflow = _get_heartflow()
        return await heartflow.subheartflow_manager.force_change_state(chat_id, target_state)

    async def get_sub_hearflow_replyer_and_expressor(self, chat_id: str) -> Tuple[Optional[Any], Optional[Any]]:
        """根据chat_id获取指定子心流的replyer和expressor实例

        Args:
            chat_id: 聊天ID

        Returns:
            Tuple[Optional[Any], Optional[Any]]: (replyer实例, expressor实例)，如果子心流不存在或未处于FOCUSED状态，返回(None, None)
        """
        subflow = await self.get_sub_hearflow_by_chat_id(chat_id)
        if not subflow:
            logger.debug(f"{self.log_prefix} 子心流不存在: {chat_id}")
            return None, None

        # 使用延迟导入获取ChatState
        _, ChatState = _get_subheartflow_types()

        # 检查子心流是否处于FOCUSED状态且有HeartFC实例
        if subflow.chat_state.chat_status != ChatState.FOCUSED:
            logger.debug(f"{self.log_prefix} 子心流 {chat_id} 未处于FOCUSED状态，当前状态: {subflow.chat_state.chat_status.value}")
            return None, None

        if not subflow.heart_fc_instance:
            logger.debug(f"{self.log_prefix} 子心流 {chat_id} 没有HeartFC实例")
            return None, None

        # 返回replyer和expressor实例
        replyer = subflow.heart_fc_instance.replyer
        expressor = subflow.heart_fc_instance.expressor
        
        if replyer and expressor:
            logger.debug(f"{self.log_prefix} 成功获取子心流 {chat_id} 的replyer和expressor")
        else:
            logger.warning(f"{self.log_prefix} 子心流 {chat_id} 的replyer或expressor为空")
            
        return replyer, expressor

    async def get_sub_hearflow_replyer(self, chat_id: str) -> Optional[Any]:
        """根据chat_id获取指定子心流的replyer实例

        Args:
            chat_id: 聊天ID

        Returns:
            Optional[Any]: replyer实例，如果不存在则返回None
        """
        replyer, _ = await self.get_sub_hearflow_replyer_and_expressor(chat_id)
        return replyer

    async def get_sub_hearflow_expressor(self, chat_id: str) -> Optional[Any]:
        """根据chat_id获取指定子心流的expressor实例

        Args:
            chat_id: 聊天ID

        Returns:
            Optional[Any]: expressor实例，如果不存在则返回None
        """
        _, expressor = await self.get_sub_hearflow_replyer_and_expressor(chat_id)
        return expressor
