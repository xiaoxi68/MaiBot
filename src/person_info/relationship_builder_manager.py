from typing import Dict

from src.common.logger import get_logger
from .relationship_builder import RelationshipBuilder

logger = get_logger("relationship_builder_manager")


class RelationshipBuilderManager:
    """关系构建器管理器

    简单的关系构建器存储和获取管理
    """

    def __init__(self):
        self.builders: Dict[str, RelationshipBuilder] = {}

    def get_or_create_builder(self, chat_id: str) -> RelationshipBuilder:
        """获取或创建关系构建器

        Args:
            chat_id: 聊天ID

        Returns:
            RelationshipBuilder: 关系构建器实例
        """
        if chat_id not in self.builders:
            self.builders[chat_id] = RelationshipBuilder(chat_id)
            logger.debug(f"创建聊天 {chat_id} 的关系构建器")

        return self.builders[chat_id]


# 全局管理器实例
relationship_builder_manager = RelationshipBuilderManager()
