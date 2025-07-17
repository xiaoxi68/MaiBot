"""工具类API模块

提供了各种辅助功能
使用方式：
    from src.plugin_system.apis import utils_api
    plugin_path = utils_api.get_plugin_path()
    data = utils_api.read_json_file("data.json")
    timestamp = utils_api.get_timestamp()
"""

import os
import json
import time
import inspect
import datetime
import uuid
from typing import Any, Optional
from src.common.logger import get_logger

logger = get_logger("utils_api")


# =============================================================================
# 文件操作API函数
# =============================================================================


def get_plugin_path(caller_frame=None) -> str:
    """获取调用者插件的路径

    Args:
        caller_frame: 调用者的栈帧，默认为None（自动获取）

    Returns:
        str: 插件目录的绝对路径
    """
    try:
        if caller_frame is None:
            caller_frame = inspect.currentframe().f_back  # type: ignore

        plugin_module_path = inspect.getfile(caller_frame)  # type: ignore
        plugin_dir = os.path.dirname(plugin_module_path)
        return plugin_dir
    except Exception as e:
        logger.error(f"[UtilsAPI] 获取插件路径失败: {e}")
        return ""


def read_json_file(file_path: str, default: Any = None) -> Any:
    """读取JSON文件

    Args:
        file_path: 文件路径，可以是相对于插件目录的路径
        default: 如果文件不存在或读取失败时返回的默认值

    Returns:
        Any: JSON数据或默认值
    """
    try:
        # 如果是相对路径，则相对于调用者的插件目录
        if not os.path.isabs(file_path):
            caller_frame = inspect.currentframe().f_back  # type: ignore
            plugin_dir = get_plugin_path(caller_frame)
            file_path = os.path.join(plugin_dir, file_path)

        if not os.path.exists(file_path):
            logger.warning(f"[UtilsAPI] 文件不存在: {file_path}")
            return default

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[UtilsAPI] 读取JSON文件出错: {e}")
        return default


def write_json_file(file_path: str, data: Any, indent: int = 2) -> bool:
    """写入JSON文件

    Args:
        file_path: 文件路径，可以是相对于插件目录的路径
        data: 要写入的数据
        indent: JSON缩进

    Returns:
        bool: 是否写入成功
    """
    try:
        # 如果是相对路径，则相对于调用者的插件目录
        if not os.path.isabs(file_path):
            caller_frame = inspect.currentframe().f_back  # type: ignore
            plugin_dir = get_plugin_path(caller_frame)
            file_path = os.path.join(plugin_dir, file_path)

        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        return True
    except Exception as e:
        logger.error(f"[UtilsAPI] 写入JSON文件出错: {e}")
        return False


# =============================================================================
# 时间相关API函数
# =============================================================================


def get_timestamp() -> int:
    """获取当前时间戳

    Returns:
        int: 当前时间戳（秒）
    """
    return int(time.time())


def format_time(timestamp: Optional[int | float] = None, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化时间

    Args:
        timestamp: 时间戳，如果为None则使用当前时间
        format_str: 时间格式字符串

    Returns:
        str: 格式化后的时间字符串
    """
    try:
        if timestamp is None:
            timestamp = time.time()
        return datetime.datetime.fromtimestamp(timestamp).strftime(format_str)
    except Exception as e:
        logger.error(f"[UtilsAPI] 格式化时间失败: {e}")
        return ""


def parse_time(time_str: str, format_str: str = "%Y-%m-%d %H:%M:%S") -> int:
    """解析时间字符串为时间戳

    Args:
        time_str: 时间字符串
        format_str: 时间格式字符串

    Returns:
        int: 时间戳（秒）
    """
    try:
        dt = datetime.datetime.strptime(time_str, format_str)
        return int(dt.timestamp())
    except Exception as e:
        logger.error(f"[UtilsAPI] 解析时间失败: {e}")
        return 0


# =============================================================================
# 其他工具函数
# =============================================================================


def generate_unique_id() -> str:
    """生成唯一ID

    Returns:
        str: 唯一ID
    """
    return str(uuid.uuid4())
