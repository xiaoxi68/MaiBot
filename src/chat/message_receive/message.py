from datetime import datetime
import time
from abc import abstractmethod
from dataclasses import dataclass
from typing import Optional

import urllib3

from config.config import global_config
from chat.utils.emoji_manager import chat_emoji_manager
from chat.utils.image_manager import chat_image_manager
from model_manager.chat_group import ChatGroupDTO, ChatGroupManager
from model_manager.chat_group_user import ChatGroupUserDTO, ChatGroupUserManager
from model_manager.chat_stream import ChatStreamDTO, ChatStreamManager
from model_manager.chat_user import ChatUserDTO, ChatUserManager
from model_manager.message import MessageDTO
from person_info.person_identity import PersonIdentityManager
from src.common.logger_manager import get_logger

from maim_message import Seg, UserInfo, BaseMessageInfo, MessageBase
from rich.traceback import install

install(extra_lines=3)

logger = get_logger("chat_message")

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class MessageRecv(MessageDTO):
    """接收消息类，用于处理从MessageCQ序列化的消息"""

    def __init__(self, message_base: MessageBase):
        """从MessageBase初始化

        :param message_base: MessageBase实例，包含消息信息和段落
        """
        super().__init__(
            message_time=(
                datetime.fromtimestamp(message_base.message_info.time)
                if message_base.message_info.time
                else datetime.now()
            )  # 若未提供message_base.message_info.time，则使用当前时间
        )

        self.message_base = message_base
        """消息元数据"""

        # -- 以下为消息处理所需字段 --

        self.is_emoji: bool = False
        """是否为表情包消息"""

        self.is_self_mentioned: bool = False
        """消息是否提到了自身"""

        self.is_self_at: bool = False
        """消息是否包含@自己"""

        self.is_self_replied: bool = False
        """是否为回复自己的消息"""

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

                case "at":
                    # self.is_at = True
                    if not isinstance(seg.data, dict):
                        return "[@消息(加载失败)]"

                    self.is_self_at = seg.data.get("self_target", False)
                    user_nickname = seg.data.get("user_nickname")
                    return f"@{user_nickname}"

                case "reply":
                    # self.self_replied = True
                    if not isinstance(seg.data, dict):
                        return "[回复消息(加载失败)]"

                    self.is_self_replied = seg.data.get("self_target", False)
                    replied_message_seg = seg.data.get("replied_message")
                    if not isinstance(replied_message_seg, Seg):
                        return "[回复消息(加载失败)]"

                    replied_message = await self._process_single_segment(replied_message_seg)
                    user_nickname = seg.data.get("user_nickname")
                    return f"[回复 {user_nickname}: {replied_message}] 说"

                case "seglist":
                    if not isinstance(seg.data, list):
                        return "[消息(加载失败)]"

                    segments_text = []
                    for single_seg in seg.data:
                        processed = await self._process_message_segments(single_seg)
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


@dataclass
class Message(MessageBase):
    """消息类，包含消息的基本信息和处理逻辑"""

    chat_stream_id: Optional[int] = None
    reply: Optional["Message"] = None
    processed_plain_text: str = ""
    memorized_times: int = 0

    def __init__(
        self,
        message_id: str,
        chat_stream: "ChatStream",
        user_info: UserInfo,
        message_segment: Optional[Seg] = None,
        timestamp: Optional[float] = None,
        reply: Optional["MessageRecv"] = None,
        detailed_plain_text: str = "",
        processed_plain_text: str = "",
    ):
        # 使用传入的时间戳或当前时间
        current_timestamp = timestamp if timestamp is not None else round(time.time(), 3)
        # 构造基础消息信息
        message_info = BaseMessageInfo(
            platform=chat_stream.platform,
            message_id=message_id,
            time=current_timestamp,
            group_info=chat_stream.group_info,
            user_info=user_info,
        )

        # 调用父类初始化
        super().__init__(message_info=message_info, message_segment=message_segment, raw_message=None)

        self.chat_stream = chat_stream
        # 文本处理相关属性
        self.processed_plain_text = processed_plain_text
        self.detailed_plain_text = detailed_plain_text

        # 回复消息
        self.reply = reply

    @abstractmethod
    async def _process_single_segment(self, segment):
        pass


@dataclass
class MessageProcessBase(Message):
    """消息处理基类，用于处理中和发送中的消息"""

    def __init__(
        self,
        message_id: str,
        chat_stream: "ChatStream",
        bot_user_info: UserInfo,
        message_segment: Optional[Seg] = None,
        reply: Optional["MessageRecv"] = None,
        thinking_start_time: float = 0,
        timestamp: Optional[float] = None,
    ):
        # 调用父类初始化，传递时间戳
        super().__init__(
            message_id=message_id,
            timestamp=timestamp,
            chat_stream=chat_stream,
            user_info=bot_user_info,
            message_segment=message_segment,
            reply=reply,
        )

        # 处理状态相关属性
        self.thinking_start_time = thinking_start_time
        self.thinking_time = 0

    def update_thinking_time(self) -> float:
        """更新思考时间"""
        self.thinking_time = round(time.time() - self.thinking_start_time, 2)
        return self.thinking_time

    async def _process_single_segment(self, seg: Seg) -> str | None:
        """处理单个消息段

        Args:
            seg: 要处理的消息段

        Returns:
            str: 处理后的文本
        """
        try:
            if seg.type == "text":
                return seg.data
            elif seg.type == "image":
                # 如果是base64图片数据
                if isinstance(seg.data, str):
                    return await chat_image_manager(seg.data)
                return "[图片，网卡了加载不出来]"
            elif seg.type == "emoji":
                if isinstance(seg.data, str):
                    return await chat_emoji_manager.get_emoji_description(seg.data)
                return "[表情，网卡了加载不出来]"
            elif seg.type == "at":
                return f"[@{seg.data}]"
            elif seg.type == "reply":
                if self.reply and hasattr(self.reply, "processed_plain_text"):
                    return f"[回复：{self.reply.processed_plain_text}]"
                return None
            else:
                return f"[{seg.type}:{str(seg.data)}]"
        except Exception as e:
            logger.error(f"处理消息段失败: {str(e)}, 类型: {seg.type}, 数据: {seg.data}")
            return f"[处理失败的{seg.type}消息]"

    def _generate_detailed_text(self) -> str:
        """生成详细文本，包含时间和用户信息"""
        # time_str = time.strftime("%m-%d %H:%M:%S", time.localtime(self.message_info.time))
        timestamp = self.message_info.time
        user_info = self.message_info.user_info

        name = f"<{self.message_info.platform}:{user_info.user_id}:{user_info.user_nickname}:{user_info.user_cardname}>"
        return f"[{timestamp}]，{name} 说：{self.processed_plain_text}\n"


@dataclass
class MessageThinking(MessageProcessBase):
    """思考状态的消息类"""

    def __init__(
        self,
        message_id: str,
        chat_stream: "ChatStream",
        bot_user_info: UserInfo,
        reply: Optional["MessageRecv"] = None,
        thinking_start_time: float = 0,
        timestamp: Optional[float] = None,
    ):
        # 调用父类初始化，传递时间戳
        super().__init__(
            message_id=message_id,
            chat_stream=chat_stream,
            bot_user_info=bot_user_info,
            message_segment=None,  # 思考状态不需要消息段
            reply=reply,
            thinking_start_time=thinking_start_time,
            timestamp=timestamp,
        )

        # 思考状态特有属性
        self.interrupt = False


@dataclass
class MessageSending(MessageProcessBase):
    """发送状态的消息类"""

    def __init__(
        self,
        message_id: str,
        chat_stream: "ChatStream",
        bot_user_info: UserInfo,
        sender_info: UserInfo | None,  # 用来记录发送者信息,用于私聊回复
        message_segment: Seg,
        display_message: str = "",
        reply: Optional["MessageRecv"] = None,
        is_head: bool = False,
        is_emoji: bool = False,
        thinking_start_time: float = 0,
        apply_set_reply_logic: bool = False,
    ):
        # 调用父类初始化
        super().__init__(
            message_id=message_id,
            chat_stream=chat_stream,
            bot_user_info=bot_user_info,
            message_segment=message_segment,
            reply=reply,
            thinking_start_time=thinking_start_time,
        )

        # 发送状态特有属性
        self.sender_info = sender_info
        self.reply_to_message_id = reply.message_info.message_id if reply else None
        self.is_head = is_head
        self.is_emoji = is_emoji
        self.apply_set_reply_logic = apply_set_reply_logic

        # 用于显示发送内容与显示不一致的情况
        self.display_message = display_message

    def set_reply(self, reply: Optional["MessageRecv"] = None):
        """设置回复消息"""
        if True:
            if reply:
                self.reply = reply
            if self.reply:
                self.reply_to_message_id = self.reply.message_info.message_id
                self.message_segment = Seg(
                    type="seglist",
                    data=[
                        Seg(type="reply", data=self.reply.message_info.message_id),
                        self.message_segment,
                    ],
                )

    async def process(self) -> None:
        """处理消息内容，生成纯文本和详细文本"""
        if self.message_segment:
            self.processed_plain_text = await self._process_message_segments(self.message_segment)

    @classmethod
    def from_thinking(
        cls,
        thinking: MessageThinking,
        message_segment: Seg,
        is_head: bool = False,
        is_emoji: bool = False,
    ) -> "MessageSending":
        """从思考状态消息创建发送状态消息"""
        return cls(
            message_id=thinking.message_info.message_id,
            chat_stream=thinking.chat_stream,
            message_segment=message_segment,
            bot_user_info=thinking.message_info.user_info,
            reply=thinking.reply,
            is_head=is_head,
            is_emoji=is_emoji,
            sender_info=None,
        )

    def to_dict(self):
        ret = super().to_dict()
        ret["message_info"]["user_info"] = self.chat_stream.user_info.to_dict()
        return ret

    def is_private_message(self) -> bool:
        """判断是否为私聊消息"""
        return self.message_info.group_info is None or self.message_info.group_info.group_id is None


@dataclass
class MessageSet:
    """消息集合类，可以存储多个发送消息"""

    def __init__(self, chat_stream: "ChatStream", message_id: str):
        self.chat_stream = chat_stream
        self.message_id = message_id
        self.messages: list[MessageSending] = []
        self.time = round(time.time(), 3)  # 保留3位小数

    def add_message(self, message: MessageSending) -> None:
        """添加消息到集合"""
        if not isinstance(message, MessageSending):
            raise TypeError("MessageSet只能添加MessageSending类型的消息")
        self.messages.append(message)
        self.messages.sort(key=lambda x: x.message_info.time)

    def get_message_by_index(self, index: int) -> Optional[MessageSending]:
        """通过索引获取消息"""
        if 0 <= index < len(self.messages):
            return self.messages[index]
        return None

    def get_message_by_time(self, target_time: float) -> Optional[MessageSending]:
        """获取最接近指定时间的消息"""
        if not self.messages:
            return None

        left, right = 0, len(self.messages) - 1
        while left < right:
            mid = (left + right) // 2
            if self.messages[mid].message_info.time < target_time:
                left = mid + 1
            else:
                right = mid

        return self.messages[left]

    def clear_messages(self) -> None:
        """清空所有消息"""
        self.messages.clear()

    def remove_message(self, message: MessageSending) -> bool:
        """移除指定消息"""
        if message in self.messages:
            self.messages.remove(message)
            return True
        return False

    def __str__(self) -> str:
        return f"MessageSet(id={self.message_id}, count={len(self.messages)})"

    def __len__(self) -> int:
        return len(self.messages)
