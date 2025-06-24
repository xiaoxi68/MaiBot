import asyncio
import time
import traceback
import random
from typing import List, Optional, Dict  # 导入类型提示
import os
import pickle
from maim_message import UserInfo, Seg
from src.common.logger import get_logger
from src.chat.heart_flow.utils_chat import get_chat_type_and_target_info
from src.manager.mood_manager import mood_manager
from src.chat.message_receive.chat_stream import ChatStream, get_chat_manager
from src.chat.utils.timer_calculator import Timer
from src.chat.utils.prompt_builder import global_prompt_manager
from .s4u_stream_generator import S4UStreamGenerator
from src.chat.message_receive.message import MessageSending, MessageRecv, MessageThinking, MessageSet
from src.chat.message_receive.message_sender import message_manager
from src.chat.normal_chat.willing.willing_manager import get_willing_manager
from src.chat.normal_chat.normal_chat_utils import get_recent_message_stats
from src.config.config import global_config
from src.chat.focus_chat.planners.action_manager import ActionManager
from src.chat.normal_chat.normal_chat_planner import NormalChatPlanner
from src.chat.normal_chat.normal_chat_action_modifier import NormalChatActionModifier
from src.chat.normal_chat.normal_chat_expressor import NormalChatExpressor
from src.chat.focus_chat.replyer.default_generator import DefaultReplyer
from src.person_info.person_info import PersonInfoManager
from src.person_info.relationship_manager import get_relationship_manager
from src.chat.utils.chat_message_builder import (
    get_raw_msg_by_timestamp_with_chat,
    get_raw_msg_by_timestamp_with_chat_inclusive,
    get_raw_msg_before_timestamp_with_chat,
    num_new_messages_since,
)
from src.common.message.api import get_global_api
from src.chat.message_receive.storage import MessageStorage
from src.audio.mock_audio import MockAudioGenerator, MockAudioPlayer


logger = get_logger("S4U_chat")


class MessageSenderContainer:
    """一个简单的容器，用于按顺序发送消息并模拟打字效果。"""
    def __init__(self, chat_stream: ChatStream, original_message: MessageRecv):
        self.chat_stream = chat_stream
        self.original_message = original_message
        self.queue = asyncio.Queue()
        self.storage = MessageStorage()
        self._task: Optional[asyncio.Task] = None
        self._paused_event = asyncio.Event()
        self._paused_event.set()  # 默认设置为非暂停状态

    async def add_message(self, chunk: str):
        """向队列中添加一个消息块。"""
        await self.queue.put(chunk)

    async def close(self):
        """表示没有更多消息了，关闭队列。"""
        await self.queue.put(None)  # Sentinel

    def pause(self):
        """暂停发送。"""
        self._paused_event.clear()

    def resume(self):
        """恢复发送。"""
        self._paused_event.set()

    def _calculate_typing_delay(self, text: str) -> float:
        """根据文本长度计算模拟打字延迟。"""
        chars_per_second = 15.0
        min_delay = 0.2
        max_delay = 2.0
        
        delay = len(text) / chars_per_second
        return max(min_delay, min(delay, max_delay))

    async def _send_worker(self):
        """从队列中取出消息并发送。"""
        while True:
            try:
                # This structure ensures that task_done() is called for every item retrieved,
                # even if the worker is cancelled while processing the item.
                chunk = await self.queue.get()
            except asyncio.CancelledError:
                break

            try:
                if chunk is None:
                    break

                # Check for pause signal *after* getting an item.
                await self._paused_event.wait()

                delay = self._calculate_typing_delay(chunk)
                await asyncio.sleep(delay)

                current_time = time.time()
                msg_id = f"{current_time}_{random.randint(1000, 9999)}"
                
                text_to_send = chunk
                if global_config.experimental.debug_show_chat_mode:
                    text_to_send += "ⁿ"

                message_segment = Seg(type="text", data=text_to_send)
                bot_message = MessageSending(
                    message_id=msg_id,
                    chat_stream=self.chat_stream,
                    bot_user_info=UserInfo(
                        user_id=global_config.bot.qq_account,
                        user_nickname=global_config.bot.nickname,
                        platform=self.original_message.message_info.platform,
                    ),
                    sender_info=self.original_message.message_info.user_info,
                    message_segment=message_segment,
                    reply=self.original_message,
                    is_emoji=False,
                    apply_set_reply_logic=True,
                )
                
                await bot_message.process()
                
                await get_global_api().send_message(bot_message)
                logger.info(f"已将消息 '{text_to_send}' 发往平台 '{bot_message.message_info.platform}'")
                
                await self.storage.store_message(bot_message, self.chat_stream)
            
            except Exception as e:
                logger.error(f"[{self.chat_stream.get_stream_name()}] 消息发送或存储时出现错误: {e}", exc_info=True)
            
            finally:
                # CRUCIAL: Always call task_done() for any item that was successfully retrieved.
                self.queue.task_done()

    def start(self):
        """启动发送任务。"""
        if self._task is None:
            self._task = asyncio.create_task(self._send_worker())
    
    async def join(self):
        """等待所有消息发送完毕。"""
        if self._task:
            await self._task


class S4UChatManager:
    def __init__(self):
        self.s4u_chats: Dict[str, "S4UChat"] = {}

    def get_or_create_chat(self, chat_stream: ChatStream) -> "S4UChat":
        if chat_stream.stream_id not in self.s4u_chats:
            stream_name = get_chat_manager().get_stream_name(chat_stream.stream_id) or chat_stream.stream_id
            logger.info(f"Creating new S4UChat for stream: {stream_name}")
            self.s4u_chats[chat_stream.stream_id] = S4UChat(chat_stream)
        return self.s4u_chats[chat_stream.stream_id]

s4u_chat_manager = S4UChatManager()

def get_s4u_chat_manager() -> S4UChatManager:
    return s4u_chat_manager


class S4UChat:
    def __init__(self, chat_stream: ChatStream):
        """初始化 S4UChat 实例。"""

        self.chat_stream = chat_stream
        self.stream_id = chat_stream.stream_id
        self.stream_name = get_chat_manager().get_stream_name(self.stream_id) or self.stream_id
        
        self._message_queue = asyncio.Queue()
        self._processing_task = asyncio.create_task(self._message_processor())
        self._current_generation_task: Optional[asyncio.Task] = None
        
        self._is_replying = False

        # 初始化Normal Chat专用表达器
        self.expressor = NormalChatExpressor(self.chat_stream)
        self.replyer = DefaultReplyer(self.chat_stream)

        self.gpt = S4UStreamGenerator()
        self.audio_generator = MockAudioGenerator()
        self.start_time = time.time()

        # 记录最近的回复内容，每项包含: {time, user_message, response, is_mentioned, is_reference_reply}
        self.recent_replies = []
        self.max_replies_history = 20  # 最多保存最近20条回复记录
        
        self.storage = MessageStorage()


        logger.info(f"[{self.stream_name}] S4UChat")


    # 改为实例方法, 移除 chat 参数
    async def response(self, message: MessageRecv, is_mentioned: bool, interested_rate: float) -> None:
        """将消息放入队列并中断当前处理（如果正在处理）。"""
        if self._current_generation_task and not self._current_generation_task.done():
            self._current_generation_task.cancel()
            logger.info(f"[{self.stream_name}] 请求中断当前回复生成任务。")
        
        await self._message_queue.put(message)

    async def _message_processor(self):
        """从队列中处理消息，支持中断。"""
        while True:
            try:
                # 等待第一条消息
                message = await self._message_queue.get()

                # 如果因快速中断导致队列中积压了更多消息，则只处理最新的一条
                while not self._message_queue.empty():
                    drained_msg = self._message_queue.get_nowait()
                    self._message_queue.task_done() # 为取出的旧消息调用 task_done
                    message = drained_msg # 始终处理最新消息
                    logger.info(f"[{self.stream_name}] 丢弃过时消息，处理最新消息: {message.processed_plain_text}")

                self._current_generation_task = asyncio.create_task(self._generate_and_send(message))

                try:
                    await self._current_generation_task
                except asyncio.CancelledError:
                    logger.info(f"[{self.stream_name}] 回复生成被外部中断。")
                except Exception as e:
                    logger.error(f"[{self.stream_name}] _generate_and_send 任务出现错误: {e}", exc_info=True)
                finally:
                    self._current_generation_task = None
            
            except asyncio.CancelledError:
                logger.info(f"[{self.stream_name}] 消息处理器正在关闭。")
                break
            except Exception as e:
                logger.error(f"[{self.stream_name}] 消息处理器主循环发生未知错误: {e}", exc_info=True)
                await asyncio.sleep(1) # 避免在未知错误下陷入CPU空转
            finally:
                # 确保处理过的消息（无论是正常完成还是被丢弃）都被标记完成
                if 'message' in locals():
                    self._message_queue.task_done()


    async def _generate_and_send(self, message: MessageRecv):
        """为单个消息生成文本和音频回复。整个过程可以被中断。"""
        self._is_replying = True
        sender_container = MessageSenderContainer(self.chat_stream, message)
        sender_container.start()
        
        try:
            logger.info(
                f"[S4U] 开始为消息生成文本和音频流: "
                f"'{message.processed_plain_text[:30]}...'"
            )
            
            # 1. 逐句生成文本、发送并播放音频
            gen = self.gpt.generate_response(message, "")
            async for chunk in gen:
                # 如果任务被取消，await 会在此处引发 CancelledError
                
                # a. 发送文本块
                await sender_container.add_message(chunk)
                
                # b. 为该文本块生成并播放音频
                if chunk.strip():
                    audio_data = await self.audio_generator.generate(chunk)
                    player = MockAudioPlayer(audio_data)
                    await player.play()

            # 等待所有文本消息发送完成
            await sender_container.close()
            await sender_container.join()
            logger.info(f"[{self.stream_name}] 所有文本和音频块处理完毕。")

        except asyncio.CancelledError:
            logger.info(f"[{self.stream_name}] 回复流程（文本或音频）被中断。")
            raise  # 将取消异常向上传播
        except Exception as e:
            logger.error(f"[{self.stream_name}] 回复生成过程中出现错误: {e}", exc_info=True)
        finally:
            self._is_replying = False
            # 确保发送器被妥善关闭（即使已关闭，再次调用也是安全的）
            sender_container.resume()
            if not sender_container._task.done():
                await sender_container.close()
                await sender_container.join()
            logger.info(f"[{self.stream_name}] _generate_and_send 任务结束，资源已清理。")


    async def shutdown(self):
        """平滑关闭处理任务。"""
        logger.info(f"正在关闭 S4UChat: {self.stream_name}")
        
        # 取消正在运行的任务
        if self._current_generation_task and not self._current_generation_task.done():
            self._current_generation_task.cancel()
        
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
        
        # 等待任务响应取消
        try:
            await self._processing_task
        except asyncio.CancelledError:
            logger.info(f"处理任务已成功取消: {self.stream_name}")