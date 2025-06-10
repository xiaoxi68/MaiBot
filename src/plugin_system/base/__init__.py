"""
插件基础类模块

提供插件开发的基础类和类型定义
"""

from src.plugin_system.base.base_plugin import BasePlugin, register_plugin
from src.plugin_system.base.base_action import BaseAction
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.base.component_types import (
    ComponentType, ActionActivationType, ChatMode,
    ComponentInfo, ActionInfo, CommandInfo, PluginInfo
)

__all__ = [
    'BasePlugin',
    'BaseAction',
    'BaseCommand',
    'register_plugin',
    'ComponentType',
    'ActionActivationType', 
    'ChatMode',
    'ComponentInfo',
    'ActionInfo',
    'CommandInfo',
    'PluginInfo',
] 