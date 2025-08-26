from typing import Optional, TYPE_CHECKING
from dataclasses import dataclass, field

from . import BaseDataModel

if TYPE_CHECKING:
    from .database_data_model import DatabaseMessages


@dataclass
class MessageAndActionModel(BaseDataModel):
    chat_id: str = field(default_factory=str)
    time: float = field(default_factory=float)
    user_id: str = field(default_factory=str)
    user_platform: str = field(default_factory=str)
    user_nickname: str = field(default_factory=str)
    user_cardname: Optional[str] = None
    processed_plain_text: Optional[str] = None
    display_message: Optional[str] = None
    chat_info_platform: str = field(default_factory=str)
    is_action_record: bool = field(default=False)
    action_name: Optional[str] = None

    @classmethod
    def from_DatabaseMessages(cls, message: "DatabaseMessages"):
        return cls(
            chat_id=message.chat_id,
            time=message.time,
            user_id=message.user_info.user_id,
            user_platform=message.user_info.platform,
            user_nickname=message.user_info.user_nickname,
            user_cardname=message.user_info.user_cardname,
            processed_plain_text=message.processed_plain_text,
            display_message=message.display_message,
            chat_info_platform=message.chat_info.platform,
        )
