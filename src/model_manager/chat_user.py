from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import select
from model_manager.people_relationship import PeopleRelationshipDTO, PeopleRelationshipManager
from src.common.database.database import DBSession
from src.common.database.database_model import ChatUser
from src.manager.cache_manager import global_cache
from model_manager.dto_base import DTOBase


@dataclass
class ChatUserDTO(DTOBase):
    """聊天用户DTO"""

    id: Optional[int] = None
    """主键（由数据库创建，自动递增）"""

    created_at: Optional[datetime] = None
    """创建时间戳"""

    platform: Optional[str] = None
    """平台名称"""

    platform_user_id: Optional[str] = None
    """平台用户 ID（如 QQ 号）"""

    user_name: Optional[str] = None
    """用户名称 (可能为空)"""

    platform_spec_info: Optional[str] = None
    """平台特定的信息 (可能为空)"""

    relation_id: Optional[int] = None
    """人际关系ID
    （外键，指向 PeopleRelationship 表）
    当一个新ChatUser对象被创建时，要么同样的创建一个新的Relationship对象，要么将其与一个已经存在的Relationship对象关联
    """

    __orm_create_rule__ = "platform & platform_user_id & relation_id"

    __orm_select_rule__ = "id | (platform & platform_user_id)"

    __orm_update_rule__ = "user_name | platform_spec_info"

    @classmethod
    def from_orm(cls, chat_user: ChatUser) -> "ChatUserDTO":
        """从ORM对象创建DTO对象。"""
        return cls(
            id=chat_user.id,
            created_at=chat_user.created_at,
            platform=chat_user.platform,
            platform_user_id=chat_user.platform_user_id,
            user_name=chat_user.user_name,
            platform_spec_info=chat_user.platform_spec_info,
            relation_id=chat_user.relation_id,
        )


def _pk(id: int):
    """构造缓存主键"""
    return f"chat_user:pk:{id}"


def _platform_info_key(platform: str, platform_user_id: str):
    """构造缓存平台信息键"""
    return f"chat_user:platform_info:{platform}:{platform_user_id}"


class ChatUserManager:
    @classmethod
    def create_user(cls, dto: ChatUserDTO) -> ChatUserDTO:
        """创建用户"""
        if dto.create_entity_check() is False:
            raise ValueError("Invalid DTO object for create.")
        if cls.get_chat_user(dto):
            return ValueError("ChatUser already exists.")

        # 确保关系对象存在
        if dto.relation_id:
            if not PeopleRelationshipManager.get_relationship(PeopleRelationshipDTO(id=dto.relation_id)):
                raise ValueError(f"PeopleRelationship '{dto.relation_id}' does not exist.")
        else:
            # 未提供关系对象外键，创建新的关系对象
            relationship_dto = PeopleRelationshipDTO()
            dto.relation_id = PeopleRelationshipManager.create_relationship(relationship_dto).id

        with DBSession() as session:
            # 创建新的用户对象
            chat_user = ChatUser(
                created_at=datetime.now(),
                platform=dto.platform,
                platform_user_id=dto.platform_user_id,
                user_name=dto.user_name,
                platform_spec_info=dto.platform_spec_info,
                relation_id=dto.relation_id,
            )
            session.add(chat_user)
            session.commit()
            session.refresh(chat_user)

            dto = ChatUserDTO.from_orm(chat_user)

        # 刷新缓存
        global_cache[_pk(dto.id)] = dto
        global_cache[_platform_info_key(dto.platform, dto.platform_user_id)] = dto.id

        return dto

    @classmethod
    def get_chat_user(cls, dto: ChatUserDTO) -> Optional[ChatUserDTO]:
        """获取用户信息

        :param dto: 用户DTO
        :return: 获取到的用户DTO
        """
        if dto.select_entity_check() is False:
            raise ValueError("Invalid DTO object for select.")

        if dto.id:
            if group := global_cache[_pk(dto.id)]:
                return group
            else:
                return cls._get_user_by_id(dto.id)
        elif group := global_cache[_platform_info_key(dto.platform, dto.platform_user_id)]:
            return group
        else:
            return cls._get_user_by_platform_info(dto.platform, dto.platform_user_id)

    @classmethod
    def _get_user_by_id(cls, id: int) -> Optional[ChatUserDTO]:
        """数据库操作：通过user_id获取用户信息"""
        with DBSession() as session:
            statement = select(ChatUser).where(ChatUser.id == id)

            if result := session.exec(statement).first():
                dto = ChatUserDTO.from_orm(result)
            else:
                return None

        # 如果查询到结果，则将其存入缓存
        global_cache[_pk(dto.id)] = dto
        global_cache[_platform_info_key(dto.platform, dto.platform_user_id)] = dto.id

        return dto

    @classmethod
    def _get_user_by_platform_info(cls, platform: str, platform_user_id: str) -> Optional[ChatUserDTO]:
        """数据库操作：通过plat_form_info获取用户信息"""
        with DBSession() as session:
            statement = select(ChatUser).where(
                ChatUser.platform == platform,
                ChatUser.platform_user_id == platform_user_id,
            )
            if result := session.exec(statement).first():
                # 如果查询到结果，则将其存入缓存
                dto = ChatUserDTO.from_orm(result)
            else:
                return None

        # 如果查询到结果，则将其存入缓存
        global_cache[_pk(dto.id)] = dto
        global_cache[_platform_info_key(dto.platform, dto.platform_user_id)] = dto.id

        return dto

    @classmethod
    def update_user(cls, dto: ChatUserDTO) -> ChatUserDTO:
        """更新用户信息

        :param dto: 用户DTO
        """
        if dto.update_entity_check() is False:
            raise ValueError("Invalid DTO object for update.")

        with DBSession() as session:
            # 更新数据库中的用户信息
            if dto.id:
                statement = select(ChatUser).where(ChatUser.id == dto.id)
            else:
                statement = select(ChatUser).where(
                    ChatUser.platform == dto.platform,
                    ChatUser.platform_user_id == dto.platform_user_id,
                )
            user = session.exec(statement).first()

            if user is None:
                if dto.id:
                    raise ValueError(f"ChatUser '{dto.id}' does not exist.")
                else:
                    raise ValueError(f"ChatUser '{dto.platform}:{dto.platform_user_id}' does not exist.")

            # 更新用户信息
            user.user_name = dto.user_name or user.user_name
            user.platform_spec_info = dto.platform_spec_info or user.platform_spec_info

            # 提交更改
            session.commit()
            session.refresh(user)
            dto = ChatUserDTO.from_orm(user)

        # 更新缓存
        global_cache[_pk(dto.id)] = dto
        global_cache[_platform_info_key(dto.platform, dto.platform_user_id)] = dto.id

        return dto
