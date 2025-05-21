from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import select

from common.database.database import DBSession
from model_manager.dto_base import DTOBase
from manager.cache_manager import global_cache
from src.common.database.database_model import PeopleRelationship


@dataclass
class PeopleRelationshipDTO(DTOBase):
    """
    用于存储人际关系数据的模型。
    """

    id: Optional[int] = None
    """主键（由数据库创建，自动递增）"""

    created_at: Optional[datetime] = None
    """创建时间戳"""

    real_name: Optional[str] = None
    """真实姓名（可能为空）"""

    nickname: Optional[str] = None
    """昵称（方便称呼的昵称，可能为空）"""

    nickname_reason: Optional[str] = None
    """昵称设定的原因（可能为空）"""

    relationship_value: Optional[float] = None
    """关系值"""

    msg_interval: Optional[float] = None
    """消息间隔（秒）"""

    __orm_create_rule__ = ""

    __orm_select_rule__ = "id"

    __orm_update_rule__ = "real_name | nickname | nickname_reason | relationship_value | msg_interval"

    @classmethod
    def from_orm(cls, people_relationship: PeopleRelationship) -> "PeopleRelationshipDTO":
        """从ORM对象创建DTO对象。"""
        return cls(
            id=people_relationship.id,
            created_at=people_relationship.created_at,
            real_name=people_relationship.real_name,
            nickname=people_relationship.nickname,
            nickname_reason=people_relationship.nickname_reason,
            relationship_value=people_relationship.relationship_value,
            msg_interval=people_relationship.msg_interval,
        )


def _pk(id: int):
    """构造缓存主键"""
    return f"people_relationship:pk:{id}"


class PeopleRelationshipManager:
    @classmethod
    def create_relationship(cls, relationship_dto: PeopleRelationshipDTO) -> PeopleRelationshipDTO:
        """创建人际关系

        :param relationship_dto: 人际关系DTO
        :return: 创建成功的人际关系DTO
        """
        if relationship_dto.create_entity_check() is False:
            raise ValueError("Invalid DTO object for create.")

        # 无法进行存在性检查，使用该func时应在逻辑上确保对应的关系不存在

        with DBSession() as session:
            # 创建新的关系对象
            relationship = PeopleRelationship(
                created_at=datetime.now(),
                real_name=relationship_dto.real_name,
                nickname=relationship_dto.nickname,
                nickname_reason=relationship_dto.nickname_reason,
                relationship_value=relationship_dto.relationship_value,
                msg_interval=relationship_dto.msg_interval,
            )
            session.add(relationship)
            session.commit()
            session.refresh(relationship)

            dto = PeopleRelationshipDTO.from_orm(relationship)

        # 刷新缓存
        global_cache[_pk(dto.id)] = dto

        return dto

    @classmethod
    def get_relationship(cls, dto: PeopleRelationshipDTO) -> Optional[PeopleRelationshipDTO]:
        """获取人际关系

        :param relationship_dto: 人际关系DTO
        :return: 获取到的人际关系DTO
        """

        if dto.select_entity_check() is False:
            raise ValueError("Invalid DTO object for select.")

        if relationship := global_cache.get(_pk(dto.id)):
            return relationship
        else:
            return cls._get_relationship_by_id(dto.id)

    @classmethod
    def _get_relationship_by_id(cls, id: int) -> Optional[PeopleRelationshipDTO]:
        """数据库操作：根据ID获取人际关系"""
        with DBSession() as session:
            statement = select(PeopleRelationship).where(PeopleRelationship.id == id)
            if relationship := session.exec(statement).first():
                dto = PeopleRelationshipDTO.from_orm(relationship)
            else:
                return None

        # 如果查询到结果，则将其存入缓存
        global_cache[_pk(dto.id)] = dto

        return dto

    @classmethod
    def update_relationship(cls, dto: PeopleRelationshipDTO) -> PeopleRelationshipDTO:
        """更新人际关系

        :param relationship_dto: 人际关系DTO
        :return: 更新后的人际关系DTO
        """
        if dto.update_entity_check() is False:
            raise ValueError("Invalid DTO object for update.")

        with DBSession() as session:
            # 更新数据库中的人际关系
            statement = select(PeopleRelationship).where(PeopleRelationship.id == dto.id)
            relationship = session.exec(statement).first()

            if relationship is None:
                raise ValueError(f"PeopleRelationship '{dto.id}' does not exist.")

            # 更新人际关系信息
            relationship.real_name = dto.real_name or relationship.real_name
            relationship.nickname = dto.nickname or relationship.nickname
            relationship.nickname_reason = dto.nickname_reason or relationship.nickname_reason
            relationship.relationship_value = dto.relationship_value or relationship.relationship_value
            relationship.msg_interval = dto.msg_interval or relationship.msg_interval

            # 提交更改
            session.commit()
            session.refresh(relationship)
            dto = PeopleRelationshipDTO.from_orm(relationship)

        # 刷新缓存
        global_cache[_pk(dto.id)] = dto

        return dto
