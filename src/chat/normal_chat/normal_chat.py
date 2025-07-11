import asyncio
import time
from random import random
from typing import List, Optional
from src.config.config import global_config
from src.common.logger import get_logger
from src.person_info.person_info import get_person_info_manager
from src.plugin_system.apis import generator_api
from maim_message import UserInfo, Seg
from src.chat.message_receive.chat_stream import ChatStream, get_chat_manager
from src.chat.utils.timer_calculator import Timer
from src.common.message_repository import count_messages
from src.chat.utils.prompt_builder import global_prompt_manager
from ..message_receive.message import MessageSending, MessageThinking, MessageSet, MessageRecv,message_from_db_dict
from src.chat.message_receive.normal_message_sender import message_manager
from src.chat.normal_chat.willing.willing_manager import get_willing_manager
from src.chat.planner_actions.action_manager import ActionManager
from src.person_info.relationship_builder_manager import relationship_builder_manager
from .priority_manager import PriorityManager
import traceback
from src.chat.planner_actions.planner import ActionPlanner
from src.chat.planner_actions.action_modifier import ActionModifier
from src.chat.utils.chat_message_builder import get_raw_msg_by_timestamp_with_chat_inclusive

from src.chat.utils.utils import get_chat_type_and_target_info
from src.mood.mood_manager import mood_manager

willing_manager = get_willing_manager()

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

        self.willing_amplifier = 1
        self.start_time = time.time()

        self.mood_manager = mood_manager
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

    async def disable(self):
        """停用 NormalChat 实例，停止所有后台任务"""
        self._disabled = True
        if self._chat_task and not self._chat_task.done():
            self._chat_task.cancel()
        if self.reply_mode == "priority" and self._priority_chat_task and not self._priority_chat_task.done():
            self._priority_chat_task.cancel()
        logger.info(f"[{self.stream_name}] NormalChat 已停用。")
        
    async def _interest_mode_loopbody(self):
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
                        self.adjust_reply_frequency()
                        await self.normal_response(
                            message_data=msg_data,
                            is_mentioned=msg_data.get("is_mentioned", False),
                            interested_rate=msg_data.get("interest_rate", 0.0) * self.willing_amplifier,
                        )
                        return True
                    except Exception as e:
                        logger.error(f"[{self.stream_name}] 处理消息时出错: {e} {traceback.format_exc()}")


        except asyncio.CancelledError:
            logger.info(f"[{self.stream_name}] 兴趣模式轮询任务被取消")
            return False
        except Exception:
            logger.error(f"[{self.stream_name}] 兴趣模式轮询循环出现错误: {traceback.format_exc()}", exc_info=True)
            await asyncio.sleep(10)
            
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

    async def _interest_message_polling_loop(self):
        """
        [Interest Mode] 通过轮询数据库获取新消息并直接处理。
        """
        logger.info(f"[{self.stream_name}] 兴趣模式消息轮询任务开始")
        try:
            while not self._disabled:
                success = await self._interest_mode_loopbody()
                
                if not success:
                    break

        except asyncio.CancelledError:
            logger.info(f"[{self.stream_name}] 兴趣模式消息轮询任务被优雅地取消了")




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

    # 改为实例方法
    async def _create_thinking_message(self, message_data: dict, timestamp: Optional[float] = None) -> str:
        """创建思考消息"""
        bot_user_info = UserInfo(
            user_id=global_config.bot.qq_account,
            user_nickname=global_config.bot.nickname,
            platform=message_data.get("chat_info_platform"),
        )

        thinking_time_point = round(time.time(), 2)
        thinking_id = "tid" + str(thinking_time_point)
        thinking_message = MessageThinking(
            message_id=thinking_id,
            chat_stream=self.chat_stream,
            bot_user_info=bot_user_info,
            reply=None,
            thinking_start_time=thinking_time_point,
            timestamp=timestamp if timestamp is not None else None,
        )

        await message_manager.add_message(thinking_message)
        return thinking_id

    # 改为实例方法
    async def _add_messages_to_manager(
        self, message_data: dict, response_set: List[str], thinking_id
    ) -> Optional[MessageSending]:
        """发送回复消息"""
        container = await message_manager.get_container(self.stream_id)  # 使用 self.stream_id
        thinking_message = None

        for msg in container.messages[:]:
            if isinstance(msg, MessageThinking) and msg.message_info.message_id == thinking_id:
                thinking_message = msg
                container.messages.remove(msg)
                break

        if not thinking_message:
            logger.warning(f"[{self.stream_name}] 未找到对应的思考消息 {thinking_id}，可能已超时被移除")
            return None

        thinking_start_time = thinking_message.thinking_start_time
        message_set = MessageSet(self.chat_stream, thinking_id)  # 使用 self.chat_stream

        sender_info = UserInfo(
            user_id=message_data.get("user_id"),
            user_nickname=message_data.get("user_nickname"),
            platform=message_data.get("chat_info_platform"),
        )
        
        reply = message_from_db_dict(message_data)
        

        mark_head = False
        first_bot_msg = None
        for msg in response_set:
            if global_config.debug.debug_show_chat_mode:
                msg += "ⁿ"
            message_segment = Seg(type="text", data=msg)
            bot_message = MessageSending(
                message_id=thinking_id,
                chat_stream=self.chat_stream,  # 使用 self.chat_stream
                bot_user_info=UserInfo(
                    user_id=global_config.bot.qq_account,
                    user_nickname=global_config.bot.nickname,
                    platform=message_data.get("chat_info_platform"),
                ),
                sender_info=sender_info,
                message_segment=message_segment,
                reply=reply,
                is_head=not mark_head,
                is_emoji=False,
                thinking_start_time=thinking_start_time,
                apply_set_reply_logic=True,
            )
            if not mark_head:
                mark_head = True
                first_bot_msg = bot_message
            message_set.add_message(bot_message)

        await message_manager.add_message(message_set)

        return first_bot_msg

    # 改为实例方法, 移除 chat 参数
    async def normal_response(self, message_data: dict, is_mentioned: bool, interested_rate: float) -> None:
        """
        处理接收到的消息。
        在"兴趣"模式下，判断是否回复并生成内容。
        """
        if self._disabled:
            return

        # 新增：在auto模式下检查是否需要直接切换到focus模式
        if global_config.chat.chat_mode == "auto":
            if await self._check_should_switch_to_focus():
                logger.info(f"[{self.stream_name}] 检测到切换到focus聊天模式的条件，尝试执行切换")
                if self.on_switch_to_focus_callback:
                    switched_successfully = await self.on_switch_to_focus_callback()
                    if switched_successfully:
                        logger.info(f"[{self.stream_name}] 成功切换到focus模式，中止NormalChat处理")
                        return
                    else:
                        logger.info(f"[{self.stream_name}] 切换到focus模式失败（可能在冷却中），继续NormalChat处理")
                else:
                    logger.warning(f"[{self.stream_name}] 没有设置切换到focus聊天模式的回调函数，无法执行切换")

        # --- 以下为 "兴趣" 模式逻辑 (从 _process_message 合并而来) ---
        timing_results = {}
        reply_probability = (
            1.0 if is_mentioned and global_config.normal_chat.mentioned_bot_inevitable_reply else 0.0
        )  # 如果被提及，且开启了提及必回复，则基础概率为1，否则需要意愿判断

        # 意愿管理器：设置当前message信息
        willing_manager.setup(message_data, self.chat_stream)
        # TODO: willing_manager 也需要修改以接收字典

        # 获取回复概率
        # is_willing = False
        # 仅在未被提及或基础概率不为1时查询意愿概率
        if reply_probability < 1:  # 简化逻辑，如果未提及 (reply_probability 为 0)，则获取意愿概率
            # is_willing = True
            reply_probability = await willing_manager.get_reply_probability(message_data.get("message_id"))

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
                f"[{self.stream_name}] 疲劳期回复频率调整: {original_probability * 100:.1f}% -> {reply_probability * 100:.1f}% (系数: {fatigue_multiplier:.2f})"
            )

        # 打印消息信息
        mes_name = self.chat_stream.group_info.group_name if self.chat_stream.group_info else "私聊"
        if reply_probability > 0.1:
            logger.info(
                f"[{mes_name}]"
                f"{message_data.get('user_nickname')}:"
                f"{message_data.get('processed_plain_text')}[兴趣:{interested_rate:.2f}][回复概率:{reply_probability * 100:.1f}%]"
            )
        do_reply = False
        response_set = None  # 初始化 response_set
        if random() < reply_probability:
            with Timer("获取回复", timing_results):
                await willing_manager.before_generate_reply_handle(message_data.get("message_id"))
                do_reply = await self.reply_one_message(message_data)
                response_set = do_reply if do_reply else None

        # 输出性能计时结果
        if do_reply and response_set:  # 确保 response_set 不是 None
            timing_str = " | ".join([f"{step}: {duration:.2f}秒" for step, duration in timing_results.items()])
            trigger_msg = message_data.get("processed_plain_text")
            response_msg = " ".join([item[1] for item in response_set if item[0] == "text"])
            logger.info(
                f"[{self.stream_name}]回复消息: {trigger_msg[:30]}... | 回复内容: {response_msg[:30]}... | 计时: {timing_str}"
            )
            await willing_manager.after_generate_reply_handle(message_data.get("message_id"))
        elif not do_reply:
            # 不回复处理
            await willing_manager.not_reply_handle(message_data.get("message_id"))

        # 意愿管理器：注销当前message信息 (无论是否回复，只要处理过就删除)
        willing_manager.delete(message_data.get("message_id"))

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
            logger.error(f"[{self.stream_name}] 回复生成出现错误：{str(e)} {traceback.format_exc()}")
            return None

    async def _plan_and_execute_actions(self, message_data: dict, thinking_id: str) -> Optional[dict]:
        """规划和执行额外动作"""
        no_action = {
            "action_result": {
                "action_type": "no_action",
                "action_data": {},
                "reasoning": "规划器初始化默认",
                "is_parallel": True,
            },
            "chat_context": "",
            "action_prompt": "",
        }

        if not self.enable_planner:
            logger.debug(f"[{self.stream_name}] Planner未启用，跳过动作规划")
            return no_action

        try:
            # 检查是否应该跳过规划
            if self.action_modifier.should_skip_planning():
                logger.debug(f"[{self.stream_name}] 没有可用动作，跳过规划")
                self.action_type = "no_action"
                return no_action

            # 执行规划
            plan_result = await self.planner.plan()
            action_type = plan_result["action_result"]["action_type"]
            action_data = plan_result["action_result"]["action_data"]
            reasoning = plan_result["action_result"]["reasoning"]
            is_parallel = plan_result["action_result"].get("is_parallel", False)

            if action_type == "no_action":
                logger.info(f"[{self.stream_name}] {global_config.bot.nickname} 决定进行回复")
            elif is_parallel:
                logger.info(
                    f"[{self.stream_name}] {global_config.bot.nickname} 决定进行回复, 同时执行{action_type}动作"
                )
            else:
                logger.info(f"[{self.stream_name}] {global_config.bot.nickname} 决定执行{action_type}动作")

            self.action_type = action_type  # 更新实例属性
            self.is_parallel_action = is_parallel  # 新增：保存并行执行标志

            # 如果规划器决定不执行任何动作
            if action_type == "no_action":
                logger.debug(f"[{self.stream_name}] Planner决定不执行任何额外动作")
                return no_action

            # 执行额外的动作（不影响回复生成）
            action_result = await self._execute_action(action_type, action_data, message_data, thinking_id)
            if action_result is not None:
                logger.info(f"[{self.stream_name}] 额外动作 {action_type} 执行完成")
            else:
                logger.warning(f"[{self.stream_name}] 额外动作 {action_type} 执行失败")

            return {
                "action_type": action_type,
                "action_data": action_data,
                "reasoning": reasoning,
                "is_parallel": is_parallel,
            }

        except Exception as e:
            logger.error(f"[{self.stream_name}] Planner执行失败: {e}")
            return no_action

    async def reply_one_message(self, message_data: dict) -> None:
        # 回复前处理
        await self.relationship_builder.build_relation()

        thinking_id = await self._create_thinking_message(message_data)

        # 如果启用planner，预先修改可用actions（避免在并行任务中重复调用）
        available_actions = None
        if self.enable_planner:
            try:
                await self.action_modifier.modify_actions(mode="normal", message_content=message_data.get("processed_plain_text"))
                available_actions = self.action_manager.get_using_actions_for_mode("normal")
            except Exception as e:
                logger.warning(f"[{self.stream_name}] 获取available_actions失败: {e}")
                available_actions = None

        # 并行执行回复生成和动作规划
        self.action_type = None  # 初始化动作类型
        self.is_parallel_action = False  # 初始化并行动作标志

        gen_task = asyncio.create_task(self._generate_normal_response(message_data, available_actions))
        plan_task = asyncio.create_task(self._plan_and_execute_actions(message_data, thinking_id))

        try:
            gather_timeout = global_config.chat.thinking_timeout
            results = await asyncio.wait_for(
                asyncio.gather(gen_task, plan_task, return_exceptions=True),
                timeout=gather_timeout,
            )
            response_set, plan_result = results
        except asyncio.TimeoutError:
            gen_timed_out = not gen_task.done()
            plan_timed_out = not plan_task.done()

            timeout_details = []
            if gen_timed_out:
                timeout_details.append("回复生成(gen)")
            if plan_timed_out:
                timeout_details.append("动作规划(plan)")

            timeout_source = " 和 ".join(timeout_details)

            logger.warning(
                f"[{self.stream_name}] {timeout_source} 任务超时 ({global_config.chat.thinking_timeout}秒)，正在取消相关任务..."
            )
            # print(f"111{self.timeout_count}")
            self.timeout_count += 1
            if self.timeout_count > 5:
                logger.warning(
                    f"[{self.stream_name}] 连续回复超时次数过多，{global_config.chat.thinking_timeout}秒 内大模型没有返回有效内容，请检查你的api是否速度过慢或配置错误。建议不要使用推理模型，推理模型生成速度过慢。或者尝试拉高thinking_timeout参数，这可能导致回复时间过长。"
                )

            # 取消未完成的任务
            if not gen_task.done():
                gen_task.cancel()
            if not plan_task.done():
                plan_task.cancel()

            # 清理思考消息
            await self._cleanup_thinking_message_by_id(thinking_id)

            response_set = None
            plan_result = None

        # 处理生成回复的结果
        if isinstance(response_set, Exception):
            logger.error(f"[{self.stream_name}] 回复生成异常: {response_set}")
            response_set = None

        # 处理规划结果（可选，不影响回复）
        if isinstance(plan_result, Exception):
            logger.error(f"[{self.stream_name}] 动作规划异常: {plan_result}")
        elif plan_result:
            logger.debug(f"[{self.stream_name}] 额外动作处理完成: {self.action_type}")

        if response_set:
            content = " ".join([item[1] for item in response_set if item[0] == "text"])

        if not response_set or (
            self.enable_planner and self.action_type not in ["no_action"] and not self.is_parallel_action
        ):
            if not response_set:
                logger.warning(f"[{self.stream_name}] 模型未生成回复内容")
            elif self.enable_planner and self.action_type not in ["no_action"] and not self.is_parallel_action:
                logger.info(
                    f"[{self.stream_name}] {global_config.bot.nickname} 原本想要回复：{content}，但选择执行{self.action_type}，不发表回复"
                )
            # 如果模型未生成回复，移除思考消息
            await self._cleanup_thinking_message_by_id(thinking_id)
            return False

        logger.info(f"[{self.stream_name}] {global_config.bot.nickname} 决定的回复内容: {content}")

        if self._disabled:
            logger.info(f"[{self.stream_name}] 已停用，忽略 normal_response。")
            return False

        # 提取回复文本
        reply_texts = [item[1] for item in response_set if item[0] == "text"]
        if not reply_texts:
            logger.info(f"[{self.stream_name}] 回复内容中没有文本，不发送消息")
            await self._cleanup_thinking_message_by_id(thinking_id)
            return False

        # 发送回复 (不再需要传入 chat)
        first_bot_msg = await self._add_messages_to_manager(message_data, reply_texts, thinking_id)

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
            if len(self.recent_replies) > self.max_replies_history:
                self.recent_replies = self.recent_replies[-self.max_replies_history :]
        return response_set if response_set else False

    # 改为实例方法, 移除 chat 参数

    async def start_chat(self):
        """启动聊天任务。"""
        # 重置停用标志
        self._disabled = False

        # 检查是否已有运行中的任务
        if self._chat_task and not self._chat_task.done():
            logger.info(f"[{self.stream_name}] 聊天轮询任务已在运行中。")
            return

        # 清理可能存在的已完成任务引用
        if self._chat_task and self._chat_task.done():
            self._chat_task = None
        if self._priority_chat_task and self._priority_chat_task.done():
            self._priority_chat_task = None

        try:
            logger.info(f"[{self.stream_name}] 创建新的聊天轮询任务，模式: {self.reply_mode}")

            if self.reply_mode == "priority":
                # Start producer loop
                producer_task = asyncio.create_task(self._priority_message_producer_loop())
                self._chat_task = producer_task
                self._chat_task.add_done_callback(lambda t: self._handle_task_completion(t, "priority_producer"))

                # Start consumer loop
                consumer_task = asyncio.create_task(self._priority_chat_loop())
                self._priority_chat_task = consumer_task
                self._priority_chat_task.add_done_callback(lambda t: self._handle_task_completion(t, "priority_consumer"))
            else:  # Interest mode
                polling_task = asyncio.create_task(self._interest_message_polling_loop())
                self._chat_task = polling_task
                self._chat_task.add_done_callback(lambda t: self._handle_task_completion(t, "interest_polling"))

            self.running = True

            logger.debug(f"[{self.stream_name}] 聊天任务启动完成")

        except Exception as e:
            logger.error(f"[{self.stream_name}] 启动聊天任务失败: {e}")
            self._chat_task = None
            self._priority_chat_task = None
            raise

    def _handle_task_completion(self, task: asyncio.Task, task_name: str = "unknown"):
        """任务完成回调处理"""
        try:
            logger.debug(f"[{self.stream_name}] 任务 '{task_name}' 完成回调被调用")

            if task is self._chat_task:
                self._chat_task = None
            elif task is self._priority_chat_task:
                self._priority_chat_task = None
            else:
                logger.debug(f"[{self.stream_name}] 回调的任务 '{task_name}' 不是当前管理的任务")
                return

            logger.debug(f"[{self.stream_name}] 任务 '{task_name}' 引用已清理")

            if task.cancelled():
                logger.debug(f"[{self.stream_name}] 任务 '{task_name}' 已取消")
            elif task.done():
                exc = task.exception()
                if exc:
                    logger.error(f"[{self.stream_name}] 任务 '{task_name}' 异常: {type(exc).__name__}: {exc}", exc_info=exc)
                else:
                    logger.debug(f"[{self.stream_name}] 任务 '{task_name}' 正常完成")

        except Exception as e:
            logger.error(f"[{self.stream_name}] 任务完成回调处理出错: {e}")
            self._chat_task = None
            self._priority_chat_task = None

    # 改为实例方法, 移除 stream_id 参数
    async def stop_chat(self):
        """停止当前实例的兴趣监控任务。"""
        logger.debug(f"[{self.stream_name}] 开始停止聊天任务")

        self._disabled = True

        if self._chat_task and not self._chat_task.done():
            self._chat_task.cancel()
        if self._priority_chat_task and not self._priority_chat_task.done():
            self._priority_chat_task.cancel()

        self._chat_task = None
        self._priority_chat_task = None

        asyncio.create_task(self._cleanup_thinking_messages_async())

    async def _cleanup_thinking_messages_async(self):
        """异步清理思考消息，避免阻塞主流程"""
        try:
            await asyncio.sleep(0.1)

            container = await message_manager.get_container(self.stream_id)
            if container:
                thinking_messages = [msg for msg in container.messages[:] if isinstance(msg, MessageThinking)]
                if thinking_messages:
                    for msg in thinking_messages:
                        container.messages.remove(msg)
                    logger.info(f"[{self.stream_name}] 清理了 {len(thinking_messages)} 条未处理的思考消息。")
        except Exception as e:
            logger.error(f"[{self.stream_name}] 异步清理思考消息时出错: {e}")

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
            logger.debug(f"[{self.stream_name}] 目标回复频率为0或负数，不调整意愿放大器。")
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
                f"[{self.stream_name}] 回复增益被抑制。最近5分钟内回复数 ({bot_reply_count_5_min}) "
                f"> 阈值 ({suppression_threshold:.1f})。意愿放大器保持在 {self.willing_amplifier:.2f}"
            )
            # 不做任何改动
        else:
            # 限制最终值在 [0.2, 5.0] 范围内
            self.willing_amplifier = max(0.2, min(5.0, new_amplifier))
            logger.debug(
                f"[{self.stream_name}] 调整回复意愿。10分钟内回复: {bot_reply_count_10_min} (目标: {target_replies_in_window:.0f}) -> "
                f"意愿放大器更新为: {self.willing_amplifier:.2f}"
            )

    async def _execute_action(
        self, action_type: str, action_data: dict, message_data: dict, thinking_id: str
    ) -> Optional[bool]:
        """执行具体的动作，只返回执行成功与否"""
        try:
            # 创建动作处理器实例
            action_handler = self.action_manager.create_action(
                action_name=action_type,
                action_data=action_data,
                reasoning=action_data.get("reasoning", ""),
                cycle_timers={},  # normal_chat使用空的cycle_timers
                thinking_id=thinking_id,
                chat_stream=self.chat_stream,
                log_prefix=self.stream_name,
                shutting_down=self._disabled,
            )

            if action_handler:
                # 执行动作
                result = await action_handler.handle_action()
                success = False

                if result and isinstance(result, tuple) and len(result) >= 2:
                    # handle_action返回 (success: bool, message: str)
                    success = result[0]
                elif result:
                    # 如果返回了其他结果，假设成功
                    success = True

                return success

        except Exception as e:
            logger.error(f"[{self.stream_name}] 执行动作 {action_type} 失败: {e}")

        return False

    def get_action_manager(self) -> ActionManager:
        """获取动作管理器实例"""
        return self.action_manager

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
            logger.warning(f"[{self.stream_name}] 获取疲劳调整系数时出错: {e}")
            return 1.0  # 出错时返回正常系数

    async def _check_should_switch_to_focus(self) -> bool:
        """
        检查是否满足切换到focus模式的条件

        Returns:
            bool: 是否应该切换到focus模式
        """
        # 检查思考消息堆积情况
        container = await message_manager.get_container(self.stream_id)
        if container:
            thinking_count = sum(1 for msg in container.messages if isinstance(msg, MessageThinking))
            if thinking_count >= 4 * global_config.chat.auto_focus_threshold:  # 如果堆积超过阈值条思考消息
                logger.debug(f"[{self.stream_name}] 检测到思考消息堆积({thinking_count}条)，切换到focus模式")
                return True

        if not self.recent_replies:
            return False

        current_time = time.time()
        time_threshold = 120 / global_config.chat.auto_focus_threshold
        reply_threshold = 6 * global_config.chat.auto_focus_threshold

        one_minute_ago = current_time - time_threshold

        # 统计指定时间内的回复数量
        recent_reply_count = sum(1 for reply in self.recent_replies if reply["time"] > one_minute_ago)

        should_switch = recent_reply_count > reply_threshold
        if should_switch:
            logger.debug(
                f"[{self.stream_name}] 检测到{time_threshold:.0f}秒内回复数量({recent_reply_count})大于{reply_threshold}，满足切换到focus模式条件"
            )

        return should_switch

    async def _cleanup_thinking_message_by_id(self, thinking_id: str):
        """根据ID清理思考消息"""
        try:
            container = await message_manager.get_container(self.stream_id)
            if container:
                for msg in container.messages[:]:
                    if isinstance(msg, MessageThinking) and msg.message_info.message_id == thinking_id:
                        container.messages.remove(msg)
                        logger.info(f"[{self.stream_name}] 已清理思考消息 {thinking_id}")
                        break
        except Exception as e:
            logger.error(f"[{self.stream_name}] 清理思考消息 {thinking_id} 时出错: {e}")


def get_recent_message_stats(minutes: int = 30, chat_id: str = None) -> dict:
    """
    Args:
        minutes (int): 检索的分钟数，默认30分钟
        chat_id (str, optional): 指定的chat_id，仅统计该chat下的消息。为None时统计全部。
    Returns:
        dict: {"bot_reply_count": int, "total_message_count": int}
    """

    now = time.time()
    start_time = now - minutes * 60
    bot_id = global_config.bot.qq_account

    filter_base = {"time": {"$gte": start_time}}
    if chat_id is not None:
        filter_base["chat_id"] = chat_id

    # 总消息数
    total_message_count = count_messages(filter_base)
    # bot自身回复数
    bot_filter = filter_base.copy()
    bot_filter["user_id"] = bot_id
    bot_reply_count = count_messages(bot_filter)

    return {"bot_reply_count": bot_reply_count, "total_message_count": total_message_count}
