import asyncio

from manager.async_task_manager import AsyncTask, async_task_manager
from src.config.config import global_config
from .willing_manager import BaseWillingManager


class WillingDecayTask(AsyncTask):
    """
    回复意愿衰减任务
    定期衰减回复意愿
    """

    def __init__(self, willing_manager: BaseWillingManager):
        super().__init__(
            task_name="Willing Decay Task",
            wait_before_start=1,
            run_interval=1,
        )
        self.willing_manager = willing_manager

    async def run(self):
        for chat_id, reply_willing in self.willing_manager.chat_reply_willing.items():
            self.willing_manager.chat_reply_willing[chat_id] = max(0.0, reply_willing * 0.9)


class ClassicalWillingManager(BaseWillingManager):
    def __init__(self):
        super().__init__()
        self._decay_task: asyncio.Task | None = None

    async def async_task_starter(self):
        await async_task_manager.add_task(WillingDecayTask(self))  # 启动回复意愿衰减任务

    async def get_reply_probability(self, message_id):
        willing_info = self.ongoing_messages[message_id]
        chat_id = willing_info.chat_id
        current_willing = self.chat_reply_willing.get(chat_id, 0)

        interested_rate = willing_info.interested_rate * global_config.normal_chat.response_interested_rate_amplifier

        if interested_rate > 0.4:
            current_willing += interested_rate - 0.3

        if willing_info.is_mentioned_bot:
            current_willing += 1 if current_willing < 1.0 else 0.05

        is_emoji_not_reply = False
        if willing_info.is_emoji:
            if global_config.normal_chat.emoji_response_penalty != 0:
                current_willing *= global_config.normal_chat.emoji_response_penalty
            else:
                is_emoji_not_reply = True

        self.chat_reply_willing[chat_id] = min(current_willing, 3.0)

        reply_probability = min(
            max((current_willing - 0.5), 0.01) * global_config.normal_chat.response_willing_amplifier * 2, 1
        )

        # 检查群组权限（如果是群聊）
        if (
            willing_info.group_info
            and willing_info.group_info.group_id in global_config.normal_chat.talk_frequency_down_groups
        ):
            reply_probability = reply_probability / global_config.normal_chat.down_frequency_rate

        if is_emoji_not_reply:
            reply_probability = 0

        return reply_probability

    async def before_generate_reply_handle(self, message_id):
        chat_id = self.ongoing_messages[message_id].chat_id
        current_willing = self.chat_reply_willing.get(chat_id, 0)
        self.chat_reply_willing[chat_id] = max(0.0, current_willing - 1.8)

    async def after_generate_reply_handle(self, message_id):
        if message_id not in self.ongoing_messages:
            return

        chat_id = self.ongoing_messages[message_id].chat_id
        current_willing = self.chat_reply_willing.get(chat_id, 0)
        if current_willing < 1:
            self.chat_reply_willing[chat_id] = min(1.0, current_willing + 0.4)

    async def bombing_buffer_message_handle(self, message_id):
        return await super().bombing_buffer_message_handle(message_id)

    async def not_reply_handle(self, message_id):
        return await super().not_reply_handle(message_id)
