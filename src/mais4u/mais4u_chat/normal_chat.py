import asyncio
import time
from typing import Optional
from src.config.config import global_config
from src.common.logger import get_logger
from src.chat.message_receive.chat_stream import ChatStream, get_chat_manager
from src.chat.planner_actions.action_manager import ActionManager
from src.person_info.relationship_builder_manager import relationship_builder_manager
from .priority_manager import PriorityManager
import traceback
from src.chat.planner_actions.planner import ActionPlanner
from src.chat.planner_actions.action_modifier import ActionModifier
from src.chat.utils.chat_message_builder import get_raw_msg_by_timestamp_with_chat_inclusive

from src.chat.utils.utils import get_chat_type_and_target_info

logger = get_logger("normal_chat")

LOOP_INTERVAL = 0.3

class NormalChat:
    """
    普通聊天处理类，负责处理非核心对话的聊天逻辑。
    每个聊天（私聊或群聊）都会有一个独立的NormalChat实例。
    """

    def __init__(
        self,
        chat_stream: ChatStream,
        on_switch_to_focus_callback=None,
        get_cooldown_progress_callback=None,
    ):
        """
        初始化NormalChat实例。

        Args:
            chat_stream (ChatStream): 聊天流对象，包含与特定聊天相关的所有信息。
        """
        self.chat_stream = chat_stream
        self.stream_id = chat_stream.stream_id
        self.last_read_time = time.time()-1

        self.stream_name = get_chat_manager().get_stream_name(self.stream_id) or self.stream_id

        self.relationship_builder = relationship_builder_manager.get_or_create_builder(self.stream_id)

        self.is_group_chat, self.chat_target_info = get_chat_type_and_target_info(self.stream_id)

        self.start_time = time.time()

        # self.mood_manager = mood_manager
        self.start_time = time.time()
        
        self.running = False

        self._initialized = False  # Track initialization status

        # Planner相关初始化
        self.action_manager = ActionManager()
        self.planner = ActionPlanner(self.stream_id, self.action_manager, mode="normal")
        self.action_modifier = ActionModifier(self.action_manager, self.stream_id)
        self.enable_planner = global_config.normal_chat.enable_planner  # 从配置中读取是否启用planner

        # 记录最近的回复内容，每项包含: {time, user_message, response, is_mentioned, is_reference_reply}
        self.recent_replies = []
        self.max_replies_history = 20  # 最多保存最近20条回复记录

        # 添加回调函数，用于在满足条件时通知切换到focus_chat模式
        self.on_switch_to_focus_callback = on_switch_to_focus_callback

        # 添加回调函数，用于获取冷却进度
        self.get_cooldown_progress_callback = get_cooldown_progress_callback

        self._disabled = False  # 增加停用标志

        self.timeout_count = 0

        self.action_type: Optional[str] = None  # 当前动作类型
        self.is_parallel_action: bool = False  # 是否是可并行动作

        # 任务管理
        self._chat_task: Optional[asyncio.Task] = None
        self._priority_chat_task: Optional[asyncio.Task] = None # for priority mode consumer
        self._disabled = False  # 停用标志

        # 新增：回复模式和优先级管理器
        self.reply_mode = self.chat_stream.context.get_priority_mode()
        if self.reply_mode == "priority":
            self.priority_manager = PriorityManager(
                normal_queue_max_size=5,
            )
        else:
            self.priority_manager = None


        
    # async def _interest_mode_loopbody(self):
    #     try:
    #         await asyncio.sleep(LOOP_INTERVAL)
            
    #         if self._disabled:
    #             return False

    #         now = time.time()
    #         new_messages_data = get_raw_msg_by_timestamp_with_chat_inclusive(
    #             chat_id=self.stream_id, timestamp_start=self.last_read_time, timestamp_end=now, limit_mode="earliest"
    #         )
            
    #         if new_messages_data:
    #             self.last_read_time = now
            
    #             for msg_data in new_messages_data:
    #                 try:
    #                     self.adjust_reply_frequency()
    #                     await self.normal_response(
    #                         message_data=msg_data,
    #                         is_mentioned=msg_data.get("is_mentioned", False),
    #                         interested_rate=msg_data.get("interest_rate", 0.0) * self.willing_amplifier,
    #                     )
    #                     return True
    #                 except Exception as e:
    #                     logger.error(f"[{self.stream_name}] 处理消息时出错: {e} {traceback.format_exc()}")


    #     except asyncio.CancelledError:
    #         logger.info(f"[{self.stream_name}] 兴趣模式轮询任务被取消")
    #         return False
    #     except Exception:
    #         logger.error(f"[{self.stream_name}] 兴趣模式轮询循环出现错误: {traceback.format_exc()}", exc_info=True)
    #         await asyncio.sleep(10)
            
    async def _priority_mode_loopbody(self):
            try:
                await asyncio.sleep(LOOP_INTERVAL)

                if self._disabled:
                    return False

                now = time.time()
                new_messages_data = get_raw_msg_by_timestamp_with_chat_inclusive(
                    chat_id=self.stream_id, timestamp_start=self.last_read_time, timestamp_end=now, limit_mode="earliest"
                )

                if new_messages_data:
                    self.last_read_time = now

                    for msg_data in new_messages_data:
                        try:
                            if self.priority_manager:
                                self.priority_manager.add_message(msg_data, msg_data.get("interest_rate", 0.0))
                                return True
                        except Exception as e:
                            logger.error(f"[{self.stream_name}] 添加消息到优先级队列时出错: {e} {traceback.format_exc()}")


            except asyncio.CancelledError:
                logger.info(f"[{self.stream_name}] 优先级消息生产者任务被取消")
                return False
            except Exception:
                logger.error(f"[{self.stream_name}] 优先级消息生产者循环出现错误: {traceback.format_exc()}", exc_info=True)
                await asyncio.sleep(10)

    # async def _interest_message_polling_loop(self):
    #     """
    #     [Interest Mode] 通过轮询数据库获取新消息并直接处理。
    #     """
    #     logger.info(f"[{self.stream_name}] 兴趣模式消息轮询任务开始")
    #     try:
    #         while not self._disabled:
    #             success = await self._interest_mode_loopbody()
                
    #             if not success:
    #                 break

    #     except asyncio.CancelledError:
    #         logger.info(f"[{self.stream_name}] 兴趣模式消息轮询任务被优雅地取消了")




    async def _priority_chat_loop(self):
        """
        使用优先级队列的消息处理循环。
        """
        while not self._disabled:
            try:
                if self.priority_manager and not self.priority_manager.is_empty():
                    # 获取最高优先级的消息,现在是字典
                    message_data = self.priority_manager.get_highest_priority_message()

                    if message_data:
                        logger.info(
                            f"[{self.stream_name}] 从队列中取出消息进行处理: User {message_data.get('user_id')}, Time: {time.strftime('%H:%M:%S', time.localtime(message_data.get('time')))}"
                        )

                        do_reply = await self.reply_one_message(message_data)
                        response_set = do_reply if do_reply else []
                        factor = 0.5
                        cnt = sum([len(r) for r in response_set])
                        await asyncio.sleep(max(1, factor * cnt - 3))  # 等待tts

                # 等待一段时间再检查队列
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                logger.info(f"[{self.stream_name}] 优先级聊天循环被取消。")
                break
            except Exception:
                logger.error(f"[{self.stream_name}] 优先级聊天循环出现错误: {traceback.format_exc()}", exc_info=True)
                # 出现错误时，等待更长时间避免频繁报错
                await asyncio.sleep(10)
