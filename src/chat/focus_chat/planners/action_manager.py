from typing import List, Optional, Dict

# 默认动作定义
DEFAULT_ACTIONS = {"no_reply": "不操作，继续浏览", "reply": "表达想法，可以只包含文本、表情或两者都有"}


class ActionManager:
    """动作管理器：控制每次决策可以使用的动作"""

    def __init__(self):
        # 初始化为新的默认动作集
        self._available_actions: Dict[str, str] = DEFAULT_ACTIONS.copy()
        self._original_actions_backup: Optional[Dict[str, str]] = None

    def get_available_actions(self) -> Dict[str, str]:
        """获取当前可用的动作集"""
        return self._available_actions.copy()  # 返回副本以防外部修改

    def add_action(self, action_name: str, description: str) -> bool:
        """
        添加新的动作

        参数:
            action_name: 动作名称
            description: 动作描述

        返回:
            bool: 是否添加成功
        """
        if action_name in self._available_actions:
            return False
        self._available_actions[action_name] = description
        return True

    def remove_action(self, action_name: str) -> bool:
        """
        移除指定动作

        参数:
            action_name: 动作名称

        返回:
            bool: 是否移除成功
        """
        if action_name not in self._available_actions:
            return False
        del self._available_actions[action_name]
        return True

    def temporarily_remove_actions(self, actions_to_remove: List[str]):
        """
        临时移除指定的动作，备份原始动作集。
        如果已经有备份，则不重复备份。
        """
        if self._original_actions_backup is None:
            self._original_actions_backup = self._available_actions.copy()

        actions_actually_removed = []
        for action_name in actions_to_remove:
            if action_name in self._available_actions:
                del self._available_actions[action_name]
                actions_actually_removed.append(action_name)
        # logger.debug(f"临时移除了动作: {actions_actually_removed}") # 可选日志

    def restore_actions(self):
        """
        恢复之前备份的原始动作集。
        """
        if self._original_actions_backup is not None:
            self._available_actions = self._original_actions_backup.copy()
            self._original_actions_backup = None
            # logger.debug("恢复了原始动作集") # 可选日志
