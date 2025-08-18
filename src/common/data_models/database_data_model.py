from typing import Optional, Dict, Any
from dataclasses import dataclass, field, fields, MISSING

from . import AbstractClassFlag


@dataclass
class DatabaseUserInfo(AbstractClassFlag):
    platform: str = field(default_factory=str)
    user_id: str = field(default_factory=str)
    user_nickname: str = field(default_factory=str)
    user_cardname: Optional[str] = None

    # def __post_init__(self):
    #     assert isinstance(self.platform, str), "platform must be a string"
    #     assert isinstance(self.user_id, str), "user_id must be a string"
    #     assert isinstance(self.user_nickname, str), "user_nickname must be a string"
    #     assert isinstance(self.user_cardname, str) or self.user_cardname is None, (
    #         "user_cardname must be a string or None"
    #     )


@dataclass
class DatabaseGroupInfo(AbstractClassFlag):
    group_id: str = field(default_factory=str)
    group_name: str = field(default_factory=str)
    group_platform: Optional[str] = None

    # def __post_init__(self):
    #     assert isinstance(self.group_id, str), "group_id must be a string"
    #     assert isinstance(self.group_name, str), "group_name must be a string"
    #     assert isinstance(self.group_platform, str) or self.group_platform is None, (
    #         "group_platform must be a string or None"
    #     )


@dataclass
class DatabaseChatInfo(AbstractClassFlag):
    stream_id: str = field(default_factory=str)
    platform: str = field(default_factory=str)
    create_time: float = field(default_factory=float)
    last_active_time: float = field(default_factory=float)
    user_info: DatabaseUserInfo = field(default_factory=DatabaseUserInfo)
    group_info: Optional[DatabaseGroupInfo] = None

    # def __post_init__(self):
    #     assert isinstance(self.stream_id, str), "stream_id must be a string"
    #     assert isinstance(self.platform, str), "platform must be a string"
    #     assert isinstance(self.create_time, float), "create_time must be a float"
    #     assert isinstance(self.last_active_time, float), "last_active_time must be a float"
    #     assert isinstance(self.user_info, DatabaseUserInfo), "user_info must be a DatabaseUserInfo instance"
    #     assert isinstance(self.group_info, DatabaseGroupInfo) or self.group_info is None, (
    #         "group_info must be a DatabaseGroupInfo instance or None"
    #     )


@dataclass(init=False)
class DatabaseMessages(AbstractClassFlag):
    message_id: str = field(default_factory=str)
    time: float = field(default_factory=float)
    chat_id: str = field(default_factory=str)
    reply_to: Optional[str] = None
    interest_value: Optional[float] = None

    key_words: Optional[str] = None
    key_words_lite: Optional[str] = None
    is_mentioned: Optional[bool] = None

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

    def __init__(self, **kwargs: Any):
        defined = {f.name: f for f in fields(self.__class__)}
        for name, f in defined.items():
            if name in kwargs:
                setattr(self, name, kwargs.pop(name))
            elif f.default is not MISSING:
                setattr(self, name, f.default)
            else:
                raise TypeError(f"缺失必需字段: {name}")

        self.group_info = None
        self.user_info = DatabaseUserInfo(
            user_id=kwargs.get("user_id"),  # type: ignore
            user_nickname=kwargs.get("user_nickname"),  # type: ignore
            user_cardname=kwargs.get("user_cardname"),  # type: ignore
            platform=kwargs.get("user_platform"),  # type: ignore
        )
        if kwargs.get("chat_info_group_id") and kwargs.get("chat_info_group_name"):
            self.group_info = DatabaseGroupInfo(
                group_id=kwargs.get("chat_info_group_id"),  # type: ignore
                group_name=kwargs.get("chat_info_group_name"),  # type: ignore
                group_platform=kwargs.get("chat_info_group_platform"),  # type: ignore
            )

        chat_user_info = DatabaseUserInfo(
            user_id=kwargs.get("chat_info_user_id"),  # type: ignore
            user_nickname=kwargs.get("chat_info_user_nickname"),  # type: ignore
            user_cardname=kwargs.get("chat_info_user_cardname"),  # type: ignore
            platform=kwargs.get("chat_info_user_platform"),  # type: ignore
        )

        self.chat_info = DatabaseChatInfo(
            stream_id=kwargs.get("chat_info_stream_id"),  # type: ignore
            platform=kwargs.get("chat_info_platform"),  # type: ignore
            create_time=kwargs.get("chat_info_create_time"),  # type: ignore
            last_active_time=kwargs.get("chat_info_last_active_time"),  # type: ignore
            user_info=chat_user_info,
            group_info=self.group_info,
        )

    # def __post_init__(self):
    #     assert isinstance(self.message_id, str), "message_id must be a string"
    #     assert isinstance(self.time, float), "time must be a float"
    #     assert isinstance(self.chat_id, str), "chat_id must be a string"
    #     assert isinstance(self.reply_to, str) or self.reply_to is None, "reply_to must be a string or None"
    #     assert isinstance(self.interest_value, float) or self.interest_value is None, (
    #         "interest_value must be a float or None"
    #     )
