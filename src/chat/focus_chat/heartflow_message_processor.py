from model_manager.message import MessageManager
from src.chat.memory_system.Hippocampus import HippocampusManager
from src.config.config import global_config
from src.chat.message_receive.message import MessageRecv
from src.chat.message_receive.storage import MessageStorage
from src.chat.heart_flow.heartflow import heartflow
from src.chat.utils.timer_calculator import Timer
from src.common.logger_manager import get_logger

import math
import re
import traceback
from typing import Optional, Tuple
from maim_message import MessageBase

# from ..message_receive.message_buffer import message_buffer

logger = get_logger("chat")


async def _handle_error(error: Exception, context: str, message: Optional[MessageRecv] = None) -> None:
    """统一的错误处理函数

    Args:
        error: 捕获到的异常
        context: 错误发生的上下文描述
        message: 可选的消息对象，用于记录相关消息内容
    """
    logger.error(f"{context}: {error}")
    logger.error(traceback.format_exc())
    if message and hasattr(message, "raw_message"):
        logger.error(f"相关消息原始内容: {message.raw_message}")


def is_mentioned_bot_in_message(message: MessageRecv) -> tuple[bool, float]:
    """检查消息是否提到了机器人"""
    reply_probability = 0.0
    is_mentioned = False

    # 来自Adapter的额外配置
    # TODO: 该部分实现非最终实现，待议
    if (
        message.message_base.message_info.additional_config is not None
        and message.message_base.message_info.additional_config.get("is_mentioned") is not None
    ):
        try:
            reply_probability = float(message.message_base.message_info.additional_config.get("is_mentioned"))
            is_mentioned = True
            return is_mentioned, reply_probability
        except Exception as e:
            logger.warning(e)
            logger.warning(
                f"消息中包含不合理的设置 is_mentioned: {message.message_base.message_info.additional_config.get('is_mentioned')}"
            )

    if message.is_self_at or message.is_self_replied:
        is_mentioned = True
        if global_config.normal_chat.at_bot_inevitable_reply:
            reply_probability = 1.0
    elif message.is_self_mentioned:
        is_mentioned = True
        if global_config.normal_chat.mentioned_bot_inevitable_reply:
            reply_probability = 1.0

    return is_mentioned, reply_probability


async def _calculate_interest(message: MessageRecv) -> Tuple[float, bool]:
    """计算消息的兴趣度

    Args:
        message: 待处理的消息对象

    Returns:
        Tuple[float, bool]: (兴趣度, 是否被提及)
    """
    is_mentioned, _ = is_mentioned_bot_in_message(message)
    interested_rate = 0.0

    with Timer("记忆激活"):
        interested_rate = await HippocampusManager.get_instance().get_activate_from_text(
            message.processed_plain_text,
            fast_retrieval=True,
        )
        text_len = len(message.processed_plain_text)
        # 根据文本长度调整兴趣度，长度越大兴趣度越高，但增长率递减，最低0.01，最高0.05
        # 采用对数函数实现递减增长

        base_interest = 0.01 + (0.05 - 0.01) * (math.log10(text_len + 1) / math.log10(1000 + 1))
        base_interest = min(max(base_interest, 0.01), 0.05)

        interested_rate += base_interest

        logger.trace(f"记忆激活率: {interested_rate:.2f}")

    if is_mentioned:
        interest_increase_on_mention = 1
        interested_rate += interest_increase_on_mention

    return interested_rate, is_mentioned


class HeartFCMessageReceiver:
    """心流处理器，负责处理接收到的消息并计算兴趣度"""

    def __init__(self):
        """初始化心流处理器，创建消息存储实例"""
        self.storage = MessageStorage()

    async def process_message(self, message_base: MessageBase) -> None:
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
        message = None
        try:
            message = MessageRecv(message_base)
            del message_base  # 释放原始消息对象

            # 1. 消息解析与初始化
            await message.process()

            is_group_msg = message.message_base.message_info.group_info is not None

            sender_name = message.message_base.message_info.user_info.user_nickname
            if is_group_msg:
                group_name = message.message_base.message_info.group_info.group_name

            # 2. 过滤检查
            for word in global_config.message_receive.ban_words:
                if word in message.processed_plain_text:
                    if is_group_msg:
                        logger.info(
                            f"[过滤词识别] 群聊 '{group_name}' 中，"
                            f"'{sender_name}' 发送的消息 '{message.processed_plain_text}' "
                            f"含有过滤词 '{word}'，已过滤"
                        )
                    else:
                        logger.info(
                            f"[过滤词识别] 与 '{sender_name}' 的私聊中，"
                            f"对方发送的消息 '{message.processed_plain_text}' "
                            f"含有过滤词 '{word}'，已过滤"
                        )
                    return

            for regex in global_config.message_receive.ban_msgs_regex:
                if re.search(regex, message.processed_plain_text):
                    if is_group_msg:
                        logger.info(
                            f"[过滤正则识别] 群聊 '{group_name}' 中，"
                            f"'{sender_name}' 发送的消息 '{message.processed_plain_text}' "
                            f"匹配到了过滤正则 '{regex}'，已过滤"
                        )
                    else:
                        logger.info(
                            f"[过滤正则识别] 与 '{sender_name}' 的私聊中，"
                            f"对方发送的消息 '{message.processed_plain_text}' "
                            f"匹配到了过滤正则 '{regex}'，已过滤"
                        )
                    return

            # 3. 消息存储
            message_dto = MessageManager.create_message(message)
            logger.trace(f"存储成功: message_id in DB-'{message_dto.id}'")

            # 4. 获取子心流
            subheartflow = await heartflow.get_or_create_subheartflow(message.chat_stream_id)

            # 5. 兴趣度计算与更新
            interested_rate, is_mentioned = await _calculate_interest(message)
            subheartflow.add_message_to_normal_chat_cache(message, interested_rate, is_mentioned)

            # 7. 日志记录
            if is_group_msg:
                logger.info(f"[群聊 '{group_name}'] '{sender_name}': '{message.processed_plain_text}'")
            else:
                logger.info(f"[私聊] '{sender_name}': '{message.processed_plain_text}'")

        except Exception as e:
            await _handle_error(e, "消息处理失败", message)
