"""
插件系统API模块

提供了插件开发所需的各种API
"""

# 导入所有API模块
from src.plugin_system.apis import (
    chat_api,
    config_api,
    database_api,
    emoji_api,
    generator_api,
    llm_api,
    message_api,
    person_api,
    send_api,
    utils_api,
)

# 导出所有API模块，使它们可以通过 apis.xxx 方式访问
__all__ = [
    "chat_api",
    "config_api",
    "database_api",
    "emoji_api",
    "generator_api",
    "llm_api",
    "message_api",
    "person_api",
    "send_api",
    "utils_api",
]
