import asyncio
import time
from typing import Optional
import traceback
from src.common.logger import get_logger
from src.chat.message_receive.chat_stream import get_chat_manager
from src.chat.focus_chat.heartFC_chat import HeartFChatting
from src.chat.utils.utils import get_chat_type_and_target_info
from src.config.config import global_config
from rich.traceback import install

logger = get_logger("sub_heartflow")

install(extra_lines=3)


class SubHeartflow:
    def __init__(
        self,
        subheartflow_id,
    ):
        """子心流初始化函数

        Args:
            subheartflow_id: 子心流唯一标识符
        """
        # 基础属性，两个值是一样的
        self.subheartflow_id = subheartflow_id
        self.chat_id = subheartflow_id


        self.is_group_chat, self.chat_target_info = get_chat_type_and_target_info(self.chat_id)
        self.log_prefix = get_chat_manager().get_stream_name(self.subheartflow_id) or self.subheartflow_id
        
        # focus模式退出冷却时间管理
        self.last_focus_exit_time: float = 0  # 上次退出focus模式的时间

        # 随便水群 normal_chat 和 认真水群 focus_chat 实例
        # CHAT模式激活 随便水群  FOCUS模式激活 认真水群
        self.heart_fc_instance: Optional[HeartFChatting] = HeartFChatting(
                    chat_id=self.subheartflow_id,
                )     # 该sub_heartflow的HeartFChatting实例

    async def initialize(self):
        """异步初始化方法，创建兴趣流并确定聊天类型"""
        await self.heart_fc_instance.start()




    async def _stop_heart_fc_chat(self):
        """停止并清理 HeartFChatting 实例"""
        if self.heart_fc_instance.running:
            logger.info(f"{self.log_prefix} 结束专注聊天...")
            try:
                await self.heart_fc_instance.shutdown()
            except Exception as e:
                logger.error(f"{self.log_prefix} 关闭 HeartFChatting 实例时出错: {e}")
                logger.error(traceback.format_exc())
        else:
            logger.info(f"{self.log_prefix} 没有专注聊天实例，无需停止专注聊天")

    async def _start_heart_fc_chat(self) -> bool:
        """启动 HeartFChatting 实例，确保 NormalChat 已停止"""
        try:
            # 如果任务已完成或不存在，则尝试重新启动
            if self.heart_fc_instance._loop_task is None or self.heart_fc_instance._loop_task.done():
                logger.info(f"{self.log_prefix} HeartFChatting 实例存在但循环未运行，尝试启动...")
                try:
                    # 添加超时保护
                    await asyncio.wait_for(self.heart_fc_instance.start(), timeout=15.0)
                    logger.info(f"{self.log_prefix} HeartFChatting 循环已启动。")
                    return True
                except Exception as e:
                    logger.error(f"{self.log_prefix} 尝试启动现有 HeartFChatting 循环时出错: {e}")
                    logger.error(traceback.format_exc())
                    # 出错时清理实例，准备重新创建
                    self.heart_fc_instance = None
            else:
                # 任务正在运行
                logger.debug(f"{self.log_prefix} HeartFChatting 已在运行中。")
                return True  # 已经在运行

        except Exception as e:
            logger.error(f"{self.log_prefix} _start_heart_fc_chat 执行时出错: {e}")
            logger.error(traceback.format_exc())
            return False
        

    def is_in_focus_cooldown(self) -> bool:
        """检查是否在focus模式的冷却期内

        Returns:
            bool: 如果在冷却期内返回True，否则返回False
        """
        if self.last_focus_exit_time == 0:
            return False

        # 基础冷却时间10分钟，受auto_focus_threshold调控
        base_cooldown = 10 * 60  # 10分钟转换为秒
        cooldown_duration = base_cooldown / global_config.chat.auto_focus_threshold

        current_time = time.time()
        elapsed_since_exit = current_time - self.last_focus_exit_time

        is_cooling = elapsed_since_exit < cooldown_duration

        if is_cooling:
            remaining_time = cooldown_duration - elapsed_since_exit
            remaining_minutes = remaining_time / 60
            logger.debug(
                f"[{self.log_prefix}] focus冷却中，剩余时间: {remaining_minutes:.1f}分钟 (阈值: {global_config.chat.auto_focus_threshold})"
            )

        return is_cooling

    def get_cooldown_progress(self) -> float:
        """获取冷却进度，返回0-1之间的值

        Returns:
            float: 0表示刚开始冷却，1表示冷却完成
        """
        if self.last_focus_exit_time == 0:
            return 1.0  # 没有冷却，返回1表示完全恢复

        # 基础冷却时间10分钟，受auto_focus_threshold调控
        base_cooldown = 10 * 60  # 10分钟转换为秒
        cooldown_duration = base_cooldown / global_config.chat.auto_focus_threshold

        current_time = time.time()
        elapsed_since_exit = current_time - self.last_focus_exit_time

        if elapsed_since_exit >= cooldown_duration:
            return 1.0  # 冷却完成

        # 计算进度：0表示刚开始冷却，1表示冷却完成
        progress = elapsed_since_exit / cooldown_duration
        return progress
