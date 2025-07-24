"""配置API模块

提供了配置读取和用户信息获取等功能
使用方式：
    from src.plugin_system.apis import config_api
    value = config_api.get_global_config("section.key")
    platform, user_id = await config_api.get_user_id_by_person_name("用户名")
"""

from typing import Any
from src.common.logger import get_logger
from src.config.config import global_config
from src.person_info.person_info import get_person_info_manager

logger = get_logger("config_api")


# =============================================================================
# 配置访问API函数
# =============================================================================


def get_global_config(key: str, default: Any = None) -> Any:
    """
    安全地从全局配置中获取一个值。
    插件应使用此方法读取全局配置，以保证只读和隔离性。

    Args:
        key: 命名空间式配置键名，支持嵌套访问，如 "section.subsection.key"，大小写敏感
        default: 如果配置不存在时返回的默认值

    Returns:
        Any: 配置值或默认值
    """
    # 支持嵌套键访问
    keys = key.split(".")
    current = global_config

    try:
        for k in keys:
            if hasattr(current, k):
                current = getattr(current, k)
            else:
                raise KeyError(f"配置中不存在子空间或键 '{k}'")
        return current
    except Exception as e:
        logger.warning(f"[ConfigAPI] 获取全局配置 {key} 失败: {e}")
        return default


def get_plugin_config(plugin_config: dict, key: str, default: Any = None) -> Any:
    """
    从插件配置中获取值，支持嵌套键访问

    Args:
        plugin_config: 插件配置字典
        key: 配置键名，支持嵌套访问如 "section.subsection.key"，大小写敏感
        default: 如果配置不存在时返回的默认值

    Returns:
        Any: 配置值或默认值
    """
    # 支持嵌套键访问
    keys = key.split(".")
    current = plugin_config

    try:
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            elif hasattr(current, k):
                current = getattr(current, k)
            else:
                raise KeyError(f"配置中不存在子空间或键 '{k}'")
        return current
    except Exception as e:
        logger.warning(f"[ConfigAPI] 获取插件配置 {key} 失败: {e}")
        return default


# =============================================================================
# 用户信息API函数
# =============================================================================


async def get_user_id_by_person_name(person_name: str) -> tuple[str, str]:
    """根据内部用户名获取用户ID

    Args:
        person_name: 用户名

    Returns:
        tuple[str, str]: (平台, 用户ID)
    """
    try:
        person_info_manager = get_person_info_manager()
        person_id = person_info_manager.get_person_id_by_person_name(person_name)
        user_id: str = await person_info_manager.get_value(person_id, "user_id")  # type: ignore
        platform: str = await person_info_manager.get_value(person_id, "platform")  # type: ignore
        return platform, user_id
    except Exception as e:
        logger.error(f"[ConfigAPI] 根据用户名获取用户ID失败: {e}")
        return "", ""


async def get_person_info(person_id: str, key: str, default: Any = None) -> Any:
    """获取用户信息

    Args:
        person_id: 用户ID
        key: 信息键名
        default: 默认值

    Returns:
        Any: 用户信息值或默认值
    """
    try:
        person_info_manager = get_person_info_manager()
        response = await person_info_manager.get_value(person_id, key)
        if not response:
            raise ValueError(f"[ConfigAPI] 获取用户 {person_id} 的信息 '{key}' 失败，返回默认值")
        return response
    except Exception as e:
        logger.error(f"[ConfigAPI] 获取用户信息失败: {e}")
        return default
