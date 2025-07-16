import asyncio
import time
import traceback
import random
from typing import List, Optional, Dict, Any
from rich.traceback import install

from src.config.config import global_config
from src.common.logger import get_logger
from src.chat.message_receive.chat_stream import ChatStream, get_chat_manager
from src.chat.utils.prompt_builder import global_prompt_manager
from src.chat.utils.timer_calculator import Timer
from src.chat.utils.chat_message_builder import get_raw_msg_by_timestamp_with_chat
from src.chat.planner_actions.planner import ActionPlanner
from src.chat.planner_actions.action_modifier import ActionModifier
from src.chat.planner_actions.action_manager import ActionManager
from src.chat.focus_chat.hfc_utils import CycleDetail
from src.chat.focus_chat.hfc_utils import get_recent_message_stats
from src.person_info.relationship_builder_manager import relationship_builder_manager
from src.person_info.person_info import get_person_info_manager
from src.plugin_system.base.component_types import ActionInfo, ChatMode
from src.plugin_system.apis import generator_api, send_api, message_api
from src.chat.willing.willing_manager import get_willing_manager
from ...mais4u.mais4u_chat.priority_manager import PriorityManager


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

        self.loop_mode = ChatMode.NORMAL  # 初始循环模式为普通模式

        # 新增：消息计数器和疲惫阈值
        self._message_count = 0  # 发送的消息计数
        self._message_threshold = max(10, int(30 * global_config.chat.focus_value))
        self._fatigue_triggered = False  # 是否已触发疲惫退出

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

        self.willing_amplifier = 1
        self.willing_manager = get_willing_manager()

        self.reply_mode = self.chat_stream.context.get_priority_mode()
        if self.reply_mode == "priority":
            self.priority_manager = PriorityManager(
                normal_queue_max_size=5,
            )
            self.loop_mode = ChatMode.PRIORITY
        else:
            self.priority_manager = None

        logger.info(f"{self.log_prefix} HeartFChatting 初始化完成")

        self.energy_value = 100

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
            await asyncio.sleep(1)
            if self.loop_mode == ChatMode.NORMAL:
                self.energy_value -= 1
                if self.energy_value <= 0:
                    self.energy_value = 0

    def print_cycle_info(self, cycle_timers):
        # 记录循环信息和计时器结果
        timer_strings = []
        for name, elapsed in cycle_timers.items():
            formatted_time = f"{elapsed * 1000:.2f}毫秒" if elapsed < 1 else f"{elapsed:.2f}秒"
            timer_strings.append(f"{name}: {formatted_time}")

        logger.info(
            f"{self.log_prefix} 第{self._current_cycle_detail.cycle_id}次思考,"
            f"耗时: {self._current_cycle_detail.end_time - self._current_cycle_detail.start_time:.1f}秒, "  # type: ignore
            f"选择动作: {self._current_cycle_detail.loop_plan_info.get('action_result', {}).get('action_type', '未知动作')}"
            + (f"\n详情: {'; '.join(timer_strings)}" if timer_strings else "")
        )

    async def _loopbody(self):
        if self.loop_mode == ChatMode.FOCUS:
            if await self._observe():
                self.energy_value -= 1 * global_config.chat.focus_value
            else:
                self.energy_value -= 3 * global_config.chat.focus_value
            if self.energy_value <= 0:
                self.energy_value = 0
                self.loop_mode = ChatMode.NORMAL
                return True

            return False
        elif self.loop_mode == ChatMode.NORMAL:
            new_messages_data = get_raw_msg_by_timestamp_with_chat(
                chat_id=self.stream_id,
                timestamp_start=self.last_read_time,
                timestamp_end=time.time(),
                limit=10,
                limit_mode="earliest",
                filter_bot=True,
            )

            if len(new_messages_data) > 3 * global_config.chat.focus_value:
                self.loop_mode = ChatMode.FOCUS
                self.energy_value =  10 + (new_messages_data / (3 * global_config.chat.focus_value)) * 10
                return True
            
            if self.energy_value >= 30 * global_config.chat.focus_value:
                self.loop_mode = ChatMode.FOCUS
                return True

            if new_messages_data:
                earliest_messages_data = new_messages_data[0]
                self.last_read_time = earliest_messages_data.get("time")

                if_think = await self.normal_response(earliest_messages_data)
                if if_think:
                    self.energy_value *= 1.1 / (global_config.chat.focus_value + 0.2)
                    logger.info(f"{self.log_prefix} 麦麦进行了思考，能量值增加1，当前能量值：{self.energy_value}")
                return False

            await asyncio.sleep(1)

            return True

    async def build_reply_to_str(self, message_data: dict):
        person_info_manager = get_person_info_manager()
        person_id = person_info_manager.get_person_id(
            message_data.get("chat_info_platform"),  # type: ignore
            message_data.get("user_id"),  # type: ignore
        )
        person_name = await person_info_manager.get_value(person_id, "person_name")
        return f"{person_name}:{message_data.get('processed_plain_text')}"

    async def _observe(self, message_data: Optional[Dict[str, Any]] = None):
        if not message_data:
            message_data = {}
        action_type = "no_action"
        # 创建新的循环信息
        cycle_timers, thinking_id = self.start_cycle()

        logger.info(f"{self.log_prefix} 开始第{self._cycle_counter}次思考[模式：{self.loop_mode}]")

        async with global_prompt_manager.async_message_scope(self.chat_stream.context.get_template_name()):
            loop_start_time = time.time()
            await self.relationship_builder.build_relation()

            available_actions = {}

            # 第一步：动作修改
            with Timer("动作修改", cycle_timers):
                try:
                    await self.action_modifier.modify_actions()
                    available_actions = self.action_manager.get_using_actions()
                except Exception as e:
                    logger.error(f"{self.log_prefix} 动作修改失败: {e}")

            # 如果normal，开始一个回复生成进程，先准备好回复（其实是和planer同时进行的）
            if self.loop_mode == ChatMode.NORMAL:
                reply_to_str = await self.build_reply_to_str(message_data)
                gen_task = asyncio.create_task(self._generate_response(message_data, available_actions, reply_to_str))

            with Timer("规划器", cycle_timers):
                plan_result, target_message = await self.action_planner.plan(mode=self.loop_mode)

            action_result: dict = plan_result.get("action_result", {})  # type: ignore
            action_type, action_data, reasoning, is_parallel = (
                action_result.get("action_type", "error"),
                action_result.get("action_data", {}),
                action_result.get("reasoning", "未提供理由"),
                action_result.get("is_parallel", True),
            )

            action_data["loop_start_time"] = loop_start_time

            if self.loop_mode == ChatMode.NORMAL:
                if action_type == "no_action":
                    logger.info(f"[{self.log_prefix}] {global_config.bot.nickname} 决定进行回复")
                elif is_parallel:
                    logger.info(
                        f"[{self.log_prefix}] {global_config.bot.nickname} 决定进行回复, 同时执行{action_type}动作"
                    )
                else:
                    logger.info(f"[{self.log_prefix}] {global_config.bot.nickname} 决定执行{action_type}动作")

            if action_type == "no_action":
                # 等待回复生成完毕
                gather_timeout = global_config.chat.thinking_timeout
                try:
                    response_set = await asyncio.wait_for(gen_task, timeout=gather_timeout)
                except asyncio.TimeoutError:
                    response_set = None

                if response_set:
                    content = " ".join([item[1] for item in response_set if item[0] == "text"])

                # 模型炸了，没有回复内容生成
                if not response_set:
                    logger.warning(f"[{self.log_prefix}] 模型未生成回复内容")
                    return False
                elif action_type not in ["no_action"] and not is_parallel:
                    logger.info(
                        f"[{self.log_prefix}] {global_config.bot.nickname} 原本想要回复：{content}，但选择执行{action_type}，不发表回复"
                    )
                    return False

                logger.info(f"[{self.log_prefix}] {global_config.bot.nickname} 决定的回复内容: {content}")

                # 发送回复 (不再需要传入 chat)
                await self._send_response(response_set, reply_to_str, loop_start_time)

                return True

            else:
                
                if message_data:
                    action_message = message_data
                else:
                    action_message = target_message
                # 动作执行计时
                
                
                with Timer("动作执行", cycle_timers):
                    success, reply_text, command = await self._handle_action(
                        action_type, reasoning, action_data, cycle_timers, thinking_id, action_message
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
                    # 停止该聊天模式的循环

        self.end_cycle(loop_info, cycle_timers)
        self.print_cycle_info(cycle_timers)

        if self.loop_mode == ChatMode.NORMAL:
            await self.willing_manager.after_generate_reply_handle(message_data.get("message_id", ""))

        if action_type != "no_reply" and action_type != "no_action":
            return True
        
        return True

    async def _main_chat_loop(self):
        """主循环，持续进行计划并可能回复消息，直到被外部取消。"""
        try:
            while self.running:  # 主循环
                success = await self._loopbody()
                await asyncio.sleep(0.1)
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
            reply_probability = await self.willing_manager.get_reply_probability(message_data.get("message_id", ""))

            additional_config = message_data.get("additional_config", {})
            if additional_config and "maimcore_reply_probability_gain" in additional_config:
                reply_probability += additional_config["maimcore_reply_probability_gain"]
                reply_probability = min(max(reply_probability, 0), 1)  # 确保概率在 0-1 之间

        # 处理表情包
        if message_data.get("is_emoji") or message_data.get("is_picid"):
            reply_probability = 0

        # 打印消息信息
        mes_name = self.chat_stream.group_info.group_name if self.chat_stream.group_info else "私聊"
        if reply_probability > 0.1:
            logger.info(
                f"[{mes_name}]"
                f"{message_data.get('user_nickname')}:"
                f"{message_data.get('processed_plain_text')}[兴趣:{interested_rate:.2f}][回复概率:{reply_probability * 100:.1f}%]"
            )
            
        talk_frequency = global_config.chat.get_current_talk_frequency(self.stream_id)
        reply_probability = talk_frequency * reply_probability

        if random.random() < reply_probability:
            await self.willing_manager.before_generate_reply_handle(message_data.get("message_id", ""))
            await self._observe(message_data=message_data)
            return True
            

        # 意愿管理器：注销当前message信息 (无论是否回复，只要处理过就删除)
        return False
        self.willing_manager.delete(message_data.get("message_id", ""))

    async def _generate_response(
        self, message_data: dict, available_actions: Optional[Dict[str, ActionInfo]], reply_to: str
    ) -> Optional[list]:
        """生成普通回复"""
        try:
            success, reply_set, _ = await generator_api.generate_reply(
                chat_stream=self.chat_stream,
                reply_to=reply_to,
                available_actions=available_actions,
                enable_tool=global_config.tool.enable_in_normal_chat,
                request_type="chat.replyer.normal",
            )

            if not success or not reply_set:
                logger.info(f"对 {message_data.get('processed_plain_text')} 的回复生成失败")
                return None

            return reply_set

        except Exception as e:
            logger.error(f"[{self.log_prefix}] 回复生成出现错误：{str(e)} {traceback.format_exc()}")
            return None

    async def _send_response(self, reply_set, reply_to, thinking_start_time):
        current_time = time.time()
        new_message_count = message_api.count_new_messages(
            chat_id=self.chat_stream.stream_id, start_time=thinking_start_time, end_time=current_time
        )

        need_reply = new_message_count >= random.randint(2, 4)

        logger.info(
            f"{self.log_prefix} 从思考到回复，共有{new_message_count}条新消息，{'使用' if need_reply else '不使用'}引用回复"
        )

        reply_text = ""
        first_replied = False
        for reply_seg in reply_set:
            data = reply_seg[1]
            if not first_replied:
                if need_reply:
                    await send_api.text_to_stream(
                        text=data, stream_id=self.chat_stream.stream_id, reply_to=reply_to, typing=False
                    )
                else:
                    await send_api.text_to_stream(text=data, stream_id=self.chat_stream.stream_id, typing=False)
                first_replied = True
            else:
                await send_api.text_to_stream(text=data, stream_id=self.chat_stream.stream_id, typing=True)
            reply_text += data

        return reply_text
