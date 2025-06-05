from typing import Optional
from dataclasses import dataclass
from datetime import datetime
from rich.traceback import install

from chat.utils.emoji_manager import chat_emoji_manager
from chat.utils.image_manager import chat_image_manager
from common.logger_manager import get_logger
from config.config import global_config
from model_manager.chat_group import ChatGroupDTO, ChatGroupManager
from model_manager.chat_group_user import ChatGroupUserDTO, ChatGroupUserManager
from model_manager.chat_stream import ChatStreamDTO, ChatStreamManager
from model_manager.chat_user import ChatUserDTO, ChatUserManager
from model_manager.message import MessageDTO
from person_info.person_identity import PersonIdentityManager
from maim_message import BaseMessageInfo, MessageBase, Seg

install(extra_lines=3)

logger = get_logger("chat_message")


@dataclass
class MessageRecv(MessageDTO):
    """接收消息类，用于MMC内部业务逻辑的消息流转

    可由MessageBase（由Adapter接收的消息）或MessageDTO（从数据库中取出的消息）构造
    """

    message_base: Optional[MessageBase] = None
    """消息元数据"""

    # -- 以下为消息处理所需字段 --

    message_info: BaseMessageInfo
    """消息信息，包含平台、消息ID、时间等元数据"""

    is_emoji: bool = False
    """是否为表情包消息"""

    is_self_mentioned: bool = False
    """消息是否提到了自身"""

    interest_bias: float = 0.0
    """兴趣偏置，用于调整兴趣值"""

    @classmethod
    def from_message_base(cls, message_base: MessageBase) -> "MessageRecv":
        """从MessageBase初始化

        :param message_base: MessageBase实例，包含消息信息和段落
        """
        message_recv = MessageRecv(
            message_base=message_base,
        )

        message_recv.message_time = (
            datetime.fromtimestamp(message_base.message_info.time) if message_base.message_info.time else datetime.now()
        )  # 若未提供message_base.message_info.time，则使用当前时间
        message_recv.platform_message_id = message_base.message_info.message_id

        return message_recv

    @classmethod
    def from_dto(cls, message_dto: MessageDTO) -> "MessageRecv":
        """从MessageDTO转换为MessageRecv实例

        :param message_dto: MessageDTO实例
        """
        return MessageRecv(**message_dto.__dict__)

    async def process(self) -> None:
        """处理消息内容，填充MessageDTO字段和消息处理必要的字段"""
        chat_user_dto = await self._get_or_create_chat_user()
        chat_group_dto = None
        _chat_group_user_dto = None

        if self.message_base.message_info.group_info:
            chat_group_dto = self._get_or_create_chat_group()
            _chat_group_user_dto = self._get_or_create_group_user(chat_group_dto, chat_user_dto)
            chat_stream_dto = self._get_chat_stream(chat_group_dto=chat_group_dto)
        else:
            chat_stream_dto = self._get_chat_stream(chat_user_dto=chat_user_dto)

        self.chat_stream_id = chat_stream_dto.id
        self.sender_id = chat_user_dto.id
        self.processed_plain_text = await self._process_single_segment(self.message_base.message_segment)

        self.is_self_mentioned = self._check_if_self_mentioned()

    async def _get_or_create_chat_user(self):
        """查找或创建发送者信息"""
        # 如果群组信息存在，尝试使用用户的群名片
        user_cardname = None
        if self.message_base.message_info.group_info:
            user_cardname = (
                self.message_base.message_info.user_info.user_cardname
                or self.message_base.message_info.user_info.user_nickname
            )

        if not (
            chat_user_dto := ChatUserManager.get_chat_user(
                ChatUserDTO(
                    platform=self.message_base.message_info.platform,
                    platform_user_id=self.message_base.message_info.user_info.user_id,
                )
            )
        ):
            # 如果没有找到用户信息，则创建新的用户信息
            person_dto = await PersonIdentityManager.create_person_info(
                user_nickname=self.message_base.message_info.user_info.user_nickname,
                user_cardname=user_cardname,
                user_avatar=None,
            )
            chat_user_dto = ChatUserManager.create_user(
                ChatUserDTO(
                    platform=self.message_base.message_info.platform,
                    platform_user_id=self.message_base.message_info.user_info.user_id,
                    user_name=self.message_base.message_info.user_info.user_nickname,
                    person_id=person_dto.id,
                )
            )
        elif (
            self.message_base.message_info.user_info.user_nickname
            and self.message_base.message_info.user_info.user_nickname != chat_user_dto.user_name
        ):
            chat_user_dto.user_name = self.message_base.message_info.user_info.user_nickname
            ChatUserManager.update_user(chat_user_dto)

        return chat_user_dto

    def _get_or_create_chat_group(self):
        """查找或创建群组信息"""
        if not (
            chat_group_dto := ChatGroupManager.get_chat_group(
                platform=self.message_base.message_info.platform,
                group_id=self.message_base.message_info.group_info.group_id,
            )
        ):
            # 如果没有找到群组信息，则创建新的群组信息
            chat_group_dto = ChatGroupManager.create_chat_group(
                ChatGroupDTO(
                    platform=self.message_base.message_info.platform,
                    platform_group_id=self.message_base.message_info.group_info.group_id,
                    group_name=self.message_base.message_info.group_info.group_name or None,
                )
            )
        elif (
            self.message_base.message_info.group_info.group_name
            and self.message_base.message_info.group_info.group_name != chat_group_dto.group_name
        ):
            chat_group_dto.group_name = self.message_base.message_info.group_info.group_name
            ChatGroupManager.update_chat_group(chat_group_dto)

        return chat_group_dto

    def _get_or_create_group_user(self, chat_group_dto, chat_user_dto):
        """查找或创建群组用户关联"""
        if self.message_base.message_info.user_info.user_cardname:
            user_cardname = self.message_base.message_info.user_info.user_cardname
        else:
            user_cardname = None

        if not (
            chat_group_user_dto := ChatGroupUserManager.create_group_user(
                ChatGroupUserDTO(
                    group_id=chat_group_dto.id,
                    user_id=chat_user_dto.id,
                )
            )
        ):
            # 如果没有找到群组用户信息，则创建新的群组用户信息
            chat_group_user_dto = ChatGroupUserManager.create_group_user(
                ChatGroupUserDTO(
                    group_id=chat_group_dto.id,
                    user_id=chat_user_dto.id,
                    platform=self.message_base.message_info.platform,
                    user_group_name=user_cardname,
                )
            )
        elif user_cardname and user_cardname != chat_group_user_dto.user_group_name:
            chat_group_user_dto.user_group_name = user_cardname
            ChatGroupUserManager.update_group_user(chat_group_user_dto)

        return chat_group_user_dto

    def _get_chat_stream(self, chat_group_dto=None, chat_user_dto=None):
        """查找聊天流"""
        if chat_group_dto:
            return ChatStreamManager.get_chat_stream(
                ChatStreamDTO(
                    group_id=chat_group_dto.id,
                )
            )
        elif chat_user_dto:
            return ChatStreamManager.get_chat_stream(
                ChatStreamDTO(
                    user_id=chat_user_dto.id,
                )
            )
        else:
            raise ValueError("chat_group_dto or chat_user_dto must be provided")

    async def _process_single_segment(self, seg: Seg) -> str:
        """处理单个消息段

        :params seg: 要处理的消息段

        :returns: 处理后的文本
        """
        try:
            match seg.type:
                case "text":
                    return seg.data

                case "image":
                    # 如果是base64图片数据
                    if not isinstance(seg.data, str):
                        return "[图片(加载失败)]"

                    return (await chat_image_manager.get_image_description(seg.data)) or "[图片(加载失败)]"

                case "emoji":
                    self.is_emoji = True
                    if not isinstance(seg.data, str):
                        return "[表情包(加载失败)]"

                    return (await chat_emoji_manager.get_emoji_description(seg.data)) or "[表情包(加载失败)]"

                case "mention_bot":
                    self.is_self_mentioned = True
                    self.interest_bias = max(
                        self.interest_bias, global_config.bot.interest_bias
                    )  # 当一条消息里有多条提及时，使用最高的兴趣值

                case "seglist":
                    if not isinstance(seg.data, list):
                        return "[消息(加载失败)]"

                    segments_text = []
                    for single_seg in seg.data:
                        processed = await self._process_single_segment(single_seg)
                        if processed:
                            segments_text.append(processed)
                    return " ".join(segments_text)

                case _:
                    return f"[{seg.type}:{str(seg.data)}]"

        except Exception as e:
            logger.error(f"处理消息段失败: {str(e)}, 类型: {seg.type}, 数据: {seg.data}")
            return f"[处理失败的{seg.type}消息]"

    def _check_if_self_mentioned(self) -> bool:
        """检查消息是否提到了自己"""
        self_tokens = [global_config.bot.nickname]
        self_tokens.extend(global_config.bot.alias_names)

        return any(token in self.processed_plain_text for token in self_tokens)
