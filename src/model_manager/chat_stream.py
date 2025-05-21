from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import select

from src.common.database.database import DBSession
from src.common.database.database_model import ChatGroup, ChatUser, ChatStream
from src.manager.cache_manager import global_cache
from model_manager.dto_base import DTOBase


@dataclass
class ChatStreamDTO(DTOBase):
    """聊天流DTO"""

    id: Optional[int] = None
    """主键（由数据库创建，自动递增）"""

    created_at: Optional[datetime] = None
    """创建时间戳"""

    group_id: Optional[int] = None
    """群组 ID
    （外键，指向 ChatGroup 表）
    （不为空时表示这是一个群组聊天流）
    """

    user_id: Optional[int] = None
    """用户 ID
    （外键，指向 ChatUser 表）
    （不为空时表示这是一个私聊聊天流）
    """

    last_active_at: Optional[datetime] = None
    """最后一次活跃的时间戳"""

    __orm_create_rule__ = "((group_id & !user_id) | (user_id & !group_id)) & last_active_at"

    __orm_select_rule__ = "id"

    __orm_update_rule__ = "last_active_at"

    @classmethod
    def from_orm(cls, chat_stream: ChatStream) -> "ChatStreamDTO":
        """从ORM对象创建DTO对象。"""
        return cls(
            id=chat_stream.id,
            created_at=chat_stream.created_at,
            group_id=chat_stream.group_id,
            user_id=chat_stream.user_id,
            last_active_at=chat_stream.last_active_at,
        )


def _pk(id: int):
    """构造缓存主键"""
    return f"chat_stream:pk:{id}"


def _user_platform_info_key(platform: str, platform_user_id: str):
    """构造缓存用户平台信息键"""
    return f"chat_stream:user_platform_info:{platform}:{platform_user_id}"


def _group_platform_info_key(platform: str, platform_group_id: str):
    """构造缓存群组平台信息键"""
    return f"chat_stream:group_platform_info:{platform}:{platform_group_id}"


class ChatStreamManager:
    @classmethod
    def get_chat_stream(
        cls,
        stream_id: Optional[int] = None,
        platform: Optional[str] = None,
        platform_user_id: Optional[str] = None,
        platform_group_id: Optional[str] = None,
    ) -> Optional[ChatStreamDTO]:
        """获取聊天流

        可选的查询参数组合（匹配优先级）：
        1. stream_id
        2. platform + platform_user_id (自动创建)
        3. platform + platform_group_id (自动创建)

        :param stream_id: 聊天流 ID
        :param platform: 平台名称
        :param platform_user_id: 平台用户 ID
        :param platform_group_id: 平台群组 ID
        :return: 聊天流 DTO 对象
        """

        def _get_by_pk(id: int) -> Optional[ChatStreamDTO]:
            """通过主键获取聊天流"""
            return chat_stream if (chat_stream := global_cache[_pk(id)]) else cls._get_stream_by_id(id)

        if stream_id:
            # 使用stream_id直接查询
            # 不会自动创建新的聊天流
            if chat_stream := _get_by_pk(stream_id):
                return chat_stream

            raise ValueError(f"ChatStream '{stream_id}' does not exist.")
        elif platform and platform_user_id:
            # 使用平台用户信息查询
            if stream_id := global_cache[_user_platform_info_key(platform, platform_user_id)]:
                if chat_stream := _get_by_pk(stream_id):
                    return chat_stream
            return cls._get_stream_by_user_info(platform, platform_user_id)
        elif platform and platform_group_id:
            # 使用平台群组信息查询
            if stream_id := global_cache[_group_platform_info_key(platform, platform_group_id)]:
                if chat_stream := _get_by_pk(stream_id):
                    return chat_stream
            return cls._get_stream_by_group_info(platform, platform_group_id)
        else:
            raise ValueError(
                "At least one of 'stream_id', 'platform + platform_user_id', or 'platform + platform_group_id' must be provided."
            )

    @classmethod
    def _get_stream_by_id(cls, stream_id: int) -> Optional[ChatStreamDTO]:
        """数据库操作：通过ChatStreamID获取聊天流信息"""
        with DBSession() as session:
            statement = select(ChatStream).where(ChatStream.id == stream_id)
            if result := session.exec(statement).first():
                # 缓存结果
                dto = ChatStreamDTO.from_orm(result)
            else:
                return None

        # 如果查询到结果，则将其存入缓存
        global_cache[_pk(stream_id)] = dto

        return dto

    @classmethod
    def _get_stream_by_user_info(cls, platform: str, platform_user_id: str) -> Optional[ChatStreamDTO]:
        """数据库操作：通过用户平台信息获取聊天流信息"""
        with DBSession() as session:
            statement = select(ChatUser).where(
                ChatUser.platform == platform,
                ChatUser.platform_user_id == platform_user_id,
            )

            user = session.exec(statement).first()

            if user is None:
                raise ValueError(f"User '{platform}:{platform_user_id}' does not exist.")

            chat_stream = user.chat_stream

        if chat_stream is None:
            dto = cls._create_stream(user_id=user.id)
        else:
            dto = ChatStreamDTO.from_orm(chat_stream)
            global_cache[_pk(dto.id)] = dto  # 主键缓存

        # 缓存键映射
        global_cache[_user_platform_info_key(platform, platform_user_id)] = dto.id

        return dto

    @classmethod
    def _get_stream_by_group_info(cls, platform: str, platform_group_id: str) -> Optional[ChatStreamDTO]:
        """数据库操作：通过群组平台信息获取聊天流信息"""
        with DBSession() as session:
            statement = select(ChatGroup).where(
                ChatGroup.platform == platform,
                ChatGroup.platform_group_id == platform_group_id,
            )

            group = session.exec(statement).first()

            if group is None:
                raise ValueError(f"Group '{platform}:{platform_group_id}' does not exist.")

            chat_stream = group.chat_stream

        if chat_stream is None:
            dto = cls._create_stream(group_id=group.id)
        else:
            dto = ChatStreamDTO.from_orm(chat_stream)
            global_cache[_pk(dto.id)] = dto  # 主键缓存

        # 缓存键映射
        global_cache[_group_platform_info_key(platform, platform_group_id)] = dto.id

        return dto

    @classmethod
    def _create_stream(cls, group_id: Optional[int] = None, user_id: Optional[int] = None) -> ChatStreamDTO:
        """创建聊天流
        （由于聊天流只能在get时被动创建，所以该方法不提供外部调用）
        """
        now = datetime.now()
        chat_stream = ChatStream(
            created_at=now,
            group_id=group_id,
            user_id=user_id,
            last_active_at=now,
        )

        with DBSession() as session:
            session.add(chat_stream)
            session.commit()
            session.refresh(chat_stream)

        dto = ChatStreamDTO.from_orm(chat_stream)

        # 缓存结果
        global_cache[_pk(dto.id)] = dto

        return dto

    @classmethod
    def update_stream(cls, dto: ChatStreamDTO) -> ChatStreamDTO:
        """更新聊天流

        :param dto: 聊天流DTO
        :return: 更新后的聊天流DTO
        """
        if dto.update_entity_check() is False:
            raise ValueError("Invalid DTO object for update.")

        with DBSession() as session:
            # 更新数据库中的聊天流
            statement = select(ChatStream).where(ChatStream.id == dto.id)
            chat_stream = session.exec(statement).first()

            if chat_stream is None:
                raise ValueError(f"ChatStream '{dto.id}' does not exist.")

            chat_stream.last_active_at = dto.last_active_at or chat_stream.last_active_at

            session.commit()
            session.refresh(chat_stream)
            dto = ChatStreamDTO.from_orm(chat_stream)

        # 更新缓存
        global_cache[_pk(dto.id)] = dto

        return dto
