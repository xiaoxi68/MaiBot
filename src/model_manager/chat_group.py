from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import select
from src.common.database.database import DBSession
from src.common.database.database_model import ChatGroup
from src.manager.cache_manager import global_cache
from model_manager.dto_base import DTOBase


@dataclass
class ChatGroupDTO(DTOBase):
    """
    聊天组DTO
    """

    id: Optional[int] = None
    """主键（由数据库创建，自动递增）"""

    created_at: Optional[datetime] = None
    """创建时间戳"""

    platform: Optional[str] = None
    """平台名称"""

    platform_group_id: Optional[str] = None
    """平台群组 ID （如 QQ 群号）"""

    group_name: Optional[str] = None
    """群组名称（可能为空）"""

    platform_spec_info: Optional[str] = None
    """平台特定的信息（可能为空）"""

    __orm_create_rule__ = "platform & platform_group_id"

    __orm_select_rule__ = "id | (platform & platform_group_id)"

    __orm_update_rule__ = "group_name | platform_spec_info"

    @classmethod
    def from_orm(cls, chat_group: ChatGroup) -> "ChatGroupDTO":
        """从ORM对象创建DTO对象。"""
        return cls(
            id=chat_group.id,
            created_at=chat_group.created_at,
            platform=chat_group.platform,
            platform_group_id=chat_group.platform_group_id,
            group_name=chat_group.group_name,
            platform_spec_info=chat_group.platform_spec_info,
        )


def _pk(id: int):
    """构造缓存主键"""
    return f"chat_group:pk:{id}"


def _platform_info_key(platform: str, platform_group_id: str):
    """构造缓存平台信息键"""
    return f"chat_group:platform_info:{platform}:{platform_group_id}"


class ChatGroupManager:
    @classmethod
    def create_chat_group(cls, dto: ChatGroupDTO) -> ChatGroupDTO:
        """创建聊天组

        :param group_dto: 聊天组DTO
        :return: 创建成功的聊天组DTO
        """
        if dto.create_entity_check() is False:
            raise ValueError("Invalid DTO object for create.")
        if cls.get_chat_group(dto):
            raise ValueError("ChatGroup already exists.")

        with DBSession() as session:
            # 创建新的聊天组对象
            chat_group = ChatGroup(
                created_at=datetime.now(),
                platform=dto.platform,
                platform_group_id=dto.platform_group_id,
                group_name=dto.group_name,
                platform_spec_info=dto.platform_spec_info,
            )
            session.add(chat_group)
            session.commit()
            session.refresh(chat_group)

            dto = ChatGroupDTO.from_orm(chat_group)

        # 刷新缓存
        global_cache[_pk(dto.id)] = dto
        global_cache[_platform_info_key(dto.platform, dto.platform_group_id)] = dto.id

        return dto

    @classmethod
    def get_chat_group(cls, dto: ChatGroupDTO) -> Optional[ChatGroupDTO]:
        """获取聊天组信息

        :param dto: 聊天组DTO
        :return: 获取到的聊天组DTO
        """
        if dto.select_entity_check() is False:
            raise ValueError("Invalid DTO object for select.")

        if dto.id:
            if group := global_cache[_pk(dto.id)]:
                return group
            else:
                return cls._get_group_by_id(dto)
        elif group := global_cache[_platform_info_key(dto.platform, dto.platform_group_id)]:
            return group
        else:
            return cls._get_group_by_platform_info(dto)

    @classmethod
    def _get_group_by_id(cls, dto: ChatGroupDTO) -> Optional[ChatGroupDTO]:
        """数据库操作：通过 group_id 获取群组信息"""
        with DBSession() as session:
            statement = select(ChatGroup).where(ChatGroup.id == dto.id)

            if result := session.exec(statement).first():
                dto = ChatGroupDTO.from_orm(result)
            else:
                return None

        # 如果查询到结果，则将其存入缓存
        global_cache[_pk(dto.id)] = dto
        global_cache[_platform_info_key(dto.platform, dto.platform_group_id)] = dto.id

        return dto

    @classmethod
    def _get_group_by_platform_info(cls, dto: ChatGroupDTO) -> Optional[ChatGroupDTO]:
        """数据库操作：通过 platform_info 获取群组信息"""
        with DBSession() as session:
            statement = select(ChatGroup).where(
                ChatGroup.platform == dto.platform,
                ChatGroup.platform_group_id == dto.platform_group_id,
            )
            if result := session.exec(statement).first():
                dto = ChatGroupDTO.from_orm(result)
            else:
                return None

        # 如果查询到结果，则将其存入缓存
        global_cache[_pk(dto.id)] = dto
        global_cache[_platform_info_key(dto.platform, dto.platform_group_id)] = dto.id

        return dto

    @classmethod
    def update_group(cls, dto: ChatGroupDTO) -> Optional[ChatGroupDTO]:
        """更新群组信息

        :param dto: 群组DTO
        :return: 更新后的群组DTO
        """
        if dto.update_entity_check() is False:
            raise ValueError("Invalid DTO object for update.")

        with DBSession() as session:
            # 更新数据库中的用户信息
            if dto.id:
                statement = select(ChatGroup).where(ChatGroup.id == dto.id)
            else:
                statement = select(ChatGroup).where(
                    ChatGroup.platform == dto.platform,
                    ChatGroup.platform_group_id == dto.platform_group_id,
                )
            group = session.exec(statement).first()

            if group is None:
                if dto.id:
                    raise ValueError(f"ChatGroup '{dto.id}' does not exist.")
                else:
                    raise ValueError(f"ChatGroup '{dto.platform}:{dto.platform_group_id}' does not exist.")

            # 更新群组信息
            group.group_name = dto.group_name or group.group_name
            group.platform_spec_info = dto.platform_spec_info or group.platform_spec_info

            # 提交更改
            session.commit()
            session.refresh(group)
            dto = ChatGroupDTO.from_orm(group)

        # 更新缓存
        global_cache[_pk(dto.id)] = dto
        global_cache[_platform_info_key(dto.platform, dto.platform_group_id)] = dto.id

        return dto
