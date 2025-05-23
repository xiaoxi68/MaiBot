from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from .info_base import InfoBase


@dataclass
class ActionInfo(InfoBase):
    """动作信息类

    用于管理和记录动作的变更信息，包括需要添加或移除的动作。
    继承自 InfoBase 类，使用字典存储具体数据。

    Attributes:
        type (str): 信息类型标识符，固定为 "action"

    Data Fields:
        add_actions (List[str]): 需要添加的动作列表
        remove_actions (List[str]): 需要移除的动作列表
        reason (str): 变更原因说明
    """

    type: str = "action"

    def get_type(self) -> str:
        """获取信息类型"""
        return self.type

    def get_data(self) -> Dict[str, Any]:
        """获取信息数据"""
        return self.data

    def set_action_changes(self, action_changes: Dict[str, List[str]]) -> None:
        """设置动作变更信息

        Args:
            action_changes (Dict[str, List[str]]): 包含要增加和删除的动作列表
                {
                    "add": ["action1", "action2"],
                    "remove": ["action3"]
                }
        """
        self.data["add_actions"] = action_changes.get("add", [])
        self.data["remove_actions"] = action_changes.get("remove", [])

    def set_reason(self, reason: str) -> None:
        """设置变更原因

        Args:
            reason (str): 动作变更的原因说明
        """
        self.data["reason"] = reason

    def get_add_actions(self) -> List[str]:
        """获取需要添加的动作列表

        Returns:
            List[str]: 需要添加的动作列表
        """
        return self.data.get("add_actions", [])

    def get_remove_actions(self) -> List[str]:
        """获取需要移除的动作列表

        Returns:
            List[str]: 需要移除的动作列表
        """
        return self.data.get("remove_actions", [])

    def get_reason(self) -> Optional[str]:
        """获取变更原因

        Returns:
            Optional[str]: 动作变更的原因说明，如果未设置则返回 None
        """
        return self.data.get("reason")

    def has_changes(self) -> bool:
        """检查是否有动作变更

        Returns:
            bool: 如果有任何动作需要添加或移除则返回True
        """
        return bool(self.get_add_actions() or self.get_remove_actions())
