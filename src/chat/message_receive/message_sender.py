# src/plugins/chat/message_sender.py
import asyncio
from collections import deque
from datetime import datetime, timedelta
from asyncio import Task
from typing import Optional

from maim_message import Seg
from src.common.message.api import global_api

from .message_send import MessageSend

from config import global_config
from src.common.logger_manager import get_logger
from rich.traceback import install

install(extra_lines=3)


logger = get_logger("sender")


def add_mode_corner_mark(message: MessageSend) -> None:
    """添加聊天模式角标"""
    if message.chat_mode == "normal":
        mode_corner_mark = "ⁿ"
    elif message.chat_mode == "focus":
        mode_corner_mark = "ᶠ"
    else:
        return
    message.message_base.message_segment.data.append(Seg(type="text", data=mode_corner_mark))


async def send_message(
    message: MessageSend,
) -> None:
    """发送消息（核心发送逻辑）"""
    if global_config.experimental.debug_show_chat_mode:
        # 聊天模式调试输出
        add_mode_corner_mark(message)

    if len(message.processed_plain_text) > 20:
        message_preview = f"{message.processed_plain_text[:20]}..."
    else:
        message_preview = message.processed_plain_text

    try:
        await global_api.send_message(message.message_base)
        logger.success(f"消息 '{message_preview}' 发送成功")  # 调整日志格式
    except Exception as e:
        logger.error(f"消息 '{message_preview}' 发送失败: {e}")


class MessageSendSet:
    """发送消息的容器"""

    def __init__(
        self,
        messages: list[MessageSend],
        enable_typing_time: bool = True,
        thinking_start_time: Optional[datetime] = None,
    ):
        """初始化发送消息容器

        :param messages: 消息列表，包含 MessageSend 对象
        :param enable_typing_time: 是否启用打字时间计算
        :param thinking_start_time: 思考开始时间，默认为当前时间
        :type messages: list[MessageSend]
        :type enable_typing_time: bool
        :type thinking_start_time: Optional[datetime]
        """
        self.messages = messages
        self.enable_typing_time = enable_typing_time
        self.thinking_start_time = thinking_start_time or datetime.now()


class ChatStreamMessageBuffer:
    """聊天流消息缓冲区"""

    def __init__(self, chat_stream_id: int):
        self.chat_stream_id: int = chat_stream_id
        """聊天流ID"""

        self.message_buffer: deque[MessageSendSet] = deque()
        """消息缓冲区，键为聊天流ID，值为消息发送容器"""

        self.send_task: Task | None = None
        """发送任务，异步任务对象"""

        self._lock = asyncio.Lock()
        """保护消息缓冲区的锁"""

    async def add_message_set(self, message_set: MessageSendSet):
        """添加消息发送容器到缓冲区"""
        async with self._lock:
            self.message_buffer.append(message_set)
            logger.debug(f"[CSID:{self.chat_stream_id}] 添加消息发送容器，当前缓冲区长度: {len(self.message_buffer)}")
            # 如果没有发送任务，则创建一个新的发送任务
            if not self.send_task or self.send_task.done():
                logger.debug(f"[CSID:{self.chat_stream_id}] 没有正在运行的消息发送任务，创建一个新的")
                # 创建新的发送任务
                self.send_task = asyncio.create_task(self.message_send_task())
                # 添加回调函数
                self.send_task.add_done_callback(self.message_send_task_callback)

    async def message_send_task(self):
        """消息发送任务，异步执行"""
        is_head = True  # 是否为首条消息
        last_message_time = datetime.now()  # 上一条消息发送时间
        while True:
            async with self._lock:
                if not self.message_buffer:
                    break  # 如果缓冲区为空，退出循环
                # 取出要发送的消息
                message_set = self.message_buffer.popleft()

            logger.debug(
                f"[CSID:{self.chat_stream_id}] 开始发送消息集，包含 {len(message_set.messages)} 条消息，当前缓冲区剩余长度: {len(self.message_buffer)}"
            )

            # 处理消息发送容器
            for message in message_set.messages:
                if is_head:
                    if message_set.enable_typing_time:
                        # 首条消息，检查与思考开始时间的时间差
                        left_time = (
                            (message_set.thinking_start_time + timedelta(seconds=message.typing_time)) - datetime.now()
                        ).total_seconds()
                        if left_time > 0:
                            # 如果未超过打字时间，则等待剩余时间
                            await asyncio.sleep(left_time)
                    await send_message(message)

                    last_message_time = datetime.now()  # 更新最后发送时间
                    is_head = False  # 之后的消息不再是头消息
                else:
                    if message_set.enable_typing_time:
                        # 非头消息，检查与上一条消息的时间差
                        time_since_last = (datetime.now() - last_message_time).total_seconds()
                        if time_since_last < message.typing_time:
                            # 如果未超过打字时间，则等待剩余时间
                            await asyncio.sleep(message.typing_time - time_since_last)
                    await send_message(message)

    def message_send_task_callback(self, future: Task):
        """发送任务完成后的回调函数"""
        if future.cancelled():
            logger.debug(f"[CSID:{self.chat_stream_id}] 消息发送任务被取消")
        elif future.exception():
            logger.error(f"[CSID:{self.chat_stream_id}] 消息发送任务发生异常: {future.exception()}")
        else:
            logger.debug(f"[CSID:{self.chat_stream_id}] 消息发送任务完成")

        # 清理已完成的任务
        self.send_task = None


class ChatStreamMessageManager:
    """聊天流消息管理器"""

    def __init__(self):
        self.message_buffer: dict[int, ChatStreamMessageBuffer] = {}
        """消息缓冲区，键为聊天流ID，值为消息发送容器列表"""

    async def add_message_set(self, message_set: MessageSendSet):
        """添加消息发送容器到对应的聊天流缓冲区"""
        chat_stream_id = message_set.messages[0].chat_stream_id
        assert chat_stream_id is not None, "消息发送容器中的聊天流ID不能为空"

        if chat_stream_id not in self.message_buffer:
            # 如果聊天流ID不存在，则创建新的缓冲区
            self.message_buffer[chat_stream_id] = ChatStreamMessageBuffer(chat_stream_id)
            logger.debug(f"创建新的聊天流消息缓冲区，[CSID:{chat_stream_id}]")

        # 获取对应的聊天流消息缓冲区
        chat_stream_buffer = self.message_buffer[chat_stream_id]
        await chat_stream_buffer.add_message_set(message_set)


message_manager = ChatStreamMessageManager()
