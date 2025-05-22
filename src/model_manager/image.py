from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import select

from common.database.database import DBSession
from model_manager.dto_base import DTOBase
from src.manager.cache_manager import global_cache
from src.common.database.database_model import Image


@dataclass
class ImageDTO(DTOBase):
    """图片DTO"""

    created_at: Optional[datetime] = None
    """创建时间戳"""

    img_hash: Optional[str] = None
    """图像的哈希值（主键）"""

    description: Optional[str] = None
    """图像的描述"""

    query_count: Optional[int] = None
    """查询次数（用于统计图像被查询描述的次数）"""

    last_queried_at: Optional[datetime] = None
    """最后一次查询的时间戳"""

    __orm_create_rule__ = "img_hash"

    __orm_select_rule__ = "img_hash"

    __orm_update_rule__ = "description | query_count | last_queried_at"

    @classmethod
    def from_orm(cls, image: Image) -> "ImageDTO":
        """从ORM对象创建DTO对象。"""
        return cls(
            created_at=image.created_at,
            img_hash=image.img_hash,
            description=image.description,
            query_count=image.query_count,
            last_queried_at=image.last_queried_at,
        )


def _pk(img_hash: str):
    """构造缓存哈希键"""
    return f"image:pk:{img_hash}"


class ImageManager:
    @classmethod
    def create_image(cls, dto: ImageDTO) -> ImageDTO:
        """创建图像"""

        if dto.create_entity_check() is False:
            raise ValueError("Invalid DTO object for create.")
        if cls.get_image(dto):
            raise ValueError("Image already exists.")

        with DBSession() as session:
            # 创建图像对象
            now = datetime.now()
            image = Image(
                created_at=now,
                img_hash=dto.img_hash,
                description=dto.description,
                last_queried_at=now,
            )

            # 将图像对象添加到数据库会话
            session.add(image)
            session.commit()
            session.refresh(image)

            # 创建DTO对象
            dto = ImageDTO.from_orm(image)

        # 刷新缓存
        global_cache[_pk(dto.img_hash)] = dto

        return dto

    @classmethod
    def get_image(cls, dto: ImageDTO) -> Optional[ImageDTO]:
        """获取图像"""
        if dto.create_entity_check() is False:
            raise ValueError("Invalid DTO object for get.")

        if image := global_cache[_pk(hash)]:
            return image
        else:
            return cls._get_image_by_hash(hash)

    @classmethod
    def _get_image_by_hash(cls, image_hash: str) -> Optional[ImageDTO]:
        """数据库操作：通过哈希值获取图像"""
        with DBSession() as session:
            statement = select(Image).where(Image.img_hash == image_hash)

            if result := session.exec(statement).first():
                dto = ImageDTO.from_orm(result)
            else:
                return None

        # 如果查询到结果，则将其存入缓存
        global_cache[_pk(dto.img_hash)] = dto

        return dto

    @classmethod
    def update_image(cls, dto: ImageDTO) -> ImageDTO:
        """更新图像

        :param dto: 图像DTO
        :return: 更新后的图像DTO
        """
        if dto.update_entity_check() is False:
            raise ValueError("Invalid DTO object for update.")

        with DBSession() as session:
            # 更新数据库中的图像
            statement = select(Image).where(Image.img_hash == dto.img_hash)
            image = session.exec(statement).first()

            if image is None:
                raise ValueError(f"Image '{dto.img_hash}' does not exist.")

            # 更新图像信息
            image.description = dto.description
            image.query_count = dto.query_count
            image.last_queried_at = dto.last_queried_at

            session.commit()
            session.refresh(image)

            dto = ImageDTO.from_orm(image)

        # 刷新缓存
        global_cache[_pk(dto.img_hash)] = dto

        return dto
