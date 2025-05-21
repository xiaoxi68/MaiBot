from dataclasses import dataclass
from typing import Optional

from sqlmodel import select

from common.database.database import DBSession
from common.database.database_model import Knowledge
from model_manager.dto_base import DTOBase


@dataclass
class KnowledgeDTO(DTOBase):
    """知识DTO"""

    id: Optional[int] = None
    """主键（由数据库创建，自动递增）"""

    content: Optional[str] = None
    """知识内容的文本"""

    embedding: Optional[str] = None
    """知识内容的嵌入向量，存储为 JSON 字符串的浮点数列表"""

    __orm_create_rule__ = "content & embedding"
    __orm_select_rule__ = "id"


class KnowledgeManager:
    @classmethod
    def create_knowledge(cls, dto: KnowledgeDTO) -> KnowledgeDTO:
        """创建知识条目

        :param dto: 知识DTO
        :return: 创建的知识DTO
        """
        if dto.create_entity_check() is False:
            raise ValueError("Invalid DTO object for create.")

    @classmethod
    def get_all_knowledge(cls) -> list[KnowledgeDTO]:
        """获取所有知识条目"""

        with DBSession() as session:
            knowledge_list = session.exec(select(Knowledge)).all()
            return [KnowledgeDTO.from_orm(knowledge) for knowledge in knowledge_list]

    @classmethod
    def delete_knowledge(cls, dto: KnowledgeDTO) -> None:
        """删除知识条目

        :param dto: 知识DTO
        """
        if dto.delete_entity_check() is False:
            raise ValueError("Invalid DTO object for delete.")

        with DBSession() as session:
            if not (knowledge := session.exec(select(Knowledge).where(Knowledge.id == dto.id)).first()):
                raise ValueError(f"Knowledge '{dto.id}' does not exist.")
            session.delete(knowledge)
            session.commit()
