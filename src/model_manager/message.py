from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import select

from common.database.database import DBSession
from model_manager.chat_stream import ChatStreamManager
from model_manager.dto_base import DTOBase
from manager.cache_manager import global_cache
from src.common.database.database_model import Message


@dataclass
class MessageDTO(DTOBase):
    """消息DTO"""

    id: Optional[int] = None
    """主键（由数据库创建，自动递增）"""

    created_at: Optional[datetime] = None
    """创建时间戳"""

    message_time: Optional[datetime] = None
    """消息时间戳"""

    chat_stream_id: Optional[int] = None
    """聊天流 ID"""

    sender_id: Optional[int] = None
    """发送者 ID"""

    processed_plain_text: Optional[str] = None
    """处理后的纯文本消息内容"""

    memorized_times: Optional[int] = None
    """记忆次数（用于统计消息被用于构建记忆的次数）"""

    __orm_create_rule__ = "message_time & chat_stream_id & sender_id"

    __orm_select_rule__ = "id"

    __orm_update_rule__ = "processed_plain_text | memorized_times"

    @classmethod
    def from_orm(cls, message: Message) -> "MessageDTO":
        """从ORM对象创建DTO对象。"""
        return cls(
            id=message.id,
            created_at=message.created_at,
            message_time=message.message_time,
            chat_stream_id=message.chat_stream_id,
            sender_id=message.sender_id,
            processed_plain_text=message.processed_plain_text,
            memorized_times=message.memorized_times,
        )


def _pk(id: int):
    """构造缓存主键"""
    return f"message:pk:{id}"


class MessageManager:
    @classmethod
    def create_message(cls, dto: MessageDTO) -> MessageDTO:
        """创建消息

        :param dto: 消息DTO
        :return: 创建的消息DTO
        """
        if dto.create_entity_check() is False:
            raise ValueError("Invalid DTO object for create.")

        # 确保聊天流和用户已存在
        if ChatStreamManager.get_chat_stream(stream_id=dto.chat_stream_id) is None:
            raise ValueError(f"ChatGroup '{dto.chat_stream_id}' does not exist.")

        with DBSession() as session:
            # 创建消息对象
            message = Message(
                created_at=datetime.now(),
                message_time=dto.message_time,
                chat_stream_id=dto.chat_stream_id,
                sender_id=dto.sender_id,
                processed_plain_text=dto.processed_plain_text,
            )
            session.add(message)
            session.commit()
            session.refresh(message)

            dto = MessageDTO.from_orm(message)

        # 刷新缓存
        global_cache[_pk(dto.id)] = dto

        return dto

    @classmethod
    def get_message(cls, dto: MessageDTO) -> Optional[MessageDTO]:
        """获取消息信息

        :param dto: 消息DTO
        :return: 获取到的消息DTO
        """
        if dto.select_entity_check() is False:
            raise ValueError("Invalid DTO object for select.")

        if message := global_cache[_pk(dto.id)]:
            return message
        else:
            return cls._get_message_by_id(dto.id)

    @classmethod
    def _get_message_by_id(cls, message_id: int) -> Optional[MessageDTO]:
        """根据消息 ID 获取消息信息"""
        with DBSession() as session:
            statement = select(MessageDTO).where(MessageDTO.id == message_id)
            if message := session.exec(statement).first():
                dto = MessageDTO.from_orm(message)
            else:
                return None

        # 如果查询到结果，则将其存入缓存
        global_cache[_pk(dto.id)] = dto

        return dto

    @classmethod
    def get_user_messages(
        cls,
        user_id: int,
        start_time: Optional[datetime] = None,
        num: Optional[int] = None,
    ) -> list[MessageDTO]:
        """获取用户的消息列表

        :param user_id: 用户ID
        :param start_time: 可选的起始时间戳，用于过滤消息
        :param num: 可选的消息数量限制
        :return: 用户的消息列表
        """
        with DBSession() as session:
            statement = select(Message).where(Message.sender_id == user_id)
            if start_time:
                statement = statement.where(Message.message_time >= start_time)
            statement = statement.order_by(Message.message_time.desc())
            if num:
                statement = statement.limit(num)

            messages = session.exec(statement).all()
            return [MessageDTO.from_orm(message) for message in messages]

    @classmethod
    def get_chat_stream_messages(
        cls,
        chat_stream_id: int,
        start_time: Optional[datetime] = None,
        num: Optional[int] = None,
    ) -> list[MessageDTO]:
        """获取聊天流的消息列表

        :param chat_stream_id: 聊天流ID
        :param start_time: 可选的起始时间戳，用于过滤消息
        :param num: 可选的消息数量限制
        :return: 聊天流的消息列表
        """
        with DBSession() as session:
            statement = select(Message).where(Message.chat_stream_id == chat_stream_id)
            if start_time:
                statement = statement.where(Message.message_time >= start_time)
            statement = statement.order_by(Message.message_time.desc())
            if num:
                statement = statement.limit(num)

            messages = session.exec(statement).all()
            return [MessageDTO.from_orm(message) for message in messages]

    @classmethod
    def update_message(cls, dto: MessageDTO) -> MessageDTO:
        """更新消息

        :param dto: 消息DTO
        :return: 更新后的消息DTO
        """
        if dto.update_entity_check() is False:
            raise ValueError("Invalid DTO object for update.")

        with DBSession() as session:
            # 更新数据库中的消息
            statement = select(Message).where(Message.id == dto.id)
            message = session.exec(statement).first()

            if message is None:
                raise ValueError(f"Message '{dto.id}' does not exist.")

            # 更新消息信息
            message.processed_plain_text = dto.processed_plain_text or message.processed_plain_text
            message.memorized_times = dto.memorized_times or message.memorized_times

            session.commit()
            session.refresh(message)
            dto = MessageDTO.from_orm(message)

        # 刷新缓存
        global_cache[_pk(dto.id)] = dto

        return dto
