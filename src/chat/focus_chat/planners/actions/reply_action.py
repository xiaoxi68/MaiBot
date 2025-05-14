from src.common.logger_manager import get_logger
from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
from src.chat.focus_chat.hfc_utils import create_empty_anchor_message
from src.chat.focus_chat.planners.actions.base_action import BaseAction
from typing import Tuple, List
from src.chat.focus_chat.heartFC_Cycleinfo import CycleDetail
from src.chat.message_receive.chat_stream import ChatStream
from src.chat.heart_flow.observation.observation import Observation
from src.chat.focus_chat.expressors.default_expressor import DefaultExpressor

logger = get_logger("action_taken")


class ReplyAction(BaseAction):
    """回复动作处理类

    处理发送回复消息的动作，包括文本和表情。
    """

    def __init__(
        self,
        action_name: str,
        action_data: dict,
        reasoning: str,
        cycle_timers: dict,
        thinking_id: str,
        observations: List[Observation],
        expressor: DefaultExpressor,
        chat_stream: ChatStream,
        current_cycle: CycleDetail,
        log_prefix: str,
    ):
        """初始化回复动作处理器

        Args:
            action_name: 动作名称
            action_data: 动作数据
            reasoning: 执行该动作的理由
            cycle_timers: 计时器字典
            thinking_id: 思考ID
            observations: 观察列表
            expressor: 表达器
            chat_stream: 聊天流
            current_cycle: 当前循环信息
            log_prefix: 日志前缀
        """
        super().__init__(action_name, action_data, reasoning, cycle_timers, thinking_id)
        self.observations = observations
        self.expressor = expressor
        self.chat_stream = chat_stream
        self._current_cycle = current_cycle
        self.log_prefix = log_prefix
        self.total_no_reply_count = 0
        self.total_waiting_time = 0.0

    async def handle_action(self) -> Tuple[bool, str]:
        """
        处理统一的回复动作 - 可包含文本和表情，顺序任意

        reply_data格式:
        {
            "text": "你好啊"  # 文本内容列表（可选）
            "target": "锚定消息",  # 锚定消息的文本内容
            "emojis": "微笑"  # 表情关键词列表（可选）
        }

        Returns:
            Tuple[bool, str]: (是否执行成功, 回复文本)
        """
        # 重置连续不回复计数器
        self.total_no_reply_count = 0
        self.total_waiting_time = 0.0

        # 从聊天观察获取锚定消息
        observations: ChattingObservation = self.observations[0]
        anchor_message = observations.serch_message_by_text(self.action_data["target"])

        # 如果没有找到锚点消息，创建一个占位符
        if not anchor_message:
            logger.info(f"{self.log_prefix} 未找到锚点消息，创建占位符")
            anchor_message = await create_empty_anchor_message(
                self.chat_stream.platform, self.chat_stream.group_info, self.chat_stream
            )
        else:
            anchor_message.update_chat_stream(self.chat_stream)

        success, reply_set = await self.expressor.deal_reply(
            cycle_timers=self.cycle_timers,
            action_data=self.action_data,
            anchor_message=anchor_message,
            reasoning=self.reasoning,
            thinking_id=self.thinking_id,
        )

        reply_text = ""
        for reply in reply_set:
            type = reply[0]
            data = reply[1]
            if type == "text":
                reply_text += data
            elif type == "emoji":
                reply_text += data

        return success, reply_text
