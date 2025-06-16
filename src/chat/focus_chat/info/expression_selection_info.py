from dataclasses import dataclass
from typing import List, Dict, Any
from .info_base import InfoBase


@dataclass
class ExpressionSelectionInfo(InfoBase):
    """表达选择信息类

    用于存储和管理选中的表达方式信息。

    Attributes:
        type (str): 信息类型标识符，默认为 "expression_selection"
        data (Dict[str, Any]): 包含选中表达方式的数据字典
    """

    type: str = "expression_selection"

    def get_selected_expressions(self) -> List[Dict[str, str]]:
        """获取选中的表达方式列表

        Returns:
            List[Dict[str, str]]: 选中的表达方式列表
        """
        return self.get_info("selected_expressions") or []

    def set_selected_expressions(self, expressions: List[Dict[str, str]]) -> None:
        """设置选中的表达方式列表

        Args:
            expressions: 选中的表达方式列表
        """
        self.data["selected_expressions"] = expressions

    def get_expressions_count(self) -> int:
        """获取选中表达方式的数量

        Returns:
            int: 表达方式数量
        """
        return len(self.get_selected_expressions())

    def get_processed_info(self) -> str:
        """获取处理后的信息

        Returns:
            str: 处理后的信息字符串
        """
        expressions = self.get_selected_expressions()
        if not expressions:
            return ""
        
        # 格式化表达方式为可读文本
        formatted_expressions = []
        for expr in expressions:
            situation = expr.get("situation", "")
            style = expr.get("style", "")
            expr_type = expr.get("type", "")
            
            if situation and style:
                formatted_expressions.append(f"当{situation}时，使用 {style}")
        
        return "\n".join(formatted_expressions)

    def get_expressions_for_action_data(self) -> List[Dict[str, str]]:
        """获取用于action_data的表达方式数据

        Returns:
            List[Dict[str, str]]: 格式化后的表达方式数据
        """
        return self.get_selected_expressions() 