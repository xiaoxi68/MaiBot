import asyncio
import time
import random
from typing import Dict, Any, Optional, List
import functools  # <-- 新增导入

# 导入日志模块
from src.common.logger_manager import get_logger

# 导入聊天流管理模块
from src.plugins.chat.chat_stream import chat_manager

# 导入心流相关类
from src.heart_flow.sub_heartflow import SubHeartflow, ChatState
from src.heart_flow.mai_state_manager import MaiStateInfo
from .observation import ChattingObservation

# 导入LLM请求工具
from src.config.config import global_config


# 初始化日志记录器

logger = get_logger("subheartflow_manager")

# 子心流管理相关常量
NORMAL_CHAT_TIMEOUT_SECONDS = 30 * 60  # 30分钟


async def _try_set_subflow_absent_internal(subflow: "SubHeartflow", log_prefix: str) -> bool:
    """
    尝试将给定的子心流对象状态设置为 ABSENT (内部方法，不处理锁)。

    Args:
        subflow: 子心流对象。
        log_prefix: 用于日志记录的前缀 (例如 "[子心流管理]" 或 "[停用]")。

    Returns:
        bool: 如果状态成功变为 ABSENT 或原本就是 ABSENT，返回 True；否则返回 False。
    """
    flow_id = subflow.subheartflow_id
    stream_name = chat_manager.get_stream_name(flow_id) or flow_id

    if subflow.chat_state.chat_status != ChatState.ABSENT:
        logger.debug(f"{log_prefix} 设置 {stream_name} 状态为 ABSENT")
        try:
            await subflow.change_chat_state(ChatState.ABSENT)
            # 再次检查以确认状态已更改 (change_chat_state 内部应确保)
            if subflow.chat_state.chat_status == ChatState.ABSENT:
                return True
            else:
                logger.warning(
                    f"{log_prefix} 调用 change_chat_state 后，{stream_name} 状态仍为 {subflow.chat_state.chat_status.value}"
                )
                return False
        except Exception as e:
            logger.error(f"{log_prefix} 设置 {stream_name} 状态为 ABSENT 时失败: {e}", exc_info=True)
            return False
    else:
        logger.debug(f"{log_prefix} {stream_name} 已是 ABSENT 状态")
        return True  # 已经是目标状态，视为成功


class SubHeartflowManager:
    """管理所有活跃的 SubHeartflow 实例。"""

    def __init__(self, mai_state_info: MaiStateInfo):
        self.subheartflows: Dict[Any, "SubHeartflow"] = {}
        self._lock = asyncio.Lock()  # 用于保护 self.subheartflows 的访问
        self.mai_state_info: MaiStateInfo = mai_state_info  # 存储传入的 MaiStateInfo 实例

    async def force_change_state(self, subflow_id: Any, target_state: ChatState) -> bool:
        """强制改变指定子心流的状态"""
        async with self._lock:
            subflow = self.subheartflows.get(subflow_id)
            if not subflow:
                logger.warning(f"[强制状态转换]尝试转换不存在的子心流{subflow_id} 到 {target_state.value}")
                return False
            await subflow.change_chat_state(target_state)
            logger.info(f"[强制状态转换]子心流 {subflow_id} 已转换到 {target_state.value}")
            return True

    def get_all_subheartflows(self) -> List["SubHeartflow"]:
        """获取所有当前管理的 SubHeartflow 实例列表 (快照)。"""
        return list(self.subheartflows.values())

    async def get_or_create_subheartflow(self, subheartflow_id: Any) -> Optional["SubHeartflow"]:
        """获取或创建指定ID的子心流实例

        Args:
            subheartflow_id: 子心流唯一标识符
            mai_states 参数已被移除，使用 self.mai_state_info

        Returns:
            成功返回SubHeartflow实例，失败返回None
        """
        async with self._lock:
            # 检查是否已存在该子心流
            if subheartflow_id in self.subheartflows:
                subflow = self.subheartflows[subheartflow_id]
                if subflow.should_stop:
                    logger.warning(f"尝试获取已停止的子心流 {subheartflow_id}，正在重新激活")
                    subflow.should_stop = False  # 重置停止标志

                subflow.last_active_time = time.time()  # 更新活跃时间
                # logger.debug(f"获取到已存在的子心流: {subheartflow_id}")
                return subflow

            try:
                # --- 使用 functools.partial 创建 HFC 回调 --- #
                # 将 manager 的 _handle_hfc_no_reply 方法与当前的 subheartflow_id 绑定
                hfc_callback = functools.partial(self._handle_hfc_no_reply, subheartflow_id)
                # --- 结束创建回调 --- #

                # 初始化子心流, 传入 mai_state_info 和 partial 创建的回调
                new_subflow = SubHeartflow(
                    subheartflow_id,
                    self.mai_state_info,
                    hfc_callback,  # <-- 传递 partial 创建的回调
                )

                # 异步初始化
                await new_subflow.initialize()

                # 添加聊天观察者
                observation = ChattingObservation(chat_id=subheartflow_id)
                await observation.initialize()

                new_subflow.add_observation(observation)

                # 注册子心流
                self.subheartflows[subheartflow_id] = new_subflow
                heartflow_name = chat_manager.get_stream_name(subheartflow_id) or subheartflow_id
                logger.info(f"[{heartflow_name}] 开始接收消息")

                # 启动后台任务
                asyncio.create_task(new_subflow.subheartflow_start_working())

                return new_subflow
            except Exception as e:
                logger.error(f"创建子心流 {subheartflow_id} 失败: {e}", exc_info=True)
                return None

    async def sbhf_chat_into_focus(self):
        """评估子心流兴趣度，满足条件则提升到FOCUSED状态（基于start_hfc_probability）"""
        try:
            # --- 新增：检查是否允许进入 FOCUS 模式 --- #
            if not global_config.allow_focus_mode:
                if int(time.time()) % 60 == 0:  # 每60秒输出一次日志避免刷屏
                    logger.trace("未开启 FOCUSED 状态 (allow_focus_mode=False)")
                return  # 如果不允许，直接返回
            # --- 结束新增 ---

            for sub_hf in list(self.subheartflows.values()):
                flow_id = sub_hf.subheartflow_id
                stream_name = chat_manager.get_stream_name(flow_id) or flow_id

                # 跳过已经是FOCUSED状态的子心流
                if sub_hf.chat_state.chat_status == ChatState.FOCUSED:
                    continue

                if sub_hf.interest_chatting.start_hfc_probability == 0:
                    continue
                else:
                    logger.debug(
                        f"{stream_name}，现在状态: {sub_hf.chat_state.chat_status.value}，进入专注概率: {sub_hf.interest_chatting.start_hfc_probability}"
                    )

                if sub_hf.chat_state.chat_status != ChatState.CHAT:
                    continue

                if random.random() >= sub_hf.interest_chatting.start_hfc_probability:
                    continue

                # 获取最新状态并执行提升
                current_subflow = self.subheartflows.get(flow_id)
                if not current_subflow:
                    continue

                logger.info(
                    f"{stream_name} 触发 认真水群 (概率={current_subflow.interest_chatting.start_hfc_probability:.2f})"
                )

                # 执行状态提升
                await current_subflow.change_chat_state(ChatState.FOCUSED)
        except Exception as e:
            logger.error(f"启动HFC 兴趣评估失败: {e}", exc_info=True)

    async def sbhf_focus_into_chat(self):
        """检查FOCUSED状态的子心流是否需要转回CHAT状态"""
        focus_time_limit = 600  # 专注状态最多持续10分钟

        async with self._lock:
            # 筛选出所有FOCUSED状态的子心流
            focused_subflows = [
                hf for hf in self.subheartflows.values() 
                if hf.chat_state.chat_status == ChatState.FOCUSED
            ]

            if not focused_subflows:
                return

            for sub_hf in focused_subflows:
                flow_id = sub_hf.subheartflow_id
                stream_name = chat_manager.get_stream_name(flow_id) or flow_id
                log_prefix = f"[{stream_name}]"

                # 检查持续时间
                sub_hf.update_last_chat_state_time()
                time_in_state = sub_hf.chat_state_last_time

                # 10%概率随机转回CHAT，或者超过时间限制
                if time_in_state > focus_time_limit or random.random() < 0.2:
                    logger.info(f"{log_prefix} {'超过时间限制' if time_in_state > focus_time_limit else '随机'}从专注水群转为普通聊天")
                    await sub_hf.change_chat_state(ChatState.CHAT)

    # --- 新增：处理 HFC 无回复回调的专用方法 --- #
    async def _handle_hfc_no_reply(self, subheartflow_id: Any):
        """处理来自 HeartFChatting 的连续无回复信号 (通过 partial 绑定 ID)"""
        logger.debug(f"[管理器 HFC 处理器] 接收到来自 {subheartflow_id} 的 HFC 无回复信号")
        await self.sbhf_focus_into_chat_single(subheartflow_id)

    # --- 专用于处理单个子心流从FOCUSED转为CHAT的方法 --- #
    async def sbhf_focus_into_chat_single(self, subflow_id: Any):
        """将特定的FOCUSED状态子心流转为CHAT状态"""
        async with self._lock:
            subflow = self.subheartflows.get(subflow_id)
            if not subflow:
                logger.warning(f"[状态转换请求] 尝试转换不存在的子心流 {subflow_id}")
                return

            stream_name = chat_manager.get_stream_name(subflow_id) or subflow_id
            current_state = subflow.chat_state.chat_status

            if current_state == ChatState.FOCUSED:
                logger.info(f"[状态转换请求] 将 {stream_name} (当前: {current_state.value}) 转换为 CHAT")
                try:
                    # 从HFC到CHAT时，清空兴趣字典
                    subflow.clear_interest_dict()
                    await subflow.change_chat_state(ChatState.CHAT)
                    final_state = subflow.chat_state.chat_status
                    if final_state == ChatState.CHAT:
                        logger.debug(f"[状态转换请求] {stream_name} 状态已成功转换为 {final_state.value}")
                    else:
                        logger.warning(
                            f"[状态转换请求] 尝试将 {stream_name} 转换为 CHAT 后，状态实际为 {final_state.value}"
                        )
                except Exception as e:
                    logger.error(
                        f"[状态转换请求] 转换 {stream_name} 到 CHAT 时出错: {e}", exc_info=True
                    )
            else:
                logger.debug(f"[状态转换请求] {stream_name} 已处于 CHAT 状态，无需转换")

    def count_subflows_by_state(self, state: ChatState) -> int:
        """统计指定状态的子心流数量"""
        count = 0
        # 遍历所有子心流实例
        for subheartflow in self.subheartflows.values():
            # 检查子心流状态是否匹配
            if subheartflow.chat_state.chat_status == state:
                count += 1
        return count

    def count_subflows_by_state_nolock(self, state: ChatState) -> int:
        """
        统计指定状态的子心流数量 (不上锁版本)。
        警告：仅应在已持有 self._lock 的上下文中使用此方法。
        """
        count = 0
        for subheartflow in self.subheartflows.values():
            if subheartflow.chat_state.chat_status == state:
                count += 1
        return count

    def get_active_subflow_minds(self) -> List[str]:
        """获取所有子心流的当前想法"""
        minds = []
        for subheartflow in self.subheartflows.values():
            minds.append(subheartflow.sub_mind.current_mind)
        return minds

    def update_main_mind_in_subflows(self, main_mind: str):
        """更新所有子心流的主心流想法"""
        updated_count = sum(
            1
            for _, subheartflow in list(self.subheartflows.items())
            if subheartflow.subheartflow_id in self.subheartflows
        )
        logger.debug(f"[子心流管理器] 更新了{updated_count}个子心流的主想法")

    async def delete_subflow(self, subheartflow_id: Any):
        """删除指定的子心流。"""
        async with self._lock:
            subflow = self.subheartflows.pop(subheartflow_id, None)
            if subflow:
                logger.info(f"正在删除 SubHeartflow: {subheartflow_id}...")
                try:
                    # 调用 shutdown 方法确保资源释放
                    await subflow.shutdown()
                    logger.info(f"SubHeartflow {subheartflow_id} 已成功删除。")
                except Exception as e:
                    logger.error(f"删除 SubHeartflow {subheartflow_id} 时出错: {e}", exc_info=True)
            else:
                logger.warning(f"尝试删除不存在的 SubHeartflow: {subheartflow_id}")
