from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Relationship
from sqlmodel import SQLModel, Field, UniqueConstraint

"""
此文件中定义了数据库模型，使用 SQLModel 进行 ORM 映射。
"""


class PersonInfo(SQLModel, table=True):
    """
    用于存储人际关系数据的模型。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    """主键（由数据库创建，自动递增）"""

    created_at: datetime
    """创建时间戳"""

    real_name: Optional[str] = Field(default=None)
    """真实姓名（可能为空）"""

    nickname: Optional[str] = Field(default=None, unique=True, index=True)
    """昵称（方便称呼的昵称，可能为空）"""

    nickname_reason: Optional[str] = Field(default=None)
    """昵称设定的原因（可能为空）"""

    relationship_value: float = Field(default=0.0)
    """关系值"""

    # -- 以下为ORM关系 --

    chat_users: list["ChatUser"] = Relationship(back_populates="person_id")
    """聊天用户对象（与 ChatUser 关联）"""


class ChatUser(SQLModel, table=True):
    """
    聊天用户
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    """主键（由数据库创建，自动递增）"""

    created_at: datetime
    """创建时间戳"""

    platform: str
    """平台名称"""

    platform_user_id: str
    """平台用户 ID（如 QQ 号）"""

    user_name: Optional[str] = Field(default=None)
    """用户名称 (可能为空)"""

    platform_spec_info: Optional[str] = Field(default=None)
    """平台特定的信息 (可能为空)"""

    msg_interval: Optional[float] = Field(default=None)
    """消息间隔（秒）"""

    person_id: int = Field(foreign_key="person_info.id")
    """个体ID
    （外键，指向 PersonInfo 表）
    当一个新ChatUser对象被创建时，要么同样的创建一个新的PersonInfo对象，要么将其与一个已经存在的PersonInfo对象关联
    """

    # -- 以下为ORM关系 --

    group_links: list["ChatGroupUser"] = Relationship(back_populates="user")
    """参与的群组（与 ChatGroupUser 关联）"""

    messages: list["Message"] = Relationship(back_populates="sender")
    """消息列表（与 Messages 关联）"""

    person_info: "PersonInfo" = Relationship(back_populates="chat_users")
    """个体信息对象（与 PersonInfo 关联）"""

    chat_stream: Optional["ChatStream"] = Relationship(back_populates="user")
    """聊天流对象（与 ChatStream 关联）"""

    # -- 以下为SQLAlchemy配置 --

    __table_args__ = (
        UniqueConstraint(
            "platform",
            "platform_user_id",
            name="uq_platform_user_id",
        ),
        # 联合唯一约束 - 确保同一平台的用户 ID 唯一
    )


class ChatGroup(SQLModel, table=True):
    """
    聊天组
    """

    id: Optional[int] = Field(
        default=None,
        primary_key=True,
    )
    """主键（由数据库创建，自动递增）"""

    created_at: datetime
    """创建时间戳"""

    platform: str
    """平台名称"""

    platform_group_id: str
    """平台群组 ID （如 QQ 群号）"""

    group_name: Optional[str] = Field(default=None)
    """群组名称（可能为空）"""

    platform_spec_info: Optional[str] = Field(default=None)
    """平台特定的信息（可能为空）"""

    # -- 以下为ORM关系 --

    member_links: list["ChatGroupUser"] = Relationship(back_populates="group")
    """群组成员（与 ChatGroupUser 关联）"""

    chat_stream: Optional["ChatStream"] = Relationship(back_populates="group")
    """聊天流对象（与 ChatStream 关联）"""

    # -- 以下为SQLAlchemy配置 --

    __table_args__ = (
        UniqueConstraint(
            "platform",
            "platform_group_id",
            name="uq_platform_group_id",
        ),
        # 联合唯一约束 - 确保同一平台的群组 ID 唯一
    )


class ChatGroupUser(SQLModel, table=True):
    """
    聊天组用户（用于关联用户和群组）
    """

    group_id: int = Field(default=None, foreign_key="chat_group.id", primary_key=True)
    """群组 ID （联合主键）"""

    user_id: int = Field(default=None, foreign_key="chat_user.id", primary_key=True)
    """用户 ID （联合主键）"""

    created_at: datetime
    """创建时间戳"""

    platform: str
    """平台名称"""

    user_group_name: str
    """用户在群组中的名称（可能为空）"""

    platform_spec_info: str | None = Field(default=None)
    """平台特定的信息 (可能为空)"""

    # -- 以下为ORM关系 --

    group: "ChatGroup" = Relationship(back_populates="member_links")
    """群组对象（与 ChatGroup 关联）"""

    user: "ChatUser" = Relationship(back_populates="group_links")
    """用户对象（与 ChatUser 关联）"""


class ChatStream(SQLModel, table=True, table_name="chat_streams"):
    """
    聊天流
    """

    id: Optional[int] = Field(
        default=None,
        primary_key=True,
    )
    """主键（由数据库创建，自动递增）"""

    created_at: datetime
    """创建时间戳"""

    group_id: Optional[int] = Field(
        default=None,
        foreign_key="chat_group.id",
        unique=True,
        index=True,
    )
    """群组 ID
    （外键，指向 ChatGroup 表）
    """

    user_id: Optional[int] = Field(
        default=None,
        foreign_key="chat_user.id",
        unique=True,
        index=True,
    )
    """用户 ID
    （外键，指向 ChatUser 表）
    """

    last_active_at: datetime
    """最后一次活跃的时间戳
    
    （是否有效存疑，理论上可通过数据库查询语句优化掉）
    """

    # -- 以下为ORM关系 --

    messages: list["Message"] = Relationship(back_populates="chat_stream")
    """消息列表（与 Messages 关联）"""

    group: Optional["ChatGroup"] = Relationship(back_populates="chat_stream")
    """群组对象（与 ChatGroup 关联）"""

    user: Optional["ChatUser"] = Relationship(back_populates="chat_stream")
    """用户对象（与 ChatUser 关联）"""

    # -- 以下为SQLAlchemy配置 --

    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "user_id",
            name="uq_group_user_stream",
        ),
    )


class Message(SQLModel, table=True):
    """
    用于存储消息数据的模型。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    """主键（由数据库创建，自动递增）"""

    created_at: datetime
    """创建时间戳"""

    message_time: datetime = Field(index=True)
    """消息时间戳"""

    platform_message_id: str
    """平台消息 ID（如 QQ 消息 ID）"""

    chat_stream_id: int = Field(foreign_key="chat_streams.id", index=True)
    """聊天流 ID"""

    sender_id: int = Field(foreign_key="chat_user.id", index=True)
    """发送者 ID"""

    processed_plain_text: Optional[str] = Field(default=None)
    """处理后的纯文本消息内容"""

    memorized_times: int = Field(default=0)
    """记忆次数（用于统计消息被用于构建记忆的次数）"""

    # -- 以下为ORM关系 --

    chat_stream: "ChatStream" = Relationship(back_populates="messages")
    """聊天流对象（与 ChatStream 关联）"""

    sender: "ChatUser" = Relationship(back_populates="messages")
    """发送者对象（与 ChatUser 关联）"""


class Image(SQLModel, table=True):
    """
    图像信息
    """

    created_at: datetime
    """创建时间戳"""

    img_hash: str = Field(unique=True, primary_key=True)
    """图像的哈希值（主键）"""

    description: Optional[str] = Field(default=None)
    """图像的描述（可能为空，表示尚未获取到描述）"""

    query_count: int = Field(default=0)
    """查询次数（用于统计图像被查询描述的次数）"""

    last_queried_at: datetime = Field(index=True)
    """最后一次查询的时间戳"""

    # -- 以下为ORM关系 --

    emoji: Optional["Emoji"] = Relationship(back_populates="image")
    """表情包对象（与 Emoji 关联）"""


class Emoji(SQLModel, table=True):
    """表情包"""

    created_at: datetime
    """创建时间戳"""

    img_hash: str = Field(unique=True, primary_key=True, foreign_key="image.img_hash")
    """图像的哈希值（主键）
    （外键，指向 Images 表）
    """

    file_name: Optional[str] = Field(default=None)
    """图像文件的文件名"""

    is_banned: bool = Field(default=False)
    """是否被禁止使用/注册（默认为 False）"""

    is_registered: bool = Field(default=False)
    """是否已注册（默认为 False）"""

    last_try_register_at: Optional[datetime] = Field(default=None, index=True)
    """最后一次尝试注册的时间戳"""

    emotions: str
    """表情包的情感描述（列表序列化为 JSON 字符串）"""

    usage_count: int = Field(default=0)
    """使用次数（用于统计表情包被使用的次数）"""

    last_used_at: Optional[datetime] = Field(default=None, index=True)
    """最后一次使用的时间戳（如果未使用，则为 None）"""

    # -- 以下为ORM关系 --

    image: "Image" = Relationship(back_populates="emoji")
    """图像对象（与 Images 关联）"""


class OnlineTimeRecord(SQLModel, table=True):
    """
    在线时长记录
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    """主键（由数据库创建，自动递增）"""

    start_timestamp: datetime = Field(unique=True, index=True)
    """开始时间戳"""

    end_timestamp: datetime = Field(unique=True, index=True)
    """结束时间戳"""


class Knowledge(SQLModel, table=True):
    """
    知识库条目
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    """主键（由数据库创建，自动递增）"""

    content: str
    """知识内容的文本"""

    embedding: str
    """知识内容的嵌入向量，存储为 JSON 字符串的浮点数列表"""


def create_database(db_engine):
    """
    创建数据库
    """
    SQLModel.metadata.create_all(
        bind=db_engine,
    )


__all__ = [
    "ChatStream",
    "ChatGroup",
    "ChatUser",
    "ChatGroupUser",
    "Message",
    "PersonInfo",
    "Image",
    "Emoji",
    "OnlineTimeRecord",
    "Knowledge",
    "create_database",
]
