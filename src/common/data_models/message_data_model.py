from typing import Optional, TYPE_CHECKING, List, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum

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


class ReplyContentType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    HYBRID = "hybrid"  # 混合类型，包含多种内容


@dataclass
class ReplySetModel(BaseDataModel):
    """
    回复集数据模型，用于多种回复类型的返回
    """

    reply_set_data: List[Tuple[ReplyContentType | str, Union[str, "ReplySetModel"]]] = field(default_factory=list)

    def add_text_content(self, text: str):
        """添加文本内容"""
        self.reply_set_data.append((ReplyContentType.TEXT, text))

    def add_image_content(self, image_base64: str):
        """添加图片内容，base64编码的图片数据"""
        self.reply_set_data.append((ReplyContentType.IMAGE, image_base64))

    def add_voice_content(self, voice_base64: str):
        """添加语音内容，base64编码的音频数据"""
        self.reply_set_data.append((ReplyContentType.VOICE, voice_base64))

    def add_hybrid_content(self, hybrid_content: "ReplySetModel"):
        """
        添加混合型内容，可以包含多种类型的内容

        实际解析时只关注最外层，没有递归嵌套处理
        """
        self.reply_set_data.append((ReplyContentType.HYBRID, hybrid_content))

    def add_custom_content(self, content_type: str, content: str):
        """添加自定义类型的内容"""
        self.reply_set_data.append((content_type, content))
