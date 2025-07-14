import asyncio
import math
from typing import Tuple

from src.chat.memory_system.Hippocampus import hippocampus_manager
from src.chat.message_receive.message import MessageRecv
from src.chat.message_receive.storage import MessageStorage
from src.chat.message_receive.chat_stream import get_chat_manager
from src.chat.utils.timer_calculator import Timer
from src.chat.utils.utils import is_mentioned_bot_in_message
from src.common.logger import get_logger
from src.config.config import global_config
from src.mais4u.mais4u_chat.body_emotion_action_manager import action_manager
from src.mais4u.mais4u_chat.s4u_mood_manager import mood_manager
from src.mais4u.mais4u_chat.s4u_watching_manager import watching_manager
from src.mais4u.mais4u_chat.context_web_manager import get_context_web_manager

from .s4u_chat import get_s4u_chat_manager


# from ..message_receive.message_buffer import message_buffer

logger = get_logger("chat")


async def _calculate_interest(message: MessageRecv) -> Tuple[float, bool]:
    """计算消息的兴趣度

    Args:
        message: 待处理的消息对象

    Returns:
        Tuple[float, bool]: (兴趣度, 是否被提及)
    """
    is_mentioned, _ = is_mentioned_bot_in_message(message)
    interested_rate = 0.0

    if global_config.memory.enable_memory:
        with Timer("记忆激活"):
            interested_rate = await hippocampus_manager.get_activate_from_text(
                message.processed_plain_text,
                fast_retrieval=True,
            )
            logger.debug(f"记忆激活率: {interested_rate:.2f}")

    text_len = len(message.processed_plain_text)
    # 根据文本长度调整兴趣度，长度越大兴趣度越高，但增长率递减，最低0.01，最高0.05
    # 采用对数函数实现递减增长

    base_interest = 0.01 + (0.05 - 0.01) * (math.log10(text_len + 1) / math.log10(1000 + 1))
    base_interest = min(max(base_interest, 0.01), 0.05)

    interested_rate += base_interest

    if is_mentioned:
        interest_increase_on_mention = 1
        interested_rate += interest_increase_on_mention

    return interested_rate, is_mentioned


class S4UMessageProcessor:
    """心流处理器，负责处理接收到的消息并计算兴趣度"""

    def __init__(self):
        """初始化心流处理器，创建消息存储实例"""
        self.storage = MessageStorage()

    async def process_message(self, message: MessageRecv) -> None:
        """处理接收到的原始消息数据

        主要流程:
        1. 消息解析与初始化
        2. 消息缓冲处理
        3. 过滤检查
        4. 兴趣度计算
        5. 关系处理

        Args:
            message_data: 原始消息字符串
        """

        target_user_id_list = ["1026294844", "964959351"]

        # 1. 消息解析与初始化
        groupinfo = message.message_info.group_info
        userinfo = message.message_info.user_info
        message_info = message.message_info

        chat = await get_chat_manager().get_or_create_stream(
            platform=message_info.platform,
            user_info=userinfo,
            group_info=groupinfo,
        )

        await self.storage.store_message(message, chat)

        s4u_chat = get_s4u_chat_manager().get_or_create_chat(chat)

        if userinfo.user_id in target_user_id_list:
            await s4u_chat.add_message(message)
        else:
            await s4u_chat.add_message(message)

        interested_rate, _ = await _calculate_interest(message)
        
        await mood_manager.start()

        chat_mood = mood_manager.get_mood_by_chat_id(chat.stream_id)
        asyncio.create_task(chat_mood.update_mood_by_message(message))
        chat_action = action_manager.get_action_state_by_chat_id(chat.stream_id)
        asyncio.create_task(chat_action.update_action_by_message(message))
        # asyncio.create_task(chat_action.update_facial_expression_by_message(message, interested_rate))
        
        # 视线管理：收到消息时切换视线状态
        chat_watching = watching_manager.get_watching_by_chat_id(chat.stream_id)
        asyncio.create_task(chat_watching.on_message_received())

        # 上下文网页管理：启动独立task处理消息上下文
        asyncio.create_task(self._handle_context_web_update(chat.stream_id, message))

        # 7. 日志记录
        logger.info(f"[S4U]{userinfo.user_nickname}:{message.processed_plain_text}")

    async def _handle_context_web_update(self, chat_id: str, message: MessageRecv):
        """处理上下文网页更新的独立task
        
        Args:
            chat_id: 聊天ID
            message: 消息对象
        """
        try:
            logger.debug(f"🔄 开始处理上下文网页更新: {message.message_info.user_info.user_nickname}")
            
            context_manager = get_context_web_manager()
            
            # 只在服务器未启动时启动（避免重复启动）
            if context_manager.site is None:
                logger.info("🚀 首次启动上下文网页服务器...")
                await context_manager.start_server()
            
            # 添加消息到上下文并更新网页
            await context_manager.add_message(chat_id, message)
            
            logger.debug(f"✅ 上下文网页更新完成: {message.message_info.user_info.user_nickname}")
            
        except Exception as e:
            logger.error(f"❌ 处理上下文网页更新失败: {e}", exc_info=True)
