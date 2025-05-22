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

    file_path: Optional[str] = None
    """图像文件的路径"""

    is_banned: Optional[bool] = None
    """是否被禁止使用/注册（默认为 False）"""

    registered_at: Optional[datetime] = None
    """注册时间戳（如果未注册，则为 None）"""

    emotions: Optional[str] = None
    """表情包的情感描述（列表序列化为 JSON 字符串）"""

    usage_count: Optional[int] = None
    """使用次数（用于统计表情包被使用的次数）"""

    last_used_at: Optional[datetime] = None
    """最后一次使用的时间戳（如果未使用，则为 None）"""

    __orm_create_rule__ = "img_hash | file_path"

    __orm_select_rule__ = "img_hash | file_path"

    __orm_update_rule__ = "file_path | is_banned | registered_at | emotions | usage_count | last_used_at"

    @classmethod
    def from_orm(cls, emoji: Emoji) -> "EmojiDTO":
        """从ORM对象创建DTO对象。"""
        return cls(
            created_at=emoji.created_at,
            img_hash=emoji.img_hash,
            file_path=emoji.file_path,
            is_banned=emoji.is_banned,
            registered_at=emoji.registered_at,
            emotions=emoji.emotions,
            usage_count=emoji.usage_count,
            last_used_at=emoji.last_used_at,
        )


def _pk(img_hash: str):
    """构造缓存主键"""
    return f"emoji:pk:{img_hash}"


def _file_path_key(file_path: str):
    """构造缓存文件路径键"""
    return f"emoji:file_path:{file_path}"


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
            emoji = Emoji(
                created_at=datetime.now(),
                img_hash=dto.img_hash,
                file_path=dto.file_path,
                is_banned=dto.is_banned,
                registered_at=dto.registered_at,
                emotions=dto.emotions,
                usage_count=dto.usage_count,
                last_used_at=dto.last_used_at,
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

        def _get_by_pk(hash: str):
            """通过主键获取表情包"""
            if emoji := global_cache.get(_pk(hash)):
                return emoji
            else:
                return cls._get_emoji_by_hash(hash)

        if dto.img_hash:
            _get_by_pk(dto.img_hash)
        elif dto.file_path:
            # 通过文件路径获取表情包
            if hash := global_cache.get(_file_path_key(dto.file_path)):
                return _get_by_pk(hash)
            else:
                cls._get_emoji_by_file_path(dto.file_path)

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
    def _get_emoji_by_file_path(cls, file_path: str) -> Optional[EmojiDTO]:
        """数据库操作：通过文件路径获取表情包信息"""
        with DBSession() as session:
            statement = select(Emoji).where(Emoji.file_path == file_path)

            if emoji := session.exec(statement).first():
                dto = EmojiDTO.from_orm(emoji)
            else:
                return None

        # 缓存结果
        global_cache[_pk(dto.img_hash)] = dto
        global_cache[_file_path_key(file_path)] = dto.img_hash

        return dto

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
            emoji.file_path = dto.file_path or emoji.file_path
            emoji.is_banned = dto.is_banned or emoji.is_banned
            emoji.registered_at = dto.registered_at or emoji.registered_at
            emoji.emotions = dto.emotions or emoji.emotions
            emoji.usage_count = dto.usage_count or emoji.usage_count
            emoji.last_used_at = dto.last_used_at or emoji.last_used_at

            session.commit()
            session.refresh(emoji)

            dto = EmojiDTO.from_orm(emoji)

        # 刷新缓存
        global_cache[_pk(dto.img_hash)] = dto

        return dto
