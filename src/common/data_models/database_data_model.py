from enum import Enum

from typing import Optional, Union, Dict, Any, Tuple, List

from dataclasses import dataclass, field


@dataclass
class DatabaseUserInfo:
    user_platform: str = field(default_factory=str)
    user_id: str = field(default_factory=str)
    user_nickname: str = field(default_factory=str)
    user_cardname: Optional[str] = None


@dataclass
class DatabaseGroupInfo:
    group_id: str = field(default_factory=str)
    group_name: str = field(default_factory=str)
    group_platform: Optional[str] = None


@dataclass
class DatabaseChatInfo:
    stream_id: str = field(default_factory=str)
    platform: str = field(default_factory=str)
    create_time: float = field(default_factory=float)
    last_active_time: float = field(default_factory=float)
    user_info: DatabaseUserInfo = field(default_factory=DatabaseUserInfo)
    group_info: Optional[DatabaseGroupInfo] = None


@dataclass
class DatabaseMessages:
    chat_info: DatabaseChatInfo
    user_info: DatabaseUserInfo
    group_info: Optional[DatabaseGroupInfo] = None

    message_id: str = field(default_factory=str)
    time: float = field(default_factory=float)
    chat_id: str = field(default_factory=str)
    reply_to: Optional[str] = None
    interest_value: Optional[float] = None

    key_words: Optional[str] = None
    key_words_lite: Optional[str] = None
    is_mentioned: Optional[bool] = None

    # 从 chat_info 扁平化而来的字段
    chat_info_stream_id: str = field(default_factory=str)
    chat_info_platform: str = field(default_factory=str)
    chat_info_user_platform: str = field(default_factory=str)
    chat_info_user_id: str = field(default_factory=str)
    chat_info_user_nickname: str = field(default_factory=str)
    chat_info_user_cardname: Optional[str] = None
    chat_info_group_platform: Optional[str] = None
    chat_info_group_id: Optional[str] = None
    chat_info_group_name: Optional[str] = None
    chat_info_create_time: float = field(default_factory=float)
    chat_info_last_active_time: float = field(default_factory=float)

    # 从顶层 user_info 扁平化而来的字段 (消息发送者信息)
    user_platform: str = field(default_factory=str)
    user_id: str = field(default_factory=str)
    user_nickname: str = field(default_factory=str)
    user_cardname: Optional[str] = None

    processed_plain_text: Optional[str] = None  # 处理后的纯文本消息
    display_message: Optional[str] = None  # 显示的消息

    priority_mode: Optional[str] = None
    priority_info: Optional[str] = None

    additional_config: Optional[str] = None
    is_emoji: bool = False
    is_picid: bool = False
    is_command: bool = False
    is_notify: bool = False

    selected_expressions: Optional[str] = None

    def __post_init__(self):
        self.user_info = DatabaseUserInfo(
            user_id=self.user_id,
            user_nickname=self.user_nickname,
            user_cardname=self.user_cardname,
            user_platform=self.user_platform,
        )

        if not (self.chat_info_group_id and self.chat_info_group_name):
            self.group_info = None

        chat_user_info = DatabaseUserInfo(
            user_id=self.chat_info_user_id,
            user_nickname=self.chat_info_user_nickname,
            user_cardname=self.chat_info_user_cardname,
            user_platform=self.chat_info_user_platform,
        )
        self.chat_info = DatabaseChatInfo(
            stream_id=self.chat_info_stream_id,
            platform=self.chat_info_platform,
            create_time=self.chat_info_create_time,
            last_active_time=self.chat_info_last_active_time,
            user_info=chat_user_info,
            group_info=self.group_info,
        )
