"""
MaiBot 插件系统

提供统一的插件开发和管理框架
"""

# 导出主要的公共接口
from src.plugin_system.base.base_plugin import BasePlugin, register_plugin
from src.plugin_system.base.base_action import BaseAction
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.base.component_types import (
    ComponentType, ActionActivationType, ChatMode,
    ComponentInfo, ActionInfo, CommandInfo, PluginInfo
)
from src.plugin_system.apis.plugin_api import PluginAPI, create_plugin_api, create_command_api
from src.plugin_system.core.plugin_manager import plugin_manager
from src.plugin_system.core.component_registry import component_registry

__version__ = "1.0.0"

__all__ = [
    # 基础类
    'BasePlugin',
    'BaseAction', 
    'BaseCommand',
    
    # 类型定义
    'ComponentType',
    'ActionActivationType',
    'ChatMode',
    'ComponentInfo',
    'ActionInfo',
    'CommandInfo',
    'PluginInfo',
    
    # API接口
    'PluginAPI',
    'create_plugin_api',
    'create_command_api',
    
    # 管理器
    'plugin_manager',
    'component_registry',
    
    # 装饰器
    'register_plugin',
] 