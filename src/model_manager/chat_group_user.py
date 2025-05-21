from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import select
from model_manager.chat_group import ChatGroupDTO, ChatGroupManager
from model_manager.chat_user import ChatUserDTO, ChatUserManager
from model_manager.dto_base import DTOBase
from src.common.database.database import DBSession
from src.common.database.database_model import ChatGroupUser
from src.manager.cache_manager import global_cache


@dataclass
class ChatGroupUserDTO(DTOBase):
    """聊天组用户DTO"""

    group_id: Optional[int] = None
    """群组 ID （联合主键）"""

    user_id: Optional[int] = None
    """用户 ID （联合主键）"""

    created_at: Optional[datetime] = None
    """创建时间戳"""

    platform: Optional[str] = None
    """平台名称"""

    user_group_name: Optional[str] = None
    """用户在群组中的名称（可能为空）"""

    platform_spec_info: Optional[str] = None
    """平台特定的信息 (可能为空)"""

    __orm_create_rule__ = "group_id & user_id & created_at & platform"

    __orm_select_rule__ = "group_id & user_id"

    __orm_update_rule__ = "user_group_name | platform_spec_info"


def _pk(group_id: int, user_id: int):
    """构造缓存主键"""
    return f"chat_group_user:pk:{group_id}:{user_id}"


class ChatGroupUserManager:
    @classmethod
    def create_group_user(cls, dto: ChatGroupUserDTO) -> ChatGroupUserDTO:
        """创建群组用户

        :param dto: 群组用户DTO
        :return: 创建的群组用户DTO
        """
        if dto.create_entity_check() is False:
            raise ValueError("Invalid DTO object for create.")
        if cls.get_group_user(dto):
            raise ValueError("Group user already exists.")

        # 确保群组和用户存在
        if ChatGroupManager.get_chat_group(ChatGroupDTO(id=dto.group_id)) is None:
            raise ValueError(f"ChatGroup '{dto.group_id}' does not exist.")
        if ChatUserManager.get_chat_user(ChatUserDTO(id=dto.user_id)) is None:
            raise ValueError(f"ChatUser '{dto.user_id}' does not exist.")

        with DBSession() as session:
            # 创建群组用户对象
            group_user = ChatGroupUser(
                group_id=dto.group_id,
                user_id=dto.user_id,
                created_at=datetime.now(),
                platform=dto.platform,
                user_group_name=dto.user_group_name,
                platform_spec_info=dto.platform_spec_info,
            )

            session.add(group_user)
            session.commit()
            session.refresh(group_user)

            # 创建DTO
            dto = ChatGroupUserDTO.from_orm(group_user)

        # 刷新缓存
        global_cache[_pk(dto.group_id, dto.user_id)] = dto

        return dto

    @classmethod
    def get_group_user(cls, dto: ChatGroupUserDTO) -> Optional[ChatGroupUserDTO]:
        """获取群组用户信息

        :param dto: 群组用户DTO
        :return: 获取到的群组用户DTO
        """
        if dto.select_entity_check() is False:
            raise ValueError("Invalid DTO object for select.")

        if group_user := global_cache[_pk(dto.group_id, dto.user_id)]:
            return group_user
        else:
            return cls._get_member_by_joint_ids(dto.group_id, dto.user_id)

    @classmethod
    def _get_member_by_joint_ids(cls, group_id: int, user_id: int) -> Optional[ChatGroupUserDTO]:
        """通过联合主键获取群组成员信息"""
        with DBSession() as session:
            statement = select(ChatGroupUser).where(
                ChatGroupUser.group_id == group_id,
                ChatGroupUser.user_id == user_id,
            )
            if result := session.exec(statement).first():
                dto = ChatGroupUserDTO.from_orm(result)
            else:
                return None

        # 如果查询到结果，则将其存入缓存
        global_cache[_pk(dto.group_id, dto.user_id)] = dto

        return dto

    @classmethod
    def update_group_user(cls, dto: ChatGroupUserDTO) -> ChatGroupUserDTO:
        """更新群组用户信息

        :param dto: 群组用户DTO
        :return: 更新后的群组用户DTO
        """

        if dto.update_entity_check() is False:
            raise ValueError("Invalid DTO object for update.")

        with DBSession() as session:
            # 更新数据库中的群组用户信息
            statement = select(ChatGroupUser).where(
                ChatGroupUser.group_id == dto.group_id,
                ChatGroupUser.user_id == dto.user_id,
            )
            group_user = session.exec(statement).first()

            if group_user is None:
                raise ValueError(f"ChatGroupUser '{dto.group_id}:{dto.user_id}' does not exist.")

            # 更新群组用户信息
            group_user.user_group_name = dto.user_group_name or group_user.user_group_name
            group_user.platform_spec_info = dto.platform_spec_info or group_user.platform_spec_info

            session.commit()
            session.refresh(group_user)
            dto = ChatGroupUserDTO.from_orm(group_user)

        # 更新缓存
        global_cache[_pk(dto.group_id, dto.user_id)] = dto

        return dto
