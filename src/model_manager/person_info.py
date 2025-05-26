from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import select

from common.database.database import DBSession
from model_manager.dto_base import DTOBase
from manager.cache_manager import global_cache
from src.common.database.database_model import PersonInfo


@dataclass
class PersonInfoDTO(DTOBase):
    """
    用于存储个体信息数据的模型。
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

    __orm_create_rule__ = ""

    __orm_select_rule__ = "id | nickname"

    __orm_update_rule__ = "real_name | nickname | nickname_reason | relationship_value"

    @classmethod
    def from_orm(cls, people_relationship: PersonInfo) -> "PersonInfoDTO":
        """从ORM对象创建DTO对象。"""
        return cls(
            id=people_relationship.id,
            created_at=people_relationship.created_at,
            real_name=people_relationship.real_name,
            nickname=people_relationship.nickname,
            nickname_reason=people_relationship.nickname_reason,
            relationship_value=people_relationship.relationship_value,
        )


def _pk(id: int):
    """构造缓存主键"""
    return f"person_info:pk:{id}"


def _nickname_key(nickname: str):
    """构造缓存主键（根据昵称）"""
    return f"person_info:nickname:{nickname}"


class PersonInfoManager:
    @classmethod
    def create_person_info(cls, dto: PersonInfoDTO) -> PersonInfoDTO:
        """创建个体信息

        :param relationship_dto: 个体信息DTO
        :return: 创建成功的个体信息DTO
        """
        if dto.create_entity_check() is False:
            raise ValueError("Invalid DTO object for create.")
        if dto.nickname and global_cache.get(_nickname_key(dto.nickname)):
            raise ValueError(f"PersonInfo with Nickname '{dto.nickname}' already exists.")

        with DBSession() as session:
            # 创建新的关系对象
            relationship = PersonInfo(
                created_at=datetime.now(),
                real_name=dto.real_name,
                nickname=dto.nickname,
                nickname_reason=dto.nickname_reason,
                relationship_value=dto.relationship_value,
                msg_interval=dto.msg_interval,
            )
            session.add(relationship)
            session.commit()
            session.refresh(relationship)

            dto = PersonInfoDTO.from_orm(relationship)

        # 刷新缓存
        global_cache[_pk(dto.id)] = dto

        if dto.nickname:
            global_cache[_nickname_key(dto.nickname)] = dto.id

        return dto

    @classmethod
    def get_person_info(cls, dto: PersonInfoDTO) -> Optional[PersonInfoDTO]:
        """获取个体信息

        :param relationship_dto: 个体信息DTO
        :return: 获取到的个体信息DTO
        """

        if dto.select_entity_check() is False:
            raise ValueError("Invalid DTO object for select.")

        def _get_by_pk(id: int) -> Optional[PersonInfoDTO]:
            """根据ID获取个体信息"""
            if relationship := global_cache.get(_pk(dto.id)):
                return relationship
            else:
                return cls._get_person_info_by_id(dto.id)

        if dto.id:
            return _get_by_pk(dto.id)
        else:
            # 根据昵称获取个体信息
            if person_info_id := global_cache.get(_nickname_key(dto.nickname)):
                return _get_by_pk(person_info_id)
            else:
                return cls._get_person_info_by_nickname(dto.nickname)

    @classmethod
    def _get_person_info_by_id(cls, id: int) -> Optional[PersonInfoDTO]:
        """数据库操作：根据ID获取个体信息"""
        with DBSession() as session:
            statement = select(PersonInfo).where(PersonInfo.id == id)
            if relationship := session.exec(statement).first():
                dto = PersonInfoDTO.from_orm(relationship)
            else:
                return None

        # 如果查询到结果，则将其存入缓存
        global_cache[_pk(dto.id)] = dto
        if dto.nickname:
            global_cache[_nickname_key(dto.nickname)] = dto.id

        return dto

    @classmethod
    def _get_person_info_by_nickname(cls, nickname: str) -> Optional[PersonInfoDTO]:
        """数据库操作：根据昵称获取个体信息"""
        with DBSession() as session:
            statement = select(PersonInfo).where(PersonInfo.nickname == nickname)
            if relationship := session.exec(statement).first():
                dto = PersonInfoDTO.from_orm(relationship)
            else:
                return None

        # 如果查询到结果，则将其存入缓存
        global_cache[_pk(dto.id)] = dto
        global_cache[_nickname_key(dto.nickname)] = dto.id

        return dto

    @classmethod
    def count_by_relationship_value(cls, min_relationship_value: float) -> int:
        """获取关系值大于等于指定值的个体个数

        :param min_relationship_value: 最小关系值
        :return: 满足条件的个体数量
        """
        with DBSession() as session:
            statement = select(PersonInfo).where(PersonInfo.relationship_value >= min_relationship_value)
            count = session.exec(statement).count()
        return count

    @classmethod
    def update_person_info(cls, dto: PersonInfoDTO) -> PersonInfoDTO:
        """更新个体信息

        :param relationship_dto: 个体信息DTO
        :return: 更新后的个体信息DTO
        """
        if dto.update_entity_check() is False:
            raise ValueError("Invalid DTO object for update.")

        with DBSession() as session:
            # 更新数据库中的个体信息
            statement = select(PersonInfo).where(PersonInfo.id == dto.id)
            relationship = session.exec(statement).first()

            if relationship is None:
                raise ValueError(f"PersonInfo '{dto.id}' does not exist.")

            old_nickname = relationship.nickname

            # 更新个体信息
            relationship.real_name = dto.real_name or relationship.real_name
            relationship.nickname = dto.nickname or relationship.nickname
            relationship.nickname_reason = dto.nickname_reason or relationship.nickname_reason
            relationship.relationship_value = dto.relationship_value or relationship.relationship_value
            relationship.msg_interval = dto.msg_interval or relationship.msg_interval

            # 提交更改
            session.commit()
            session.refresh(relationship)
            dto = PersonInfoDTO.from_orm(relationship)

        # 刷新缓存
        global_cache[_pk(dto.id)] = dto
        if old_nickname != dto.nickname:
            # 如果昵称发生变化，更新缓存
            del global_cache[_nickname_key(old_nickname)]
            global_cache[_nickname_key(dto.nickname)] = dto.id

        return dto
