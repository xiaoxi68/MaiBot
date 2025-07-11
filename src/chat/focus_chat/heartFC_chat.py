import asyncio
import time
import traceback
from collections import deque
from typing import Optional, Deque, Callable, Awaitable

from sqlalchemy import False_
from src.chat.message_receive.chat_stream import get_chat_manager
from rich.traceback import install
from src.chat.utils.prompt_builder import global_prompt_manager
from src.common.logger import get_logger
from src.chat.utils.timer_calculator import Timer
from src.chat.focus_chat.focus_loop_info import FocusLoopInfo
from src.chat.planner_actions.planner import ActionPlanner
from src.chat.planner_actions.action_modifier import ActionModifier
from src.chat.planner_actions.action_manager import ActionManager
from src.config.config import global_config
from src.person_info.relationship_builder_manager import relationship_builder_manager
from src.chat.focus_chat.hfc_utils import CycleDetail
from random import random
from src.chat.focus_chat.hfc_utils import create_thinking_message_from_dict, add_messages_to_manager,get_recent_message_stats,cleanup_thinking_message_by_id
from src.person_info.person_info import get_person_info_manager
from src.plugin_system.apis import generator_api
from ..message_receive.message import MessageThinking
from src.chat.message_receive.normal_message_sender import message_manager
from src.chat.willing.willing_manager import get_willing_manager
from .priority_manager import PriorityManager
from src.chat.utils.chat_message_builder import get_raw_msg_by_timestamp_with_chat_inclusive



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
        self.chat_stream = get_chat_manager().get_stream(self.stream_id)
        self.log_prefix = f"[{get_chat_manager().get_stream_name(self.stream_id) or self.stream_id}]"

        self.relationship_builder = relationship_builder_manager.get_or_create_builder(self.stream_id)

        self.loop_mode = "normal"
        
        self.recent_replies = []
        
        # 新增：消息计数器和疲惫阈值
        self._message_count = 0  # 发送的消息计数
        # 基于exit_focus_threshold动态计算疲惫阈值
        # 基础值30条，通过exit_focus_threshold调节：threshold越小，越容易疲惫
        self._message_threshold = max(10, int(30 * global_config.chat.exit_focus_threshold))
        self._fatigue_triggered = False  # 是否已触发疲惫退出

        self.loop_info: FocusLoopInfo = FocusLoopInfo(observe_id=self.stream_id)

        self.action_manager = ActionManager()
        self.action_planner = ActionPlanner(chat_id=self.stream_id, action_manager=self.action_manager)
        self.action_modifier = ActionModifier(action_manager=self.action_manager, chat_id=self.stream_id)

        # 循环控制内部状态
        self.running: bool = False
        self._loop_task: Optional[asyncio.Task] = None  # 主循环任务

        # 添加循环信息管理相关的属性
        self._cycle_counter = 0
        self._cycle_history: Deque[CycleDetail] = deque(maxlen=10)  # 保留最近10个循环的信息
        self._current_cycle_detail: Optional[CycleDetail] = None

        self.reply_timeout_count = 0
        self.plan_timeout_count = 0
        
        self.last_read_time = time.time()-1
        
        
        
        self.willing_amplifier = 1

        self.action_type: Optional[str] = None  # 当前动作类型
        self.is_parallel_action: bool = False  # 是否是可并行动作
        
        self._chat_task: Optional[asyncio.Task] = None
        self._priority_chat_task: Optional[asyncio.Task] = None # for priority mode consumer
        
        self.reply_mode = self.chat_stream.context.get_priority_mode()
        if self.reply_mode == "priority":
            self.priority_manager = PriorityManager(
                normal_queue_max_size=5,
            )
        else:
            self.priority_manager = None
            
        self.willing_manager = get_willing_manager()
        
        

        logger.info(
            f"{self.log_prefix} HeartFChatting 初始化完成，消息疲惫阈值: {self._message_threshold}条（基于exit_focus_threshold={global_config.chat.exit_focus_threshold}计算，仅在auto模式下生效）"
        )

    async def start(self):
        """检查是否需要启动主循环，如果未激活则启动。"""

        # 如果循环已经激活，直接返回
        if self.running:
            logger.debug(f"{self.log_prefix} HeartFChatting 已激活，无需重复启动")
            return

        try:
            # 重置消息计数器，开始新的focus会话
            self.reset_message_count()
            # 标记为活动状态，防止重复启动
            self.running = True

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
            exception = task.exception()
            if exception:
                logger.error(f"{self.log_prefix} HeartFChatting: 脱离了聊天(异常): {exception}")
                logger.error(traceback.format_exc())  # Log full traceback for exceptions
            else:
                logger.info(f"{self.log_prefix} HeartFChatting: 脱离了聊天 (外部停止)")
        except asyncio.CancelledError:
            logger.info(f"{self.log_prefix} HeartFChatting: 脱离了聊天(任务取消)")
        finally:
            self.running = False
            self._loop_task = None
            
    def start_cycle(self):
        self._cycle_counter += 1
        self._current_cycle_detail = CycleDetail(self._cycle_counter)
        self._current_cycle_detail.prefix = self.log_prefix
        thinking_id = "tid" + str(round(time.time(), 2))
        self._current_cycle_detail.set_thinking_id(thinking_id)
        cycle_timers = {}
        return cycle_timers, thinking_id
    
    def end_cycle(self,loop_info,cycle_timers):
        self._current_cycle_detail.set_loop_info(loop_info)
        self.loop_info.add_loop_info(self._current_cycle_detail)
        self._current_cycle_detail.timers = cycle_timers
        self._current_cycle_detail.complete_cycle()
        self._cycle_history.append(self._current_cycle_detail)
        
    def print_cycle_info(self,cycle_timers):
            # 记录循环信息和计时器结果
            timer_strings = []
            for name, elapsed in cycle_timers.items():
                formatted_time = f"{elapsed * 1000:.2f}毫秒" if elapsed < 1 else f"{elapsed:.2f}秒"
                timer_strings.append(f"{name}: {formatted_time}")

            logger.info(
                f"{self.log_prefix} 第{self._current_cycle_detail.cycle_id}次思考,"
                f"耗时: {self._current_cycle_detail.end_time - self._current_cycle_detail.start_time:.1f}秒, "
                f"选择动作: {self._current_cycle_detail.loop_plan_info.get('action_result', {}).get('action_type', '未知动作')}"
                + (f"\n详情: {'; '.join(timer_strings)}" if timer_strings else "")
            )
        

    
    async def _loopbody(self):
        if self.loop_mode == "focus":
            logger.info(f"{self.log_prefix} 开始第{self._cycle_counter}次观察")
            return await self._observe()
        elif self.loop_mode == "normal":
            now = time.time()
            new_messages_data = get_raw_msg_by_timestamp_with_chat_inclusive(
                chat_id=self.stream_id, timestamp_start=self.last_read_time, timestamp_end=now, limit_mode="earliest"
            )
            
            if new_messages_data:
                self.last_read_time = now
            
                for msg_data in new_messages_data:
                    try:
                        self.adjust_reply_frequency()
                        logger.info(f"{self.log_prefix} 开始第{self._cycle_counter}次循环")
                        await self.normal_response(msg_data)
                        # TODO: 这个地方可能导致阻塞，需要优化
                        return True
                    except Exception as e:
                        logger.error(f"[{self.log_prefix}] 处理消息时出错: {e} {traceback.format_exc()}")
            else:
                await asyncio.sleep(0.1)
            
            return True
            


    async def _observe(self,message_data:dict = None):
        # 创建新的循环信息
        cycle_timers, thinking_id = self.start_cycle()
        
        await create_thinking_message_from_dict(message_data,self.chat_stream,thinking_id)

        async with global_prompt_manager.async_message_scope(
            self.chat_stream.context.get_template_name()
        ):

            loop_start_time = time.time()
            await self.loop_info.observe()
            await self.relationship_builder.build_relation()
            
            # 第一步：动作修改
            with Timer("动作修改", cycle_timers):
                try:
                    if self.loop_mode == "focus":
                        await self.action_modifier.modify_actions(
                            loop_info=self.loop_info,
                            mode="focus",
                        )
                    elif self.loop_mode == "normal":
                        await self.action_modifier.modify_actions(mode="normal")
                        available_actions = self.action_manager.get_using_actions_for_mode("normal")
                except Exception as e:
                    logger.error(f"{self.log_prefix} 动作修改失败: {e}")
                    
            #如果normal，开始一个回复生成进程，先准备好回复（其实是和planer同时进行的）
            if self.loop_mode == "normal":
                gen_task = asyncio.create_task(self._generate_normal_response(message_data, available_actions))
            

            with Timer("规划器", cycle_timers):
                if self.loop_mode == "focus":
                    if self.action_modifier.should_skip_planning_for_no_reply():
                        logger.info(f"[{self.log_prefix}] 没有可用动作，跳过规划")
                        action_type = "no_reply"
                    else:
                        plan_result = await self.action_planner.plan(mode="focus")
                elif self.loop_mode == "normal":
                    if self.action_modifier.should_skip_planning_for_no_action():
                        logger.info(f"[{self.log_prefix}] 没有可用动作，跳过规划")
                        action_type = "no_action"
                    else:
                        plan_result = await self.action_planner.plan(mode="normal")



            action_result = plan_result.get("action_result", {})
            action_type, action_data, reasoning, is_parallel = (
                action_result.get("action_type", "error"),
                action_result.get("action_data", {}),
                action_result.get("reasoning", "未提供理由"),
                action_result.get("is_parallel", True),
            )

            action_data["loop_start_time"] = loop_start_time
            
            if self.loop_mode == "normal":
                if action_type == "no_action":
                    logger.info(f"[{self.log_prefix}] {global_config.bot.nickname} 决定进行回复")
                elif is_parallel:
                    logger.info(
                        f"[{self.log_prefix}] {global_config.bot.nickname} 决定进行回复, 同时执行{action_type}动作"
                    )
                else:
                    logger.info(f"[{self.log_prefix}] {global_config.bot.nickname} 决定执行{action_type}动作")

            
            
            if action_type == "no_action":
                gather_timeout = global_config.chat.thinking_timeout
                results = await asyncio.wait_for(
                    asyncio.gather(gen_task, return_exceptions=True),
                    timeout=gather_timeout,
                )
                response_set = results[0]
                
                if response_set:
                    content = " ".join([item[1] for item in response_set if item[0] == "text"])

                
                if not response_set or (
                    action_type not in ["no_action"] and not is_parallel
                ):
                    if not response_set:
                        logger.warning(f"[{self.log_prefix}] 模型未生成回复内容")
                    elif action_type not in ["no_action"] and not is_parallel:
                        logger.info(
                            f"[{self.log_prefix}] {global_config.bot.nickname} 原本想要回复：{content}，但选择执行{self.action_type}，不发表回复"
                        )
                    # 如果模型未生成回复，移除思考消息
                    await cleanup_thinking_message_by_id(self.chat_stream.stream_id,thinking_id,self.log_prefix)
                    return False

                logger.info(f"[{self.log_prefix}] {global_config.bot.nickname} 决定的回复内容: {content}")

                # 提取回复文本
                reply_texts = [item[1] for item in response_set if item[0] == "text"]
                if not reply_texts:
                    logger.info(f"[{self.log_prefix}] 回复内容中没有文本，不发送消息")
                    await cleanup_thinking_message_by_id(self.chat_stream.stream_id,thinking_id,self.log_prefix)
                    return False

                # 发送回复 (不再需要传入 chat)
                first_bot_msg = await add_messages_to_manager(message_data, reply_texts, thinking_id,self.chat_stream.stream_id)

                # 检查 first_bot_msg 是否为 None (例如思考消息已被移除的情况)
                if first_bot_msg:
                    # 消息段已在接收消息时更新，这里不需要额外处理

                    # 记录回复信息到最近回复列表中
                    reply_info = {
                        "time": time.time(),
                        "user_message": message_data.get("processed_plain_text"),
                        "user_info": {
                            "user_id": message_data.get("user_id"),
                            "user_nickname": message_data.get("user_nickname"),
                        },
                        "response": response_set,
                        "is_reference_reply": message_data.get("reply") is not None,  # 判断是否为引用回复
                    }
                    self.recent_replies.append(reply_info)
                    # 保持最近回复历史在限定数量内
                    if len(self.recent_replies) > 10:
                        self.recent_replies = self.recent_replies[-10 :]
                return response_set if response_set else False
                
                
                
                
                
            else:
                # 动作执行计时
                with Timer("动作执行", cycle_timers):
                    success, reply_text, command = await self._handle_action(
                        action_type, reasoning, action_data, cycle_timers, thinking_id
                    )

                loop_info = {
                    "loop_plan_info": {
                        "action_result": plan_result.get("action_result", {}),
                    },
                    "loop_action_info": {
                        "action_taken": success,
                        "reply_text": reply_text,
                        "command": command,
                        "taken_time": time.time(),
                    },
                }

                if loop_info["loop_action_info"]["command"] == "stop_focus_chat":
                    logger.info(f"{self.log_prefix} 麦麦决定停止专注聊天")
                    return False
                    #停止该聊天模式的循环

        self.end_cycle(loop_info,cycle_timers)
        self.print_cycle_info(cycle_timers)

        if self.loop_mode == "normal":
            await self.willing_manager.after_generate_reply_handle(message_data.get("message_id"))

        return True
    
    
    
    async def _main_chat_loop(self):
        """主循环，持续进行计划并可能回复消息，直到被外部取消。"""
        try:
            while self.running:  # 主循环
                success = await self._loopbody()
                if not success:
                    break
                
            logger.info(f"{self.log_prefix} 麦麦已强制离开聊天")
        except asyncio.CancelledError:
            # 设置了关闭标志位后被取消是正常流程
            logger.info(f"{self.log_prefix} 麦麦已关闭聊天")
        except Exception:
            logger.error(f"{self.log_prefix} 麦麦聊天意外错误")
            print(traceback.format_exc())
        # 理论上不能到这里
        logger.error(f"{self.log_prefix} 麦麦聊天意外错误，结束了聊天循环")

    async def _handle_action(
        self,
        action: str,
        reasoning: str,
        action_data: dict,
        cycle_timers: dict,
        thinking_id: str,
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
            if len(result) == 3:
                success, reply_text, command = result
            else:
                success, reply_text = result
                command = ""

            command = self._count_reply_and_exit_focus_chat(action,success)
            
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
        
    def _count_reply_and_exit_focus_chat(self,action,success):
        # 新增：消息计数和疲惫检查
        if action == "reply" and success:
            self._message_count += 1
            current_threshold = self._get_current_fatigue_threshold()
            logger.info(
                f"{self.log_prefix} 已发送第 {self._message_count} 条消息（动态阈值: {current_threshold}, exit_focus_threshold: {global_config.chat.exit_focus_threshold}）"
            )

            # 检查是否达到疲惫阈值（只有在auto模式下才会自动退出）
            if (
                global_config.chat.chat_mode == "auto"
                and self._message_count >= current_threshold
                and not self._fatigue_triggered
            ):
                self._fatigue_triggered = True
                logger.info(
                    f"{self.log_prefix} [auto模式] 已发送 {self._message_count} 条消息，达到疲惫阈值 {current_threshold}，麦麦感到疲惫了，准备退出专注聊天模式"
                )
                # 设置系统命令，在下次循环检查时触发退出
                command = "stop_focus_chat"
                
                return command
        return ""

    def _get_current_fatigue_threshold(self) -> int:
        """动态获取当前的疲惫阈值，基于exit_focus_threshold配置

        Returns:
            int: 当前的疲惫阈值
        """
        return max(10, int(30 / global_config.chat.exit_focus_threshold))


    def reset_message_count(self):
        """重置消息计数器（用于重新启动focus模式时）"""
        self._message_count = 0
        self._fatigue_triggered = False
        logger.info(f"{self.log_prefix} 消息计数器已重置")

    async def shutdown(self):
        """优雅关闭HeartFChatting实例，取消活动循环任务"""
        logger.info(f"{self.log_prefix} 正在关闭HeartFChatting...")
        self.running = False  # <-- 在开始关闭时设置标志位

        # 记录最终的消息统计
        if self._message_count > 0:
            logger.info(f"{self.log_prefix} 本次focus会话共发送了 {self._message_count} 条消息")
            if self._fatigue_triggered:
                logger.info(f"{self.log_prefix} 因疲惫而退出focus模式")

        # 取消循环任务
        if self._loop_task and not self._loop_task.done():
            logger.info(f"{self.log_prefix} 正在取消HeartFChatting循环任务")
            self._loop_task.cancel()
            try:
                await asyncio.wait_for(self._loop_task, timeout=1.0)
                logger.info(f"{self.log_prefix} HeartFChatting循环任务已取消")
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.error(f"{self.log_prefix} 取消循环任务出错: {e}")
        else:
            logger.info(f"{self.log_prefix} 没有活动的HeartFChatting循环任务")

        # 清理状态
        self.running = False
        self._loop_task = None

        # 重置消息计数器，为下次启动做准备
        self.reset_message_count()

        logger.info(f"{self.log_prefix} HeartFChatting关闭完成")


    def adjust_reply_frequency(self):
        """
        根据预设规则动态调整回复意愿（willing_amplifier）。
        - 评估周期：10分钟
        - 目标频率：由 global_config.chat.talk_frequency 定义（例如 1条/分钟）
        - 调整逻辑：
            - 0条回复 -> 5.0x 意愿
            - 达到目标回复数 -> 1.0x 意愿（基准）
            - 达到目标2倍回复数 -> 0.2x 意愿
            - 中间值线性变化
        - 增益抑制：如果最近5分钟回复过快，则不增加意愿。
        """
        # --- 1. 定义参数 ---
        evaluation_minutes = 10.0
        target_replies_per_min = global_config.chat.get_current_talk_frequency(
            self.stream_id
        )  # 目标频率：e.g. 1条/分钟
        target_replies_in_window = target_replies_per_min * evaluation_minutes  # 10分钟内的目标回复数

        if target_replies_in_window <= 0:
            logger.debug(f"[{self.log_prefix}] 目标回复频率为0或负数，不调整意愿放大器。")
            return

        # --- 2. 获取近期统计数据 ---
        stats_10_min = get_recent_message_stats(minutes=evaluation_minutes, chat_id=self.stream_id)
        bot_reply_count_10_min = stats_10_min["bot_reply_count"]

        # --- 3. 计算新的意愿放大器 (willing_amplifier) ---
        # 基于回复数在 [0, target*2] 区间内进行分段线性映射
        if bot_reply_count_10_min <= target_replies_in_window:
            # 在 [0, 目标数] 区间，意愿从 5.0 线性下降到 1.0
            new_amplifier = 5.0 + (bot_reply_count_10_min - 0) * (1.0 - 5.0) / (target_replies_in_window - 0)
        elif bot_reply_count_10_min <= target_replies_in_window * 2:
            # 在 [目标数, 目标数*2] 区间，意愿从 1.0 线性下降到 0.2
            over_target_cap = target_replies_in_window * 2
            new_amplifier = 1.0 + (bot_reply_count_10_min - target_replies_in_window) * (0.2 - 1.0) / (
                over_target_cap - target_replies_in_window
            )
        else:
            # 超过目标数2倍，直接设为最小值
            new_amplifier = 0.2

        # --- 4. 检查是否需要抑制增益 ---
        # "如果邻近5分钟内，回复数量 > 频率/2，就不再进行增益"
        suppress_gain = False
        if new_amplifier > self.willing_amplifier:  # 仅在计算结果为增益时检查
            suppression_minutes = 5.0
            # 5分钟内目标回复数的一半
            suppression_threshold = (target_replies_per_min / 2) * suppression_minutes  # e.g., (1/2)*5 = 2.5
            stats_5_min = get_recent_message_stats(minutes=suppression_minutes, chat_id=self.stream_id)
            bot_reply_count_5_min = stats_5_min["bot_reply_count"]

            if bot_reply_count_5_min > suppression_threshold:
                suppress_gain = True

        # --- 5. 更新意愿放大器 ---
        if suppress_gain:
            logger.debug(
                f"[{self.log_prefix}] 回复增益被抑制。最近5分钟内回复数 ({bot_reply_count_5_min}) "
                f"> 阈值 ({suppression_threshold:.1f})。意愿放大器保持在 {self.willing_amplifier:.2f}"
            )
            # 不做任何改动
        else:
            # 限制最终值在 [0.2, 5.0] 范围内
            self.willing_amplifier = max(0.2, min(5.0, new_amplifier))
            logger.debug(
                f"[{self.log_prefix}] 调整回复意愿。10分钟内回复: {bot_reply_count_10_min} (目标: {target_replies_in_window:.0f}) -> "
                f"意愿放大器更新为: {self.willing_amplifier:.2f}"
            )
            
            
            
    async def normal_response(self, message_data: dict) -> None:
        """
        处理接收到的消息。
        在"兴趣"模式下，判断是否回复并生成内容。
        """
        
        is_mentioned = message_data.get("is_mentioned", False)
        interested_rate = message_data.get("interest_rate", 0.0) * self.willing_amplifier
        
        reply_probability = (
            1.0 if is_mentioned and global_config.normal_chat.mentioned_bot_inevitable_reply else 0.0
        )  # 如果被提及，且开启了提及必回复，则基础概率为1，否则需要意愿判断

        # 意愿管理器：设置当前message信息
        self.willing_manager.setup(message_data, self.chat_stream)

        # 获取回复概率
        # 仅在未被提及或基础概率不为1时查询意愿概率
        if reply_probability < 1:  # 简化逻辑，如果未提及 (reply_probability 为 0)，则获取意愿概率
            # is_willing = True
            reply_probability = await self.willing_manager.get_reply_probability(message_data.get("message_id"))

            additional_config = message_data.get("additional_config", {})
            if additional_config and "maimcore_reply_probability_gain" in additional_config:
                reply_probability += additional_config["maimcore_reply_probability_gain"]
                reply_probability = min(max(reply_probability, 0), 1)  # 确保概率在 0-1 之间

        # 处理表情包
        if message_data.get("is_emoji") or message_data.get("is_picid"):
            reply_probability = 0

        # 应用疲劳期回复频率调整
        fatigue_multiplier = self._get_fatigue_reply_multiplier()
        original_probability = reply_probability
        reply_probability *= fatigue_multiplier

        # 如果应用了疲劳调整，记录日志
        if fatigue_multiplier < 1.0:
            logger.info(
                f"[{self.log_prefix}] 疲劳期回复频率调整: {original_probability * 100:.1f}% -> {reply_probability * 100:.1f}% (系数: {fatigue_multiplier:.2f})"
            )

        # 打印消息信息
        mes_name = self.chat_stream.group_info.group_name if self.chat_stream.group_info else "私聊"
        if reply_probability > 0.1:
            logger.info(
                f"[{mes_name}]"
                f"{message_data.get('user_nickname')}:"
                f"{message_data.get('processed_plain_text')}[兴趣:{interested_rate:.2f}][回复概率:{reply_probability * 100:.1f}%]"
            )

        if random() < reply_probability:
            await self.willing_manager.before_generate_reply_handle(message_data.get("message_id"))
            await self._observe(message_data = message_data)

        # 意愿管理器：注销当前message信息 (无论是否回复，只要处理过就删除)
        self.willing_manager.delete(message_data.get("message_id"))
        
        return True
        
        
    async def _generate_normal_response(
        self, message_data: dict, available_actions: Optional[list]
    ) -> Optional[list]:
        """生成普通回复"""
        try:
            person_info_manager = get_person_info_manager()
            person_id = person_info_manager.get_person_id(
                message_data.get("chat_info_platform"), message_data.get("user_id")
            )
            person_name = await person_info_manager.get_value(person_id, "person_name")
            reply_to_str = f"{person_name}:{message_data.get('processed_plain_text')}"

            success, reply_set = await generator_api.generate_reply(
                chat_stream=self.chat_stream,
                reply_to=reply_to_str,
                available_actions=available_actions,
                enable_tool=global_config.tool.enable_in_normal_chat,
                request_type="normal.replyer",
            )

            if not success or not reply_set:
                logger.info(f"对 {message_data.get('processed_plain_text')} 的回复生成失败")
                return None

            return reply_set

        except Exception as e:
            logger.error(f"[{self.log_prefix}] 回复生成出现错误：{str(e)} {traceback.format_exc()}")
            return None
    

    def _get_fatigue_reply_multiplier(self) -> float:
        """获取疲劳期回复频率调整系数

        Returns:
            float: 回复频率调整系数，范围0.5-1.0
        """
        if not self.get_cooldown_progress_callback:
            return 1.0  # 没有冷却进度回调，返回正常系数

        try:
            cooldown_progress = self.get_cooldown_progress_callback()

            if cooldown_progress >= 1.0:
                return 1.0  # 冷却完成，正常回复频率

            # 疲劳期间：从0.5逐渐恢复到1.0
            # progress=0时系数为0.5，progress=1时系数为1.0
            multiplier = 0.2 + (0.8 * cooldown_progress)

            return multiplier
        except Exception as e:
            logger.warning(f"[{self.log_prefix}] 获取疲劳调整系数时出错: {e}")
            return 1.0  # 出错时返回正常系数
        
    # async def _check_should_switch_to_focus(self) -> bool:
    #     """
    #     检查是否满足切换到focus模式的条件

    #     Returns:
    #         bool: 是否应该切换到focus模式
    #     """
    #     # 检查思考消息堆积情况
    #     container = await message_manager.get_container(self.stream_id)
    #     if container:
    #         thinking_count = sum(1 for msg in container.messages if isinstance(msg, MessageThinking))
    #         if thinking_count >= 4 * global_config.chat.auto_focus_threshold:  # 如果堆积超过阈值条思考消息
    #             logger.debug(f"[{self.stream_name}] 检测到思考消息堆积({thinking_count}条)，切换到focus模式")
    #             return True

    #     if not self.recent_replies:
    #         return False

    #     current_time = time.time()
    #     time_threshold = 120 / global_config.chat.auto_focus_threshold
    #     reply_threshold = 6 * global_config.chat.auto_focus_threshold

    #     one_minute_ago = current_time - time_threshold

    #     # 统计指定时间内的回复数量
    #     recent_reply_count = sum(1 for reply in self.recent_replies if reply["time"] > one_minute_ago)

    #     should_switch = recent_reply_count > reply_threshold
    #     if should_switch:
    #         logger.debug(
    #             f"[{self.stream_name}] 检测到{time_threshold:.0f}秒内回复数量({recent_reply_count})大于{reply_threshold}，满足切换到focus模式条件"
    #         )

    #     return should_switch