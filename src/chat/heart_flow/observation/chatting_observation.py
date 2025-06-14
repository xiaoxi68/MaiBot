from datetime import datetime
from src.config.config import global_config
from src.chat.utils.chat_message_builder import (
    get_raw_msg_before_timestamp_with_chat,
    build_readable_messages,
    get_raw_msg_by_timestamp_with_chat,
    num_new_messages_since,
    get_person_id_list,
)
from src.chat.utils.prompt_builder import global_prompt_manager, Prompt
from typing import Optional
import difflib
from src.chat.message_receive.message import MessageRecv
from src.chat.heart_flow.observation.observation import Observation
from src.common.logger import get_logger
from src.chat.heart_flow.utils_chat import get_chat_type_and_target_info

logger = get_logger("observation")

# 定义提示模板
Prompt(
    """这是qq群聊的聊天记录，请总结以下聊天记录的主题：
{chat_logs}
请概括这段聊天记录的主题和主要内容
主题：简短的概括，包括时间，人物和事件，不要超过20个字
内容：具体的信息内容，包括人物、事件和信息，不要超过200个字，不要分点。

请用json格式返回，格式如下：
{{
    "theme": "主题，例如 2025-06-14 10:00:00 群聊 麦麦 和 网友 讨论了 游戏 的话题",
    "content": "内容，可以是对聊天记录的概括，也可以是聊天记录的详细内容"
}}
""",
    "chat_summary_group_prompt",  # Template for group chat
)

Prompt(
    """这是你和{chat_target}的私聊记录，请总结以下聊天记录的主题：
{chat_logs}
请用一句话概括，包括事件，时间，和主要信息，不要分点。
主题：简短的介绍，不要超过10个字
内容：包括人物、事件和主要信息，不要分点。

请用json格式返回，格式如下：
{{
    "theme": "主题",
    "content": "内容"
}}""",
    "chat_summary_private_prompt",  # Template for private chat
)


class ChattingObservation(Observation):
    def __init__(self, chat_id):
        super().__init__(chat_id)
        self.chat_id = chat_id
        self.platform = "qq"

        self.is_group_chat, self.chat_target_info = get_chat_type_and_target_info(self.chat_id)

        self.talking_message = []
        self.talking_message_str = ""
        self.talking_message_str_truncate = ""
        self.name = global_config.bot.nickname
        self.nick_name = global_config.bot.alias_names
        self.max_now_obs_len = global_config.focus_chat.observation_context_size
        self.overlap_len = global_config.focus_chat.compressed_length
        self.person_list = []
        self.compressor_prompt = ""
        self.oldest_messages = []
        self.oldest_messages_str = ""

        initial_messages = get_raw_msg_before_timestamp_with_chat(self.chat_id, self.last_observe_time, 10)
        self.last_observe_time = initial_messages[-1]["time"] if initial_messages else self.last_observe_time
        self.talking_message = initial_messages
        self.talking_message_str = build_readable_messages(self.talking_message, show_actions=True)

    def to_dict(self) -> dict:
        """将观察对象转换为可序列化的字典"""
        return {
            "chat_id": self.chat_id,
            "platform": self.platform,
            "is_group_chat": self.is_group_chat,
            "chat_target_info": self.chat_target_info,
            "talking_message_str": self.talking_message_str,
            "talking_message_str_truncate": self.talking_message_str_truncate,
            "name": self.name,
            "nick_name": self.nick_name,
            "last_observe_time": self.last_observe_time,
        }

    def get_observe_info(self, ids=None):
        return self.talking_message_str

    def search_message_by_text(self, text: str) -> Optional[MessageRecv]:
        """
        根据回复的纯文本
        1. 在talking_message中查找最新的，最匹配的消息
        2. 如果找到，则返回消息
        """
        msg_list = []
        find_msg = None
        reverse_talking_message = list(reversed(self.talking_message))

        for message in reverse_talking_message:
            if message["processed_plain_text"] == text:
                find_msg = message
                break
            else:
                raw_message = message.get("raw_message")
                if raw_message:
                    similarity = difflib.SequenceMatcher(None, text, raw_message).ratio()
                else:
                    similarity = difflib.SequenceMatcher(None, text, message.get("processed_plain_text", "")).ratio()
                msg_list.append({"message": message, "similarity": similarity})

        if not find_msg:
            if msg_list:
                msg_list.sort(key=lambda x: x["similarity"], reverse=True)
                if msg_list[0]["similarity"] >= 0.9:
                    find_msg = msg_list[0]["message"]
                else:
                    logger.debug("没有找到锚定消息,相似度低")
                    return None
            else:
                logger.debug("没有找到锚定消息，没有消息捕获")
                return None

        user_info = {
            "platform": find_msg.get("user_platform", ""),
            "user_id": find_msg.get("user_id", ""),
            "user_nickname": find_msg.get("user_nickname", ""),
            "user_cardname": find_msg.get("user_cardname", ""),
        }

        group_info = {}
        if find_msg.get("chat_info_group_id"):
            group_info = {
                "platform": find_msg.get("chat_info_group_platform", ""),
                "group_id": find_msg.get("chat_info_group_id", ""),
                "group_name": find_msg.get("chat_info_group_name", ""),
            }

        content_format = ""
        accept_format = ""
        template_items = {}

        format_info = {"content_format": content_format, "accept_format": accept_format}
        template_info = {
            "template_items": template_items,
        }

        message_info = {
            "platform": self.platform,
            "message_id": find_msg.get("message_id"),
            "time": find_msg.get("time"),
            "group_info": group_info,
            "user_info": user_info,
            "additional_config": find_msg.get("additional_config"),
            "format_info": format_info,
            "template_info": template_info,
        }
        message_dict = {
            "message_info": message_info,
            "raw_message": find_msg.get("processed_plain_text"),
            "detailed_plain_text": find_msg.get("processed_plain_text"),
            "processed_plain_text": find_msg.get("processed_plain_text"),
        }
        find_rec_msg = MessageRecv(message_dict)
        return find_rec_msg

    async def observe(self):
        # 自上一次观察的新消息
        new_messages_list = get_raw_msg_by_timestamp_with_chat(
            chat_id=self.chat_id,
            timestamp_start=self.last_observe_time,
            timestamp_end=datetime.now().timestamp(),
            limit=self.max_now_obs_len,
            limit_mode="latest",
        )

        last_obs_time_mark = self.last_observe_time
        if new_messages_list:
            self.last_observe_time = new_messages_list[-1]["time"]
            self.talking_message.extend(new_messages_list)

        if len(self.talking_message) > self.max_now_obs_len:
            # 计算需要移除的消息数量，保留最新的 max_now_obs_len 条
            messages_to_remove_count = len(self.talking_message) - self.max_now_obs_len
            oldest_messages = self.talking_message[:messages_to_remove_count]
            self.talking_message = self.talking_message[messages_to_remove_count:]

            # 构建压缩提示
            oldest_messages_str = build_readable_messages(
                messages=oldest_messages, timestamp_mode="normal_no_YMD", read_mark=0, show_actions=True
            )

            # 根据聊天类型选择提示模板
            if self.is_group_chat:
                prompt_template_name = "chat_summary_group_prompt"
                prompt = await global_prompt_manager.format_prompt(prompt_template_name, chat_logs=oldest_messages_str)
            else:
                prompt_template_name = "chat_summary_private_prompt"
                chat_target_name = "对方"
                if self.chat_target_info:
                    chat_target_name = (
                        self.chat_target_info.get("person_name")
                        or self.chat_target_info.get("user_nickname")
                        or chat_target_name
                    )
                prompt = await global_prompt_manager.format_prompt(
                    prompt_template_name,
                    chat_target=chat_target_name,
                    chat_logs=oldest_messages_str,
                )

            self.compressor_prompt = prompt

        # 构建当前消息
        self.talking_message_str = build_readable_messages(
            messages=self.talking_message,
            timestamp_mode="lite",
            read_mark=last_obs_time_mark,
            show_actions=True,
        )
        self.talking_message_str_truncate = build_readable_messages(
            messages=self.talking_message,
            timestamp_mode="normal_no_YMD",
            read_mark=last_obs_time_mark,
            truncate=True,
            show_actions=True,
        )

        self.person_list = await get_person_id_list(self.talking_message)

        # logger.debug(
        #     f"Chat {self.chat_id} - 现在聊天内容：{self.talking_message_str}"
        # )

    async def has_new_messages_since(self, timestamp: float) -> bool:
        """检查指定时间戳之后是否有新消息"""
        count = num_new_messages_since(chat_id=self.chat_id, timestamp_start=timestamp)
        return count > 0
