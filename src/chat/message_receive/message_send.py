from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional
from rich.traceback import install

from chat.utils.emoji_manager import chat_emoji_manager
from chat.utils.image_manager import chat_image_manager
from manager.mood_manager import mood_manager
from individuality.self_construction import self_record
from maim_message import BaseMessageInfo, GroupInfo, MessageBase, Seg, UserInfo
from chat.message_receive.message_recv import MessageRecv
from model_manager.chat_group import ChatGroupDTO, ChatGroupManager
from model_manager.chat_stream import ChatStreamDTO, ChatStreamManager
from model_manager.chat_user import ChatUserDTO, ChatUserManager
from model_manager.message import MessageDTO
from common.logger_manager import get_logger


install(extra_lines=3)

logger = get_logger("chat_message")


@dataclass
class MessageSend(MessageDTO):
    """发送消息类，用于MMC发送到Adapter的消息流转

    可构造为普通消息（如普通的文本/图像/语音）或指令消息（控制Adapter执行特定操作，如禁言、踢人等）
    """

    message_base: Optional[MessageBase] = None
    """消息元数据"""

    # -- 以下为消息处理所需字段 --

    replied_message: Optional[MessageRecv] = None
    """回复的消息对象（可选）"""

    chat_mode: Literal["normal", "focus"] = "normal"
    """聊天模式（Debug显示用），默认为"normal"，可选"focus"专注模式"""

    typing_time: float = 0.0
    """打字时间，单位为秒"""

    @classmethod
    def build_normal_message(
        cls,
        target_chat_stream_id: int,
        segs: Seg,
        replied_message: Optional[MessageRecv] = None,
        thinking_start_time: float = 0,
        chat_mode: Literal["normal", "focus"] = "normal",
    ) -> "MessageSend":
        """构建一个普通消息

        :target_chat_stream_id: 目标聊天流ID
        :message_segment: 消息段，包含文本、图片等内容
        :replied_message: 回复的消息对象（可选）
        :thinking_start_time: 思考开始时间戳，用于计算思考时间
        :chat_mode: 聊天模式（Debug显示用），默认为"normal"，可选"focus"专注模式
        """

        # 取group_info和user_info
        chat_stream_dto = ChatStreamManager.get_chat_stream(ChatStreamDTO(id=target_chat_stream_id))
        if not chat_stream_dto:
            raise ValueError(f"ChatStream with ID {target_chat_stream_id} does not exist.")

        group_info = None
        user_info = None

        if chat_stream_dto.group_id:
            chat_group_dto = ChatGroupManager.get_chat_group(ChatGroupDTO(id=chat_stream_dto.group_id))
            group_info = GroupInfo(
                platform=chat_group_dto.platform,
                group_id=chat_group_dto.platform_group_id,
            )

        if chat_stream_dto.user_id:
            chat_user_dto = ChatUserManager.get_chat_user(ChatUserDTO(id=chat_stream_dto.user_id))
            user_info = UserInfo(
                platform=chat_user_dto.platform,
                user_id=chat_user_dto.platform_user_id,
            )

        if group_info and user_info:
            assert group_info.platform == user_info.platform, "群组和用户信息的platform不一致，这不应该发生"

        platform = group_info.platform if group_info else user_info.platform

        base_message_info = BaseMessageInfo(
            platform=platform,
            group_info=group_info,
            user_info=user_info,
        )

        message_segment = Seg(
            type="seglist",
            data=[],
        )

        # 如果有回复的消息，则设置回复信息
        if replied_message and replied_message.platform_message_id != "N/A":
            message_segment.data.append(
                Seg(
                    type="reply",
                    data=replied_message.platform_message_id,
                )
            )

        # 将消息段添加进message_segment
        if segs.type == "seglist":
            # 如果是列表，直接添加seg
            assert isinstance(segs.data, list)
            message_segment.data.extend(segs.data)
        else:
            # 其他情况，附在列表后
            message_segment.data.append(segs)

        message_base = MessageBase(
            message_info=base_message_info,
            message_segment=message_segment,
        )

        message_send = MessageSend(
            message_base=message_base,
            message_time=datetime.now(),
            platform_message_id="N/A",  # 发送时，使用占位符
            chat_stream_id=target_chat_stream_id,
            sender_id=self_record.platform_user_id[platform],
            chat_mode=chat_mode,
            # processed_plain_text 会通过process()填入
            # typing_time 会通过process()填入
            # 需在存入数据库前调用process()
        )

        message_send.thinking_start_time = thinking_start_time

        return message_send

    async def process(self) -> None:
        """处理消息内容，填充MessageDTO字段和消息处理必要的字段"""

        if self.processed_plain_text:
            # 如果已经处理过了，则不再处理
            return

        self.processed_plain_text = await self._process_single_segment(self.message_base.message_segment)

        self.typing_time += _calc_typing_time(is_enter=True)  # 回车输入时间

        if self.replied_message:
            chat_user_dto = ChatUserManager.get_chat_user(
                ChatUserDTO(
                    id=self.replied_message.sender_id,
                )
            )
            if chat_user_dto and chat_user_dto.user_name and chat_user_dto.platform_user_id:
                self.processed_plain_text = f"[回复<{chat_user_dto.user_name}:{chat_user_dto.platform_user_id}>：{self.replied_message.processed_plain_text}]，说：{self.processed_plain_text}"
            else:
                self.processed_plain_text = (
                    f"[回复 未知用户：{self.replied_message.processed_plain_text}]，说：{self.processed_plain_text}"
                )

    async def _process_single_segment(self, seg: Seg) -> str:
        """处理单个消息段

        :params seg: 要处理的消息段

        :returns: 处理后的文本
        """
        try:
            match seg.type:
                case "text":
                    # 如果是文本消息
                    self.typing_time += _calc_typing_time(text=seg.data)
                    return seg.data
                case "image":
                    # 如果是base64图片数据
                    if not isinstance(seg.data, str):
                        return "[图片(加载失败)]"

                    self.typing_time += _calc_typing_time(is_emoji_or_image=True)

                    return (await chat_image_manager.get_image_description(seg.data)) or "[图片(加载失败)]"

                case "emoji":
                    if not isinstance(seg.data, str):
                        return "[表情包(加载失败)]"

                    self.typing_time += _calc_typing_time(is_emoji_or_image=True)

                    return (await chat_emoji_manager.get_emoji_description(seg.data)) or "[表情包(加载失败)]"

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

    def build_command_message(
        self,
        target_chat_stream_id: int,
        segs: Seg,
        in_prompt_display: str,
    ):
        """构建一个指令消息

        :target_chat_stream_id: 目标聊天流ID
        :segs: 消息段
        :in_prompt_display: 在Prompt中显示的文本内容
        :returns: 构建好的指令消息对象
        """
        chat_stream_dto = ChatStreamManager.get_chat_stream(ChatStreamDTO(id=target_chat_stream_id))
        if not chat_stream_dto:
            raise ValueError(f"ChatStream with ID {target_chat_stream_id} does not exist.")

        group_info = None
        user_info = None

        if chat_stream_dto.group_id:
            chat_group_dto = ChatGroupManager.get_chat_group(ChatGroupDTO(id=chat_stream_dto.group_id))
            group_info = GroupInfo(
                platform=chat_group_dto.platform,
                group_id=chat_group_dto.platform_group_id,
            )

        if chat_stream_dto.user_id:
            chat_user_dto = ChatUserManager.get_chat_user(ChatUserDTO(id=chat_stream_dto.user_id))
            user_info = UserInfo(
                platform=chat_user_dto.platform,
                user_id=chat_user_dto.platform_user_id,
            )

        if group_info and user_info:
            assert group_info.platform == user_info.platform, "群组和用户信息的platform不一致，这不应该发生"

        platform = group_info.platform if group_info else user_info.platform

        base_message_info = BaseMessageInfo(
            platform=platform,
            group_info=group_info,
            user_info=user_info,
        )

        message_base = MessageBase(
            message_info=base_message_info,
            message_segment=segs,
        )

        return MessageSend(
            message_base=message_base,
            message_time=datetime.now(),
            platform_message_id="N/A",  # 发送时，使用占位符
            chat_stream_id=target_chat_stream_id,
            sender_id=self_record.platform_user_id[platform],
            processed_plain_text=in_prompt_display,
        )


def _calc_typing_time(
    text: str = None,
    is_emoji_or_image: bool = False,
    is_enter: bool = False,
    chinese_typing_speed_per_word: float = 0.6,
    english_typing_speed_per_word: float = 0.5,
    other_typing_speed_per_char: float = 0.1,
    emoji_or_image_speed: float = 1.0,
    enter_speed: float = 0.2,
) -> float:
    """计算打字时间

    :param text: 要计算的文本内容
    :param is_emoji_or_image: 是否为表情或图片
    :param is_enter: 是否为回车输入
    :param chinese_typing_speed_per_word: 中文打字速度，默认为0.8秒/字
    :param english_typing_speed_per_word: 英文打字速度，默认为0.5秒/词
    :param other_typing_speed_per_char: 其他字符打字速度，默认为0.2秒/字符
    :param emoji_speed: 表情输入速度，默认为1.0秒
    :param enter_speed: 回车输入速度，默认为0.3秒

    :return: 计算出的打字时间，单位为秒
    """

    if is_emoji_or_image:
        total_time = emoji_or_image_speed
    elif is_enter:
        total_time = enter_speed
    elif not text:
        return 0.0
    else:
        # 计算中文字符数和英文单词数
        # 中文字符逐字符计算，英文单词视为连续字母或数字
        chinese_chars = 0
        english_words = 0
        other_chars = 0
        for idx, char in enumerate(text):
            if "\u4e00" <= char <= "\u9fff":  # 检查是否为中文字符
                chinese_chars += 1
            elif char.isalpha() or char in ["-", "_"]:  # 检查是否为英文字符，允许连字符和下划线
                if idx == 0 or not text[idx - 1].isalpha():
                    english_words += 1
            else:
                other_chars += 1

        # 计算总打字时间
        if chinese_chars <= 5 and english_words == 0 and other_chars == 0:
            # 如果只有少量中文字符，直接返回
            total_time = 1
        else:
            total_time = (
                chinese_chars * chinese_typing_speed_per_word
                + english_words * english_typing_speed_per_word
                + other_chars * other_typing_speed_per_char
            )

    # 根据心情的唤醒度调整打字时间
    mood_arousal = mood_manager.current_mood.arousal  # -1.0 ~ 1.0
    # -1.0 ~ 0.0 -> x0.5 ~ x1.0
    # 0.0 ~ 1.0 -> x1.0 ~ x2.0
    arousal_factor = 2**mood_arousal
    total_time /= arousal_factor

    return total_time
