import asyncio
import time
from enum import Enum
from typing import Optional

from src.common.logger import get_logger
from src.plugin_system.apis import send_api

"""
视线管理系统使用说明：

1. 视线状态：
   - wandering: 随意看
   - danmu: 看弹幕
   - lens: 看镜头

2. 状态切换逻辑：
   - 收到消息时 → 切换为看弹幕，立即发送更新
   - 开始生成回复时 → 切换为看镜头或随意，立即发送更新  
   - 生成完毕后 → 看弹幕1秒，然后回到看镜头直到有新消息，状态变化时立即发送更新

3. 使用方法：
   # 获取视线管理器
   watching = watching_manager.get_watching_by_chat_id(chat_id)
   
   # 收到消息时调用
   await watching.on_message_received()
   
   # 开始生成回复时调用
   await watching.on_reply_start()
   
   # 生成回复完毕时调用
   await watching.on_reply_finished()

4. 自动更新系统：
   - 状态变化时立即发送type为"watching"，data为状态值的websocket消息
   - 使用定时器自动处理状态转换（如看弹幕时间结束后自动切换到看镜头）
   - 无需定期检查，所有状态变化都是事件驱动的
"""

logger = get_logger("watching")


class WatchingState(Enum):
    """视线状态枚举"""
    WANDERING = "wandering"  # 随意看
    DANMU = "danmu"         # 看弹幕
    LENS = "lens"           # 看镜头


class ChatWatching:
    def __init__(self, chat_id: str):
        self.chat_id: str = chat_id
        self.current_state: WatchingState = WatchingState.LENS  # 默认看镜头
        self.last_sent_state: Optional[WatchingState] = None    # 上次发送的状态
        self.state_needs_update: bool = True                    # 是否需要更新状态
        
        # 状态切换相关
        self.is_replying: bool = False                          # 是否正在生成回复
        self.reply_finished_time: Optional[float] = None        # 回复完成时间
        self.danmu_viewing_duration: float = 1.0               # 看弹幕持续时间（秒）
        
        logger.info(f"[{self.chat_id}] 视线管理器初始化，默认状态: {self.current_state.value}")

    async def _change_state(self, new_state: WatchingState, reason: str = ""):
        """内部状态切换方法"""
        if self.current_state != new_state:
            old_state = self.current_state
            self.current_state = new_state
            self.state_needs_update = True
            logger.info(f"[{self.chat_id}] 视线状态切换: {old_state.value} → {new_state.value} ({reason})")
            
            # 立即发送视线状态更新
            await self._send_watching_update()
        else:
            logger.debug(f"[{self.chat_id}] 状态无变化，保持: {new_state.value} ({reason})")

    async def on_message_received(self):
        """收到消息时调用"""
        if not self.is_replying:  # 只有在非回复状态下才切换到看弹幕
            await self._change_state(WatchingState.DANMU, "收到消息")
        else:
            logger.debug(f"[{self.chat_id}] 正在生成回复中，暂不切换到弹幕状态")

    async def on_reply_start(self, look_at_lens: bool = True):
        """开始生成回复时调用"""
        self.is_replying = True
        self.reply_finished_time = None
        
        if look_at_lens:
            await self._change_state(WatchingState.LENS, "开始生成回复-看镜头")
        else:
            await self._change_state(WatchingState.WANDERING, "开始生成回复-随意看")

    async def on_reply_finished(self):
        """生成回复完毕时调用"""
        self.is_replying = False
        self.reply_finished_time = time.time()
        
        # 先看弹幕1秒
        await self._change_state(WatchingState.DANMU, "回复完毕-看弹幕")
        logger.info(f"[{self.chat_id}] 回复完毕，将看弹幕{self.danmu_viewing_duration}秒后转为看镜头")
        
        # 设置定时器，1秒后自动切换到看镜头
        asyncio.create_task(self._auto_switch_to_lens())

    async def _auto_switch_to_lens(self):
        """自动切换到看镜头（延迟执行）"""
        await asyncio.sleep(self.danmu_viewing_duration)
        
        # 检查是否仍需要切换（可能状态已经被其他事件改变）
        if (self.reply_finished_time is not None and 
            self.current_state == WatchingState.DANMU and
            not self.is_replying):
            
            await self._change_state(WatchingState.LENS, "看弹幕时间结束")
            self.reply_finished_time = None  # 重置完成时间

    async def _send_watching_update(self):
        """立即发送视线状态更新"""
        await send_api.custom_to_stream(
            message_type="watching",
            content=self.current_state.value,
            stream_id=self.chat_id
        )
        
        logger.info(f"[{self.chat_id}] 发送视线状态更新: {self.current_state.value}")
        self.last_sent_state = self.current_state
        self.state_needs_update = False

    def get_current_state(self) -> WatchingState:
        """获取当前视线状态"""
        return self.current_state

    def get_state_info(self) -> dict:
        """获取状态信息（用于调试）"""
        return {
            "current_state": self.current_state.value,
            "is_replying": self.is_replying,
            "reply_finished_time": self.reply_finished_time,
            "state_needs_update": self.state_needs_update
        }



class WatchingManager:
    def __init__(self):
        self.watching_list: list[ChatWatching] = []
        """当前视线状态列表"""
        self.task_started: bool = False

    async def start(self):
        """启动视线管理系统"""
        if self.task_started:
            return

        logger.info("启动视线管理系统...")
        
        self.task_started = True
        logger.info("视线管理系统已启动（状态变化时立即发送）")

    def get_watching_by_chat_id(self, chat_id: str) -> ChatWatching:
        """获取或创建聊天对应的视线管理器"""
        for watching in self.watching_list:
            if watching.chat_id == chat_id:
                return watching

        new_watching = ChatWatching(chat_id)
        self.watching_list.append(new_watching)
        logger.info(f"为chat {chat_id}创建新的视线管理器")
        
        # 发送初始状态
        asyncio.create_task(new_watching._send_watching_update())
        
        return new_watching

    def reset_watching_by_chat_id(self, chat_id: str):
        """重置聊天的视线状态"""
        for watching in self.watching_list:
            if watching.chat_id == chat_id:
                watching.current_state = WatchingState.LENS
                watching.last_sent_state = None
                watching.state_needs_update = True
                watching.is_replying = False
                watching.reply_finished_time = None
                logger.info(f"[{chat_id}] 视线状态已重置为默认状态")
                
                # 发送重置后的状态
                asyncio.create_task(watching._send_watching_update())
                return
        
        # 如果没有找到现有的watching，创建新的
        new_watching = ChatWatching(chat_id)
        self.watching_list.append(new_watching)
        logger.info(f"为chat {chat_id}创建并重置视线管理器")
        
        # 发送初始状态
        asyncio.create_task(new_watching._send_watching_update())

    def get_all_watching_info(self) -> dict:
        """获取所有聊天的视线状态信息（用于调试）"""
        return {
            watching.chat_id: watching.get_state_info() 
            for watching in self.watching_list
        }


# 全局视线管理器实例
watching_manager = WatchingManager()
"""全局视线管理器""" 