from src.common.server import global_server
import os
import importlib.metadata
from maim_message import MessageServer
from src.common.logger_manager import get_logger


# 检查maim_message版本
try:
    maim_message_version = importlib.metadata.version("maim_message")
    version_compatible = [int(x) for x in maim_message_version.split(".")] >= [0, 3, 0]
except (importlib.metadata.PackageNotFoundError, ValueError):
    version_compatible = False

# 根据版本决定是否使用自定义logger
kwargs = {
    "host": os.environ["HOST"],
    "port": int(os.environ["PORT"]),
    "app": global_server.get_app(),
}

# 只有在版本 >= 0.3.0 时才使用自定义logger
if version_compatible:
    maim_message_logger = get_logger("maim_message")
    kwargs["custom_logger"] = maim_message_logger

global_api = MessageServer(**kwargs)
