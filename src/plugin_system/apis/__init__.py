"""
插件API模块

提供插件可以使用的各种API接口
"""

from src.plugin_system.apis.plugin_api import PluginAPI, create_plugin_api, create_command_api
from src.plugin_system.apis.message_api import MessageAPI
from src.plugin_system.apis.llm_api import LLMAPI
from src.plugin_system.apis.database_api import DatabaseAPI
from src.plugin_system.apis.config_api import ConfigAPI
from src.plugin_system.apis.utils_api import UtilsAPI
from src.plugin_system.apis.stream_api import StreamAPI
from src.plugin_system.apis.hearflow_api import HearflowAPI

# 新增：分类的API聚合
from src.plugin_system.apis.action_apis import ActionAPI
from src.plugin_system.apis.independent_apis import IndependentAPI, StaticAPI

__all__ = [
    # 原有统一API
    "PluginAPI",
    "create_plugin_api",
    "create_command_api",
    # 原有单独API
    "MessageAPI",
    "LLMAPI",
    "DatabaseAPI",
    "ConfigAPI",
    "UtilsAPI",
    "StreamAPI",
    "HearflowAPI",
    # 新增分类API
    "ActionAPI",  # 需要Action依赖的API
    "IndependentAPI",  # 独立API
    "StaticAPI",  # 静态API
]
