import asyncio
import contextlib
import time
import traceback
from collections import deque
from typing import List, Optional, Dict, Any, Deque, Callable, Awaitable
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
        on_stop_focus_chat: Optional[Callable[[], Awaitable[None]]] = None,
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

        # 存储回调函数
        self.on_stop_focus_chat = on_stop_focus_chat

        self.reply_timeout_count = 0
        self.plan_timeout_count = 0

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
        

    
    async def _focus_mode_loopbody(self):
        logger.info(f"{self.log_prefix} 开始第{self._cycle_counter}次循环")

        # 创建新的循环信息
        cycle_timers, thinking_id = self.start_cycle()

        # 执行规划和处理阶段
        try:
            async with global_prompt_manager.async_message_scope(
                self.chat_stream.context.get_template_name()
            ):

                loop_start_time = time.time()
                await self.loop_info.observe()
                await self.relationship_builder.build_relation()

                # 第一步：动作修改
                with Timer("动作修改", cycle_timers):
                    try:
                        await self.action_modifier.modify_actions(
                            loop_info=self.loop_info,
                            mode="focus",
                        )
                    except Exception as e:
                        logger.error(f"{self.log_prefix} 动作修改失败: {e}")

                with Timer("规划器", cycle_timers):
                    plan_result = await self.action_planner.plan()

                action_result = plan_result.get("action_result", {})
                action_type, action_data, reasoning = (
                    action_result.get("action_type", "error"),
                    action_result.get("action_data", {}),
                    action_result.get("reasoning", "未提供理由"),
                )

                action_data["loop_start_time"] = loop_start_time

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

            await asyncio.sleep(global_config.focus_chat.think_interval)
            
            return True
            
            
        except asyncio.CancelledError:
            logger.info(f"{self.log_prefix} focus循环任务被取消")
            return False
        except Exception as e:
            logger.error(f"{self.log_prefix} 循环处理时出错: {e}")
            logger.error(traceback.format_exc())
            
            # 如果_current_cycle_detail存在但未完成，为其设置错误状态
            if self._current_cycle_detail and not hasattr(self._current_cycle_detail, "end_time"):
                error_loop_info = ERROR_LOOP_INFO
                try:
                    self._current_cycle_detail.set_loop_info(error_loop_info)
                    self._current_cycle_detail.complete_cycle()
                except Exception as inner_e:
                    logger.error(f"{self.log_prefix} 设置错误状态时出错: {inner_e}")

            await asyncio.sleep(1)  # 出错后等待一秒再继续\
            return False
        
    
    async def _main_chat_loop(self):
        """主循环，持续进行计划并可能回复消息，直到被外部取消。"""
        try:
            loop_mode = "focus"
            loop_mode_loopbody = self._focus_mode_loopbody
            
            
            while self.running:  # 主循环
                success = await loop_mode_loopbody()
                if not success:
                    break
                
            logger.info(f"{self.log_prefix} 麦麦已强制离开 {loop_mode} 聊天模式")
                
                
        except asyncio.CancelledError:
            # 设置了关闭标志位后被取消是正常流程
            logger.info(f"{self.log_prefix} 麦麦已强制离开 {loop_mode} 聊天模式")
        except Exception as e:
            logger.error(f"{self.log_prefix} 麦麦 {loop_mode} 聊天模式意外错误: {e}")
            print(traceback.format_exc())

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

