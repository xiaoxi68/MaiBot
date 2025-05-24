from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import select

from common.database.database import DBSession
from common.database.database_model import Emoji
from model_manager.dto_base import DTOBase
from model_manager.image import ImageDTO, ImageManager
from src.manager.cache_manager import global_cache


@dataclass
class EmojiDTO(DTOBase):
    """表情DTO"""

    created_at: Optional[datetime] = None
    """创建时间戳"""

    img_hash: Optional[str] = None
    """图像的哈希值（主键）
    （外键，指向 Images 表）
    """

    file_name: Optional[str] = None
    """图像文件的文件名"""

    is_banned: Optional[bool] = None
    """是否被禁止使用/注册（默认为 False）"""

    is_registered: Optional[bool] = None
    """是否已注册（默认为 False）"""

    last_try_register_at: Optional[datetime] = None
    """最后一次尝试注册的时间戳（默认为None）"""

    emotions: Optional[str] = None
    """表情包的情感描述（列表序列化为 JSON 字符串）"""

    usage_count: Optional[int] = None
    """使用次数（用于统计表情包被使用的次数）"""

    last_used_at: Optional[datetime] = None
    """最后一次使用的时间戳（如果未使用，则为 None）"""

    __orm_create_rule__ = "img_hash & emotions"

    __orm_select_rule__ = "img_hash"

    __orm_update_rule__ = "file_name | is_banned | is_registered | last_try_register_at | usage_count | last_used_at"

    @classmethod
    def from_orm(cls, emoji: Emoji) -> "EmojiDTO":
        """从ORM对象创建DTO对象。"""
        return cls(
            created_at=emoji.created_at,
            img_hash=emoji.img_hash,
            file_name=emoji.file_name,
            is_banned=emoji.is_banned,
            is_registered=emoji.is_registered,
            last_try_register_at=emoji.last_try_register_at,
            emotions=emoji.emotions,
            usage_count=emoji.usage_count,
            last_used_at=emoji.last_used_at,
        )


def _pk(img_hash: str):
    """构造缓存主键"""
    return f"emoji:pk:{img_hash}"


class EmojiManager:
    @classmethod
    def create_emoji(cls, dto: EmojiDTO) -> EmojiDTO:
        """创建表情包

        :param dto: 表情包DTO
        :return: 创建的表情包DTO
        """
        if dto.create_entity_check() is False:
            raise ValueError("Invalid DTO object for create.")
        if cls.get_emoji(dto):
            raise ValueError("Emoji already exists.")

        # 确保图像存在
        if ImageManager.get_image(ImageDTO(img_hash=dto.img_hash)) is None:
            raise ValueError(f"Image '{dto.img_hash}' does not exist.")

        with DBSession() as session:
            now = datetime.now()
            emoji = Emoji(
                created_at=now,
                img_hash=dto.img_hash,
                emotions=dto.emotions,
            )

            session.add(emoji)
            session.commit()
            session.refresh(emoji)

            # 创建DTO对象
            dto = EmojiDTO.from_orm(emoji)

        # 刷新缓存
        global_cache[_pk(dto.img_hash)] = dto

        return dto

    @classmethod
    def get_emoji(cls, dto: EmojiDTO) -> Optional[EmojiDTO]:
        """获取表情包

        :param dto: 表情包DTO
        :return: 表情包DTO
        """
        if dto.select_entity_check() is False:
            raise ValueError("Invalid DTO object for select.")

        if emoji := global_cache.get(_pk(dto.img_hash)):
            return emoji
        else:
            return cls._get_emoji_by_hash(dto.img_hash)

    @classmethod
    def _get_emoji_by_hash(cls, img_hash: str) -> Optional[EmojiDTO]:
        """数据库操作：通过图像哈希值获取表情包信息"""
        with DBSession() as session:
            statement = select(Emoji).where(Emoji.img_hash == img_hash)

            if emoji := session.exec(statement).first():
                dto = EmojiDTO.from_orm(emoji)
            else:
                return None

        # 缓存结果
        global_cache[_pk(dto.img_hash)] = dto

        return dto

    @classmethod
    def get_all_emojis(cls) -> list[EmojiDTO]:
        """获取所有表情包

        :return: 表情包DTO列表
        """
        with DBSession() as session:
            statement = select(Emoji)
            emojis = session.exec(statement).all()

            return [EmojiDTO.from_orm(emoji) for emoji in emojis]

    @classmethod
    def get_all_registered_emojis(cls) -> list[EmojiDTO]:
        """获取所有注册的表情包

        :return: 表情包DTO列表
        """
        with DBSession() as session:
            statement = select(Emoji).where(Emoji.is_registered is True)
            emojis = session.exec(statement).all()

            return [EmojiDTO.from_orm(emoji) for emoji in emojis]

    @classmethod
    def update_emoji(cls, dto: EmojiDTO) -> EmojiDTO:
        """更新表情包

        :param dto: 表情包DTO
        :return: 更新后的表情包DTO
        """
        if dto.update_entity_check() is False:
            raise ValueError("Invalid DTO object for update.")

        with DBSession() as session:
            # 更新数据库中的表情包
            statement = select(Emoji).where(Emoji.img_hash == dto.img_hash)
            emoji = session.exec(statement).first()

            if emoji is None:
                raise ValueError(f"Emoji '{dto.img_hash}' does not exist.")

            # 更新表情包信息
            emoji.file_name = dto.file_name or emoji.file_name
            emoji.is_banned = dto.is_banned or emoji.is_banned
            emoji.is_registered = dto.is_registered or emoji.is_registered
            emoji.last_try_register_at = dto.last_try_register_at or emoji.last_try_register_at
            emoji.usage_count = dto.usage_count or emoji.usage_count
            emoji.last_used_at = dto.last_used_at or emoji.last_used_at

            session.commit()
            session.refresh(emoji)

            dto = EmojiDTO.from_orm(emoji)

        # 刷新缓存
        global_cache[_pk(dto.img_hash)] = dto

        return dto

    @classmethod
    def delete_emoji(cls, dto: EmojiDTO) -> None:
        """删除表情包

        :param dto: 表情包DTO
        """
        if dto.delete_entity_check() is False:
            raise ValueError("Invalid DTO object for delete.")

        with DBSession() as session:
            statement = select(Emoji).where(Emoji.img_hash == dto.img_hash)
            emoji = session.exec(statement).first()

            if emoji is None:
                raise ValueError(f"Emoji '{dto.img_hash}' does not exist.")

            session.delete(emoji)
            session.commit()

        # 删除缓存
        global_cache.pop(_pk(dto.img_hash), None)
