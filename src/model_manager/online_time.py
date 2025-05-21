from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import exists, select
from common.database.database import DBSession
from common.database.database_model import OnlineTimeRecord
from model_manager.dto_base import DTOBase


@dataclass
class OnlineTimeRecordDTO(DTOBase):
    """在线时长DTO"""

    id: Optional[int] = None
    """主键（由数据库创建，自动递增）"""

    start_timestamp: Optional[datetime] = None
    """开始时间戳"""

    end_timestamp: Optional[datetime] = None
    """结束时间戳"""

    __orm_create_rule__ = "start_timestamp & end_timestamp"

    __orm_select_rule__ = "id | start_timestamp | end_timestamp"

    __orm_update_rule__ = "end_timestamp"

    @classmethod
    def from_orm(cls, entity: OnlineTimeRecord) -> "OnlineTimeRecordDTO":
        """从 ORM 实体创建 DTO 对象"""
        return cls(
            id=entity.id,
            start_timestamp=entity.start_timestamp,
            end_timestamp=entity.end_timestamp,
        )


class OnlineTimeRecordManager:
    @classmethod
    def create_online_time_record(cls, dto: OnlineTimeRecordDTO) -> OnlineTimeRecordDTO:
        """创建在线时长记录

        :param dto: 在线时长DTO
        :return: 创建的在线时长DTO
        """
        if dto.create_entity_check() is False:
            raise ValueError("Invalid DTO object for create.")

        with DBSession() as session:
            # 检查是否存在相同的开始时间戳
            if session.exec(select(exists().where(OnlineTimeRecord.start_timestamp == dto.start_timestamp))).first():
                raise ValueError("Online time record with the same start timestamp already exists.")

            online_time = OnlineTimeRecord(
                start_timestamp=dto.start_timestamp,
                end_timestamp=dto.end_timestamp,
            )
            session.add(online_time)
            session.commit()
            session.refresh(online_time)

            dto = OnlineTimeRecordDTO.from_orm(online_time)

        return dto

    @classmethod
    def update_online_time_record(cls, dto: OnlineTimeRecordDTO) -> OnlineTimeRecordDTO:
        """更新在线时长记录

        :param dto: 在线时长DTO
        :return: 更新后的在线时长DTO
        """
        if dto.update_entity_check() is False:
            raise ValueError("Invalid DTO object for update.")

        with DBSession() as session:
            # 更新数据库中的在线时长记录
            statement = select(OnlineTimeRecord).where(OnlineTimeRecord.id == dto.id)
            online_time = session.exec(statement).first()

            if online_time is None:
                raise ValueError(f"Online time record '{dto.id}' does not exist.")

            online_time.start_timestamp = dto.start_timestamp
            online_time.end_timestamp = dto.end_timestamp

            session.add(online_time)
            session.commit()
            session.refresh(online_time)

            dto = OnlineTimeRecordDTO.from_orm(online_time)

        return dto

    @classmethod
    def get_latest_online_time(cls) -> Optional[OnlineTimeRecordDTO]:
        """获取最新的在线时长记录

        :return: 最新的在线时长DTO
        """
        with DBSession() as session:
            statement = select(OnlineTimeRecord).order_by(OnlineTimeRecord.end_timestamp.desc())
            if online_time := session.exec(statement).first():
                dto = OnlineTimeRecordDTO.from_orm(online_time)
            else:
                return None

        return dto

    @classmethod
    def get_record_between_timestamps(cls, start_t: datetime, end_t: datetime = None) -> list[OnlineTimeRecordDTO]:
        """获取指定时间范围内的在线时长记录（筛选索引为Record的end_timestamp）

        :param start_t: 开始时间戳
        :param end_t: 结束时间戳（可选，不提供则默认为当前时间）
        :return: 在线时长DTO
        """
        if end_t is None:
            end_t = datetime.now()

        with DBSession() as session:
            # 筛选任何 end_timestamp 位于 (start_t, end_t] 区间的记录
            # 筛选任何 start_timestamp 位于 [start_t, end_t) 区间的记录
            statement = select(OnlineTimeRecord).where(
                ((OnlineTimeRecord.end_timestamp > start_t) & (OnlineTimeRecord.end_timestamp <= end_t))
                | ((OnlineTimeRecord.start_timestamp >= start_t) & (OnlineTimeRecord.start_timestamp < end_t))
            )
            records = session.exec(statement).all()
            if not records:
                return []

        # 将 ORM 实体转换为 DTO 对象
        return [OnlineTimeRecordDTO.from_orm(record) for record in records]
