"""
MaiBot模块系统
包含聊天、情绪、记忆、日程等功能模块
"""

from src.chat.normal_chat.willing.willing_manager import willing_manager

# 导出主要组件供外部使用
__all__ = [
    "willing_manager",
]
