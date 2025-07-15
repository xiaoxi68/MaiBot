import json

from dataclasses import dataclass
from typing import Dict, List, Optional
from pathlib import Path


@dataclass
class Personality:
    """人格特质类"""

    bot_nickname: str  # 机器人昵称
    personality_core: str  # 人格核心特点
    personality_side: str  # 人格侧面描述
    identity: List[str]  # 身份细节描述
    compress_personality: bool  # 是否压缩人格
    compress_identity: bool  # 是否压缩身份

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, personality_core: str = "", personality_side: str = "", identity: List[str] = None):
        self.personality_core = personality_core
        self.personality_side = personality_side
        self.identity = identity
        self.compress_personality = True
        self.compress_identity = True

    @classmethod
    def get_instance(cls) -> "Personality":
        """获取Personality单例实例

        Returns:
            Personality: 单例实例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def initialize(cls, bot_nickname: str, personality_core: str, personality_side: str, identity: List[str] = None, compress_personality: bool = True, compress_identity: bool = True) -> "Personality":
        """初始化人格特质

        Args:
            bot_nickname: 机器人昵称
            personality_core: 人格核心特点
            personality_side: 人格侧面描述
            identity: 身份细节描述
            compress_personality: 是否压缩人格
            compress_identity: 是否压缩身份

        Returns:
            Personality: 初始化后的人格特质实例
        """
        instance = cls.get_instance()
        instance.bot_nickname = bot_nickname
        instance.personality_core = personality_core
        instance.personality_side = personality_side
        instance.identity = identity
        instance.compress_personality = compress_personality
        instance.compress_identity = compress_identity
        return instance

    def to_dict(self) -> Dict:
        """将人格特质转换为字典格式"""
        return {
            "bot_nickname": self.bot_nickname,
            "personality_core": self.personality_core,
            "personality_side": self.personality_side,
            "identity": self.identity,
            "compress_personality": self.compress_personality,
            "compress_identity": self.compress_identity,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Personality":
        """从字典创建人格特质实例"""
        instance = cls.get_instance()
        for key, value in data.items():
            setattr(instance, key, value)
        return instance
