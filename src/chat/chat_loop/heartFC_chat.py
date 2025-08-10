import asyncio
import time
import traceback
import random
from typing import List, Optional, Dict, Any, Tuple
from rich.traceback import install
from collections import deque

from src.config.config import global_config
from src.common.logger import get_logger
from src.chat.message_receive.chat_stream import ChatStream, get_chat_manager
from src.chat.utils.prompt_builder import global_prompt_manager
from src.chat.utils.timer_calculator import Timer
from src.chat.utils.chat_message_builder import get_raw_msg_by_timestamp_with_chat
from src.chat.planner_actions.planner import ActionPlanner
from src.chat.planner_actions.action_modifier import ActionModifier
from src.chat.planner_actions.action_manager import ActionManager
from src.chat.chat_loop.hfc_utils import CycleDetail
from src.person_info.relationship_builder_manager import relationship_builder_manager
from src.chat.express.expression_learner import expression_learner_manager
from src.person_info.person_info import get_person_info_manager
from src.plugin_system.base.component_types import ActionInfo, ChatMode, EventType
from src.plugin_system.core import events_manager
from src.plugin_system.apis import generator_api, send_api, message_api, database_api
from src.chat.willing.willing_manager import get_willing_manager
from src.mais4u.mai_think import mai_thinking_manager
from src.mais4u.constant_s4u import ENABLE_S4U
# no_reply逻辑已集成到heartFC_chat.py中，不再需要导入
from src.chat.chat_loop.hfc_utils import send_typing, stop_typing

ERROR_LOOP_INFO = {
    "loop_plan_info": {
        "action_result": {
            "action_type": "error",
            "action_data": {},
            "reasoning": "循环处理失败",
        },
    },
    "loop_action_info": {
        "action_taken": False,
        "reply_text": "",
        "command": "",
        "taken_time": time.time(),
    },
}

NO_ACTION = {
    "action_result": {
        "action_type": "no_action",
        "action_data": {},
        "reasoning": "规划器初始化默认",
        "is_parallel": True,
    },
    "chat_context": "",
    "action_prompt": "",
}

install(extra_lines=3)

# 注释：原来的动作修改超时常量已移除，因为改为顺序执行

logger = get_logger("hfc")  # Logger Name Changed


class HeartFChatting:
    """
    管理一个连续的Focus Chat循环
    用于在特定聊天流中生成回复。
    其生命周期现在由其关联的 SubHeartflow 的 FOCUSED 状态控制。
    """

    def __init__(
        self,
        chat_id: str,
    ):
        """
        HeartFChatting 初始化函数

        参数:
            chat_id: 聊天流唯一标识符(如stream_id)
            on_stop_focus_chat: 当收到stop_focus_chat命令时调用的回调函数
            performance_version: 性能记录版本号，用于区分不同启动版本
        """
        # 基础属性
        self.stream_id: str = chat_id  # 聊天流ID
        self.chat_stream: ChatStream = get_chat_manager().get_stream(self.stream_id)  # type: ignore
        if not self.chat_stream:
            raise ValueError(f"无法找到聊天流: {self.stream_id}")
        self.log_prefix = f"[{get_chat_manager().get_stream_name(self.stream_id) or self.stream_id}]"

        self.relationship_builder = relationship_builder_manager.get_or_create_builder(self.stream_id)
        self.expression_learner = expression_learner_manager.get_expression_learner(self.stream_id)
        

        self.action_manager = ActionManager()
        self.action_planner = ActionPlanner(chat_id=self.stream_id, action_manager=self.action_manager)
        self.action_modifier = ActionModifier(action_manager=self.action_manager, chat_id=self.stream_id)

        # 循环控制内部状态
        self.running: bool = False
        self._loop_task: Optional[asyncio.Task] = None  # 主循环任务
        self._energy_task: Optional[asyncio.Task] = None

        # 添加循环信息管理相关的属性
        self.history_loop: List[CycleDetail] = []
        self._cycle_counter = 0
        self._current_cycle_detail: CycleDetail = None  # type: ignore

        self.reply_timeout_count = 0
        self.plan_timeout_count = 0

        self.last_read_time = time.time() - 1

        self.willing_manager = get_willing_manager()

        logger.info(f"{self.log_prefix} HeartFChatting 初始化完成")

        self.energy_value = 5
        
        self.focus_energy = 1
        self.no_reply_consecutive = 0
        # 最近三次no_reply的新消息兴趣度记录
        self.recent_interest_records: deque = deque(maxlen=3)

    async def start(self):
        """检查是否需要启动主循环，如果未激活则启动。"""

        # 如果循环已经激活，直接返回
        if self.running:
            logger.debug(f"{self.log_prefix} HeartFChatting 已激活，无需重复启动")
            return

        try:
            # 标记为活动状态，防止重复启动
            self.running = True

            self._energy_task = asyncio.create_task(self._energy_loop())
            self._energy_task.add_done_callback(self._handle_energy_completion)

            self._loop_task = asyncio.create_task(self._main_chat_loop())
            self._loop_task.add_done_callback(self._handle_loop_completion)
            logger.info(f"{self.log_prefix} HeartFChatting 启动完成")

        except Exception as e:
            # 启动失败时重置状态
            self.running = False
            self._loop_task = None
            logger.error(f"{self.log_prefix} HeartFChatting 启动失败: {e}")
            raise

    def _handle_loop_completion(self, task: asyncio.Task):
        """当 _hfc_loop 任务完成时执行的回调。"""
        try:
            if exception := task.exception():
                logger.error(f"{self.log_prefix} HeartFChatting: 脱离了聊天(异常): {exception}")
                logger.error(traceback.format_exc())  # Log full traceback for exceptions
            else:
                logger.info(f"{self.log_prefix} HeartFChatting: 脱离了聊天 (外部停止)")
        except asyncio.CancelledError:
            logger.info(f"{self.log_prefix} HeartFChatting: 结束了聊天")

    def start_cycle(self):
        self._cycle_counter += 1
        self._current_cycle_detail = CycleDetail(self._cycle_counter)
        self._current_cycle_detail.thinking_id = f"tid{str(round(time.time(), 2))}"
        cycle_timers = {}
        return cycle_timers, self._current_cycle_detail.thinking_id

    def end_cycle(self, loop_info, cycle_timers):
        self._current_cycle_detail.set_loop_info(loop_info)
        self.history_loop.append(self._current_cycle_detail)
        self._current_cycle_detail.timers = cycle_timers
        self._current_cycle_detail.end_time = time.time()

    def _handle_energy_completion(self, task: asyncio.Task):
        if exception := task.exception():
            logger.error(f"{self.log_prefix} HeartFChatting: 能量循环异常: {exception}")
            logger.error(traceback.format_exc())
        else:
            logger.info(f"{self.log_prefix} HeartFChatting: 能量循环完成")

    async def _energy_loop(self):
        while self.running:
            await asyncio.sleep(12)
            self.energy_value -= 0.5
            self.energy_value = max(self.energy_value, 0.3)

    def print_cycle_info(self, cycle_timers):
        # 记录循环信息和计时器结果
        timer_strings = []
        for name, elapsed in cycle_timers.items():
            formatted_time = f"{elapsed * 1000:.2f}毫秒" if elapsed < 1 else f"{elapsed:.2f}秒"
            timer_strings.append(f"{name}: {formatted_time}")

        # 获取动作类型，兼容新旧格式
        action_type = "未知动作"
        if hasattr(self, '_current_cycle_detail') and self._current_cycle_detail:
            loop_plan_info = self._current_cycle_detail.loop_plan_info
            if isinstance(loop_plan_info, dict):
                action_result = loop_plan_info.get('action_result', {})
                if isinstance(action_result, dict):
                    # 旧格式：action_result是字典
                    action_type = action_result.get('action_type', '未知动作')
                elif isinstance(action_result, list) and action_result:
                    # 新格式：action_result是actions列表
                    action_type = action_result[0].get('action_type', '未知动作')
            elif isinstance(loop_plan_info, list) and loop_plan_info:
                # 直接是actions列表的情况
                action_type = loop_plan_info[0].get('action_type', '未知动作')

        logger.info(
            f"{self.log_prefix} 第{self._current_cycle_detail.cycle_id}次思考,"
            f"耗时: {self._current_cycle_detail.end_time - self._current_cycle_detail.start_time:.1f}秒, "  # type: ignore
            f"选择动作: {action_type}"
            + (f"\n详情: {'; '.join(timer_strings)}" if timer_strings else "")
        )
        
    def _determine_form_type(self) -> str:
        """判断使用哪种形式的no_reply"""
        # 如果连续no_reply次数少于3次，使用waiting形式
        if self.no_reply_consecutive <= 3:
            self.focus_energy = 1
        else:
            # 计算最近三次记录的兴趣度总和
            total_recent_interest = sum(self.recent_interest_records)
    
            # 计算调整后的阈值
            adjusted_threshold = 3 / global_config.chat.get_current_talk_frequency(self.stream_id)
            
            logger.info(f"{self.log_prefix} 最近三次兴趣度总和: {total_recent_interest:.2f}, 调整后阈值: {adjusted_threshold:.2f}")
        
            # 如果兴趣度总和小于阈值，进入breaking形式
            if total_recent_interest < adjusted_threshold:
                logger.info(f"{self.log_prefix} 兴趣度不足，进入breaking形式")
                self.focus_energy = random.randint(3, 6)
            else:
                logger.info(f"{self.log_prefix} 兴趣度充足")
                self.focus_energy = 1      
            
    async def _should_process_messages(self, new_message: List[Dict[str, Any]]) -> tuple[bool,float]:
        """
        判断是否应该处理消息
        
        Args:
            new_message: 新消息列表
            mode: 当前聊天模式
            
        Returns:
            bool: 是否应该处理消息
        """
        new_message_count = len(new_message)
        

        talk_frequency = global_config.chat.get_current_talk_frequency(self.stream_id)
        modified_exit_count_threshold = self.focus_energy / talk_frequency
        
        if new_message_count >= modified_exit_count_threshold:
            # 记录兴趣度到列表
            total_interest = 0.0
            for msg_dict in new_message:
                interest_value = msg_dict.get("interest_value", 0.0)
                if msg_dict.get("processed_plain_text", ""):
                    total_interest += interest_value
            
            self.recent_interest_records.append(total_interest)
            
            logger.info(
                f"{self.log_prefix} 累计消息数量达到{new_message_count}条(>{modified_exit_count_threshold})，结束等待"
            )
            return True,total_interest/new_message_count

        # 检查累计兴趣值
        if new_message_count > 0:
            accumulated_interest = 0.0
            for msg_dict in new_message:
                text = msg_dict.get("processed_plain_text", "")
                interest_value = msg_dict.get("interest_value", 0.0)
                if text:
                    accumulated_interest += interest_value
            
            # 只在兴趣值变化时输出log
            if not hasattr(self, "_last_accumulated_interest") or accumulated_interest != self._last_accumulated_interest:
                logger.info(f"{self.log_prefix} breaking形式当前累计兴趣值: {accumulated_interest:.2f}, 当前聊天频率: {talk_frequency:.2f}")
                self._last_accumulated_interest = accumulated_interest
            
            if accumulated_interest >= 3 / talk_frequency:
                # 记录兴趣度到列表
                self.recent_interest_records.append(accumulated_interest)
                
                logger.info(
                    f"{self.log_prefix} 累计兴趣值达到{accumulated_interest:.2f}(>{5 / talk_frequency})，结束等待"
                )
                return True,accumulated_interest/new_message_count

        # 每10秒输出一次等待状态
        if int(time.time() - self.last_read_time) > 0 and int(time.time() - self.last_read_time) % 10 == 0:
            logger.info(
                f"{self.log_prefix} 已等待{time.time() - self.last_read_time:.0f}秒，累计{new_message_count}条消息，继续等待..."
            )
            await asyncio.sleep(0.5)
        
        return False,0.0


    async def _loopbody(self):
        recent_messages_dict = message_api.get_messages_by_time_in_chat(
            chat_id=self.stream_id,
            start_time=self.last_read_time,
            end_time=time.time(),
            limit = 10,
            limit_mode="latest",
            filter_mai=True,
            filter_command=True,
        )   
        
        # 统一的消息处理逻辑
        should_process,interest_value = await self._should_process_messages(recent_messages_dict)
        
        if should_process:
            earliest_message_data = recent_messages_dict[0]
            self.last_read_time = earliest_message_data.get("time")
            await self._observe(interest_value = interest_value)

        else:
            # Normal模式：消息数量不足，等待
            await asyncio.sleep(0.5)
            return True

        return True

    async def build_reply_to_str(self, message_data: dict):
        person_info_manager = get_person_info_manager()
        
        # 获取 platform，如果不存在则从 chat_stream 获取，如果还是 None 则使用默认值
        platform = message_data.get("chat_info_platform")
        if platform is None:
            platform = getattr(self.chat_stream, "platform", "unknown")
        
        person_id = person_info_manager.get_person_id(
            platform,  # type: ignore
            message_data.get("user_id"),  # type: ignore
        )
        person_name = await person_info_manager.get_value(person_id, "person_name")
        return f"{person_name}:{message_data.get('processed_plain_text')}"

    async def _send_and_store_reply(
        self,
        response_set,
        reply_to_str,
        loop_start_time,
        action_message,
        cycle_timers: Dict[str, float],
        thinking_id,
        actions,
    ) -> Tuple[Dict[str, Any], str, Dict[str, float]]:
        with Timer("回复发送", cycle_timers):
            reply_text = await self._send_response(response_set, reply_to_str, loop_start_time, action_message)

            # 存储reply action信息
        person_info_manager = get_person_info_manager()
        
        # 获取 platform，如果不存在则从 chat_stream 获取，如果还是 None 则使用默认值
        platform = action_message.get("chat_info_platform")
        if platform is None:
            platform = getattr(self.chat_stream, "platform", "unknown")
        
        person_id = person_info_manager.get_person_id(
            platform,
            action_message.get("user_id", ""),
        )
        person_name = await person_info_manager.get_value(person_id, "person_name")
        action_prompt_display = f"你对{person_name}进行了回复：{reply_text}"

        await database_api.store_action_info(
            chat_stream=self.chat_stream,
            action_build_into_prompt=False,
            action_prompt_display=action_prompt_display,
            action_done=True,
            thinking_id=thinking_id,
            action_data={"reply_text": reply_text, "reply_to": reply_to_str},
            action_name="reply",
        )

        # 构建循环信息
        loop_info: Dict[str, Any] = {
            "loop_plan_info": {
                "action_result": actions,
            },
            "loop_action_info": {
                "action_taken": True,
                "reply_text": reply_text,
                "command": "",
                "taken_time": time.time(),
            },
        }

        return loop_info, reply_text, cycle_timers

    async def _observe(self,interest_value:float = 0.0) -> bool:

        action_type = "no_action"
        reply_text = ""  # 初始化reply_text变量，避免UnboundLocalError
        reply_to_str = ""  # 初始化reply_to_str变量

        # 根据interest_value计算概率，决定使用哪种planner模式
        # interest_value越高，越倾向于使用Normal模式
        import random
        import math
        
        # 使用sigmoid函数将interest_value转换为概率
        # 当interest_value为0时，概率接近0（使用Focus模式）
        # 当interest_value很高时，概率接近1（使用Normal模式）
        def calculate_normal_mode_probability(interest_val: float) -> float:
            # 使用sigmoid函数，调整参数使概率分布更合理
            # 当interest_value = 0时，概率约为0.1
            # 当interest_value = 1时，概率约为0.5
            # 当interest_value = 2时，概率约为0.8
            # 当interest_value = 3时，概率约为0.95
            k = 2.0  # 控制曲线陡峭程度
            x0 = 1.0  # 控制曲线中心点
            return 1.0 / (1.0 + math.exp(-k * (interest_val - x0)))
        
        normal_mode_probability = calculate_normal_mode_probability(interest_value)
        
        # 根据概率决定使用哪种模式
        if random.random() < normal_mode_probability:
            mode = ChatMode.NORMAL
            logger.info(f"{self.log_prefix} 基于兴趣值 {interest_value:.2f}，概率 {normal_mode_probability:.2f}，选择Normal planner模式")
        else:
            mode = ChatMode.FOCUS
            logger.info(f"{self.log_prefix} 基于兴趣值 {interest_value:.2f}，概率 {normal_mode_probability:.2f}，选择Focus planner模式")

        # 创建新的循环信息
        cycle_timers, thinking_id = self.start_cycle()

        logger.info(f"{self.log_prefix} 开始第{self._cycle_counter}次思考")

        if ENABLE_S4U:
            await send_typing()

        async with global_prompt_manager.async_message_scope(self.chat_stream.context.get_template_name()):
            loop_start_time = time.time()
            await self.relationship_builder.build_relation()
            await self.expression_learner.trigger_learning_for_chat()

            available_actions = {}

            # 第一步：动作修改
            with Timer("动作修改", cycle_timers):
                try:
                    await self.action_modifier.modify_actions()
                    available_actions = self.action_manager.get_using_actions()
                except Exception as e:
                    logger.error(f"{self.log_prefix} 动作修改失败: {e}")

            # 执行planner
            planner_info = self.action_planner.get_necessary_info()
            prompt_info = await self.action_planner.build_planner_prompt(
                is_group_chat=planner_info[0],
                chat_target_info=planner_info[1],
                current_available_actions=planner_info[2],
            )
            if not await events_manager.handle_mai_events(
                EventType.ON_PLAN, None, prompt_info[0], None, self.chat_stream.stream_id
            ):
                return False
            with Timer("规划器", cycle_timers):
                actions, _= await self.action_planner.plan(
                    mode=mode,
                    loop_start_time=loop_start_time,
                    available_actions=available_actions,
                )

            # action_result: Dict[str, Any] = plan_result.get("action_result", {})  # type: ignore
            # action_type, action_data, reasoning, is_parallel = (
            #     action_result.get("action_type", "error"),
            #     action_result.get("action_data", {}),
            #     action_result.get("reasoning", "未提供理由"),
            #     action_result.get("is_parallel", True),
            # )

            
            # 3. 并行执行所有动作
            async def execute_action(action_info):
                """执行单个动作的通用函数"""
                try:
                    if action_info["action_type"] == "no_reply":
                        # 直接处理no_reply逻辑，不再通过动作系统
                        reason = action_info.get("reasoning", "选择不回复")
                        logger.info(f"{self.log_prefix} 选择不回复，原因: {reason}")
                        
                        # 存储no_reply信息到数据库
                        await database_api.store_action_info(
                            chat_stream=self.chat_stream,
                            action_build_into_prompt=False,
                            action_prompt_display=reason,
                            action_done=True,
                            thinking_id=thinking_id,
                            action_data={"reason": reason},
                            action_name="no_reply",
                        )
                        
                        return {
                            "action_type": "no_reply",
                            "success": True,
                            "reply_text": "",
                            "command": ""
                        }
                    elif action_info["action_type"] != "reply":
                        # 执行普通动作
                        with Timer("动作执行", cycle_timers):
                            success, reply_text, command = await self._handle_action(
                                action_info["action_type"],
                                action_info["reasoning"],
                                action_info["action_data"],
                                cycle_timers,
                                thinking_id,
                                action_info["action_message"]
                            )
                        return {
                            "action_type": action_info["action_type"],
                            "success": success,
                            "reply_text": reply_text,
                            "command": command
                        }
                    else:
                        # 执行回复动作
                        reply_to_str = await self.build_reply_to_str(action_info["action_message"])
                        
                        
                        # 生成回复
                        gather_timeout = global_config.chat.thinking_timeout
                        try:
                            response_set = await asyncio.wait_for(
                                self._generate_response(
                                    message_data=action_info["action_message"],
                                    available_actions=action_info["available_actions"],
                                    reply_to=reply_to_str,
                                    request_type="chat.replyer",
                                ),
                                timeout=gather_timeout
                            )
                        except asyncio.TimeoutError:
                            logger.warning(
                                f"{self.log_prefix} 并行执行：回复生成超时>{global_config.chat.thinking_timeout}s，已跳过"
                            )
                            return {
                                "action_type": "reply",
                                "success": False,
                                "reply_text": "",
                                "loop_info": None
                            }
                        except asyncio.CancelledError:
                            logger.debug(f"{self.log_prefix} 并行执行：回复生成任务已被取消")
                            return {
                                "action_type": "reply",
                                "success": False,
                                "reply_text": "",
                                "loop_info": None
                            }

                        if not response_set:
                            logger.warning(f"{self.log_prefix} 模型超时或生成回复内容为空")
                            return {
                                "action_type": "reply",
                                "success": False,
                                "reply_text": "",
                                "loop_info": None
                            }

                        loop_info, reply_text, cycle_timers_reply = await self._send_and_store_reply(
                            response_set,
                            reply_to_str,
                            loop_start_time,
                            action_info["action_message"],
                            cycle_timers,
                            thinking_id,
                            actions,
                        )
                        return {
                            "action_type": "reply",
                            "success": True,
                            "reply_text": reply_text,
                            "loop_info": loop_info
                        }
                except Exception as e:
                    logger.error(f"{self.log_prefix} 执行动作时出错: {e}")
                    logger.error(f"{self.log_prefix} 错误信息: {traceback.format_exc()}")
                    return {
                        "action_type": action_info["action_type"],
                        "success": False,
                        "reply_text": "",
                        "loop_info": None,
                        "error": str(e)
                    }
            
            # 创建所有动作的后台任务
            print(actions)
            
            action_tasks = [asyncio.create_task(execute_action(action)) for action in actions]
            
            # 并行执行所有任务
            results = await asyncio.gather(*action_tasks, return_exceptions=True)
            
            # 处理执行结果
            reply_loop_info = None
            reply_text_from_reply = ""
            action_success = False
            action_reply_text = ""
            action_command = ""
            
            for i, result in enumerate(results):
                if isinstance(result, BaseException):
                    logger.error(f"{self.log_prefix} 动作执行异常: {result}")
                    continue
                
                action_info = actions[i]
                if result["action_type"] != "reply":
                    action_success = result["success"]
                    action_reply_text = result["reply_text"]
                    action_command = result.get("command", "")
                elif result["action_type"] == "reply":
                    if result["success"]:
                        reply_loop_info = result["loop_info"]
                        reply_text_from_reply = result["reply_text"]
                    else:
                        logger.warning(f"{self.log_prefix} 回复动作执行失败")

            # 构建最终的循环信息
            if reply_loop_info:
                # 如果有回复信息，使用回复的loop_info作为基础
                loop_info = reply_loop_info
                # 更新动作执行信息
                loop_info["loop_action_info"].update(
                    {
                        "action_taken": action_success,
                        "command": action_command,
                        "taken_time": time.time(),
                    }
                )
                reply_text = reply_text_from_reply
            else:
                # 没有回复信息，构建纯动作的loop_info
                loop_info = {
                    "loop_plan_info": {
                        "action_result": actions,
                    },
                    "loop_action_info": {
                        "action_taken": action_success,
                        "reply_text": action_reply_text,
                        "command": action_command,
                        "taken_time": time.time(),
                    },
                }
                reply_text = action_reply_text
                    

        if ENABLE_S4U:
            await stop_typing()
            await mai_thinking_manager.get_mai_think(self.stream_id).do_think_after_response(reply_text)

        self.end_cycle(loop_info, cycle_timers)
        self.print_cycle_info(cycle_timers)

        # await self.willing_manager.after_generate_reply_handle(message_data.get("message_id", ""))

        action_type = actions[0]["action_type"] if actions else "no_action"
        
        # 管理no_reply计数器：当执行了非no_reply动作时，重置计数器
        if action_type != "no_reply":
            # no_reply逻辑已集成到heartFC_chat.py中，直接重置计数器
            self.recent_interest_records.clear()
            self.no_reply_consecutive = 0
            logger.debug(f"{self.log_prefix} 执行了{action_type}动作，重置no_reply计数器")
            return True
            
        if action_type == "no_reply":
            self.no_reply_consecutive += 1
            self._determine_form_type()

        return True

    async def _main_chat_loop(self):
        """主循环，持续进行计划并可能回复消息，直到被外部取消。"""
        try:
            while self.running:
                # 主循环
                success = await self._loopbody()
                await asyncio.sleep(0.1)
                if not success:
                    break
        except asyncio.CancelledError:
            # 设置了关闭标志位后被取消是正常流程
            logger.info(f"{self.log_prefix} 麦麦已关闭聊天")
        except Exception:
            logger.error(f"{self.log_prefix} 麦麦聊天意外错误，将于3s后尝试重新启动")
            print(traceback.format_exc())
            await asyncio.sleep(3)
            self._loop_task = asyncio.create_task(self._main_chat_loop())
        logger.error(f"{self.log_prefix} 结束了当前聊天循环")

    async def _handle_action(
        self,
        action: str,
        reasoning: str,
        action_data: dict,
        cycle_timers: Dict[str, float],
        thinking_id: str,
        action_message: dict,
    ) -> tuple[bool, str, str]:
        """
        处理规划动作，使用动作工厂创建相应的动作处理器

        参数:
            action: 动作类型
            reasoning: 决策理由
            action_data: 动作数据，包含不同动作需要的参数
            cycle_timers: 计时器字典
            thinking_id: 思考ID

        返回:
            tuple[bool, str, str]: (是否执行了动作, 思考消息ID, 命令)
        """
        try:
            # 使用工厂创建动作处理器实例
            try:
                action_handler = self.action_manager.create_action(
                    action_name=action,
                    action_data=action_data,
                    reasoning=reasoning,
                    cycle_timers=cycle_timers,
                    thinking_id=thinking_id,
                    chat_stream=self.chat_stream,
                    log_prefix=self.log_prefix,
                    action_message=action_message,
                )
            except Exception as e:
                logger.error(f"{self.log_prefix} 创建动作处理器时出错: {e}")
                traceback.print_exc()
                return False, "", ""

            if not action_handler:
                logger.warning(f"{self.log_prefix} 未能创建动作处理器: {action}")
                return False, "", ""

            # 处理动作并获取结果
            result = await action_handler.handle_action()
            success, reply_text = result
            command = ""

            if reply_text == "timeout":
                self.reply_timeout_count += 1
                if self.reply_timeout_count > 5:
                    logger.warning(
                        f"[{self.log_prefix} ] 连续回复超时次数过多，{global_config.chat.thinking_timeout}秒 内大模型没有返回有效内容，请检查你的api是否速度过慢或配置错误。建议不要使用推理模型，推理模型生成速度过慢。或者尝试拉高thinking_timeout参数，这可能导致回复时间过长。"
                    )
                logger.warning(f"{self.log_prefix} 回复生成超时{global_config.chat.thinking_timeout}s，已跳过")
                return False, "", ""

            return success, reply_text, command

        except Exception as e:
            logger.error(f"{self.log_prefix} 处理{action}时出错: {e}")
            traceback.print_exc()
            return False, "", ""

    async def _generate_response(
        self,
        message_data: dict,
        available_actions: Optional[Dict[str, ActionInfo]],
        reply_to: str,
        request_type: str = "chat.replyer.normal",
    ) -> Optional[list]:
        """生成普通回复"""
        try:
            success, reply_set, _ = await generator_api.generate_reply(
                chat_stream=self.chat_stream,
                reply_to=reply_to,
                available_actions=available_actions,
                enable_tool=global_config.tool.enable_tool,
                request_type=request_type,
                from_plugin=False,
            )

            if not success or not reply_set:
                logger.info(f"对 {message_data.get('processed_plain_text')} 的回复生成失败")
                return None

            return reply_set

        except Exception as e:
            logger.error(f"{self.log_prefix}回复生成出现错误：{str(e)} {traceback.format_exc()}")
            return None

    async def _send_response(self, reply_set, reply_to, thinking_start_time, message_data) -> str:
        current_time = time.time()
        new_message_count = message_api.count_new_messages(
            chat_id=self.chat_stream.stream_id, start_time=thinking_start_time, end_time=current_time
        )
        platform = message_data.get("user_platform", "")
        user_id = message_data.get("user_id", "")
        reply_to_platform_id = f"{platform}:{user_id}"

        need_reply = new_message_count >= random.randint(2, 4)

        if need_reply:
            logger.info(f"{self.log_prefix} 从思考到回复，共有{new_message_count}条新消息，使用引用回复")

        reply_text = ""
        first_replied = False
        for reply_seg in reply_set:
            data = reply_seg[1]
            if not first_replied:
                if need_reply:
                    await send_api.text_to_stream(
                        text=data,
                        stream_id=self.chat_stream.stream_id,
                        reply_to=reply_to,
                        reply_to_platform_id=reply_to_platform_id,
                        typing=False,
                    )
                else:
                    await send_api.text_to_stream(
                        text=data,
                        stream_id=self.chat_stream.stream_id,
                        reply_to_platform_id=reply_to_platform_id,
                        typing=False,
                    )
                first_replied = True
            else:
                await send_api.text_to_stream(
                    text=data,
                    stream_id=self.chat_stream.stream_id,
                    reply_to_platform_id=reply_to_platform_id,
                    typing=True,
                )
            reply_text += data

        return reply_text
