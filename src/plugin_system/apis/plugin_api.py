# -*- coding: utf-8 -*-
"""
统一的插件API聚合模块

提供所有插件API功能的统一访问入口
"""

from src.common.logger_manager import get_logger

# 导入所有API模块
from src.plugin_system.apis.message_api import MessageAPI
from src.plugin_system.apis.llm_api import LLMAPI
from src.plugin_system.apis.database_api import DatabaseAPI
from src.plugin_system.apis.config_api import ConfigAPI
from src.plugin_system.apis.utils_api import UtilsAPI
from src.plugin_system.apis.stream_api import StreamAPI
from src.plugin_system.apis.hearflow_api import HearflowAPI

logger = get_logger("plugin_api")


class PluginAPI(MessageAPI, LLMAPI, DatabaseAPI, ConfigAPI, UtilsAPI, StreamAPI, HearflowAPI):
    """
    插件API聚合类

    集成了所有可供插件使用的API功能，提供统一的访问接口。
    插件组件可以直接使用此API实例来访问各种功能。

    特性：
    - 聚合所有API模块的功能
    - 支持依赖注入和配置
    - 提供统一的错误处理和日志记录
    """

    def __init__(
        self, chat_stream=None, expressor=None, replyer=None, observations=None, log_prefix: str = "[PluginAPI]"
    ):
        """
        初始化插件API

        Args:
            chat_stream: 聊天流对象
            expressor: 表达器对象
            replyer: 回复器对象
            observations: 观察列表
            log_prefix: 日志前缀
        """
        # 存储依赖对象
        self._services = {
            "chat_stream": chat_stream,
            "expressor": expressor,
            "replyer": replyer,
            "observations": observations or [],
        }

        self.log_prefix = log_prefix

        # 存储action上下文信息
        self._action_context = {}

        # 调用所有父类的初始化
        super().__init__()

        logger.debug(f"{self.log_prefix} PluginAPI 初始化完成")

    def set_chat_stream(self, chat_stream):
        """设置聊天流对象"""
        self._services["chat_stream"] = chat_stream
        logger.debug(f"{self.log_prefix} 设置聊天流: {getattr(chat_stream, 'stream_id', 'Unknown')}")

    def set_expressor(self, expressor):
        """设置表达器对象"""
        self._services["expressor"] = expressor
        logger.debug(f"{self.log_prefix} 设置表达器")

    def set_replyer(self, replyer):
        """设置回复器对象"""
        self._services["replyer"] = replyer
        logger.debug(f"{self.log_prefix} 设置回复器")

    def set_observations(self, observations):
        """设置观察列表"""
        self._services["observations"] = observations or []
        logger.debug(f"{self.log_prefix} 设置观察列表，数量: {len(observations or [])}")

    def get_service(self, service_name: str):
        """获取指定的服务对象"""
        return self._services.get(service_name)

    def has_service(self, service_name: str) -> bool:
        """检查是否有指定的服务对象"""
        return service_name in self._services and self._services[service_name] is not None

    def set_action_context(self, thinking_id: str = None, shutting_down: bool = False, **kwargs):
        """设置action上下文信息"""
        if thinking_id:
            self._action_context["thinking_id"] = thinking_id
        self._action_context["shutting_down"] = shutting_down
        self._action_context.update(kwargs)

    def get_action_context(self, key: str, default=None):
        """获取action上下文信息"""
        return self._action_context.get(key, default)


# 便捷的工厂函数
def create_plugin_api(
    chat_stream=None, expressor=None, replyer=None, observations=None, log_prefix: str = "[Plugin]"
) -> PluginAPI:
    """
    创建插件API实例的便捷函数

    Args:
        chat_stream: 聊天流对象
        expressor: 表达器对象
        replyer: 回复器对象
        observations: 观察列表
        log_prefix: 日志前缀

    Returns:
        PluginAPI: 配置好的插件API实例
    """
    return PluginAPI(
        chat_stream=chat_stream, expressor=expressor, replyer=replyer, observations=observations, log_prefix=log_prefix
    )


def create_command_api(message, log_prefix: str = "[Command]") -> PluginAPI:
    """
    为命令创建插件API实例的便捷函数

    Args:
        message: 消息对象，应该包含 chat_stream 等信息
        log_prefix: 日志前缀

    Returns:
        PluginAPI: 配置好的插件API实例
    """
    chat_stream = getattr(message, "chat_stream", None)

    api = PluginAPI(chat_stream=chat_stream, log_prefix=log_prefix)

    return api


# 导出主要接口
__all__ = [
    "PluginAPI",
    "create_plugin_api",
    "create_command_api",
    # 也可以导出各个API类供单独使用
    "MessageAPI",
    "LLMAPI",
    "DatabaseAPI",
    "ConfigAPI",
    "UtilsAPI",
    "StreamAPI",
    "HearflowAPI",
]
