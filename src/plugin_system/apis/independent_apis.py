"""
独立API聚合模块

聚合了不需要Action组件依赖的API，这些API可以独立使用，不需要注入服务对象。
包括：LLMAPI、ConfigAPI、UtilsAPI、StreamAPI、HearflowAPI等独立功能的API。
"""

from src.plugin_system.apis.llm_api import LLMAPI
from src.plugin_system.apis.config_api import ConfigAPI
from src.plugin_system.apis.utils_api import UtilsAPI
from src.plugin_system.apis.stream_api import StreamAPI
from src.plugin_system.apis.hearflow_api import HearflowAPI
from src.common.logger_manager import get_logger

logger = get_logger("independent_apis")


class IndependentAPI(LLMAPI, ConfigAPI, UtilsAPI, StreamAPI, HearflowAPI):
    """
    独立API聚合类

    聚合了不需要Action组件依赖的API功能。这些API的特点：
    - 不需要chat_stream、expressor等服务对象
    - 可以独立调用，不依赖Action执行上下文
    - 主要是工具类方法和配置查询方法

    包含的API：
    - LLMAPI: LLM模型调用（仅需要全局配置）
    - ConfigAPI: 配置读取（使用全局配置）
    - UtilsAPI: 工具方法（文件操作、时间处理等）
    - StreamAPI: 聊天流查询（使用ChatManager）
    - HearflowAPI: 心流状态控制（使用heartflow）

    使用场景：
    - 在Command组件中使用
    - 独立的工具函数调用
    - 配置查询和系统状态检查
    """

    def __init__(self, log_prefix: str = "[IndependentAPI]"):
        """
        初始化独立API

        Args:
            log_prefix: 日志前缀，用于区分不同的调用来源
        """
        self.log_prefix = log_prefix

        logger.debug(f"{self.log_prefix} IndependentAPI 初始化完成")


# 提供便捷的静态访问方式
class StaticAPI:
    """
    静态API类

    提供完全静态的API访问方式，不需要实例化，适合简单的工具调用。
    """

    # LLM相关
    @staticmethod
    def get_available_models():
        """获取可用的LLM模型"""
        api = LLMAPI()
        return api.get_available_models()

    @staticmethod
    async def generate_with_model(prompt: str, model_config: dict, **kwargs):
        """使用LLM生成内容"""
        api = LLMAPI()
        api.log_prefix = "[StaticAPI]"
        return await api.generate_with_model(prompt, model_config, **kwargs)

    # 配置相关
    @staticmethod
    def get_global_config(key: str, default=None):
        """获取全局配置"""
        api = ConfigAPI()
        return api.get_global_config(key, default)

    @staticmethod
    async def get_user_id_by_name(person_name: str):
        """根据用户名获取用户ID"""
        api = ConfigAPI()
        return await api.get_user_id_by_person_name(person_name)

    # 工具相关
    @staticmethod
    def get_timestamp():
        """获取当前时间戳"""
        api = UtilsAPI()
        return api.get_timestamp()

    @staticmethod
    def format_time(timestamp=None, format_str="%Y-%m-%d %H:%M:%S"):
        """格式化时间"""
        api = UtilsAPI()
        return api.format_time(timestamp, format_str)

    @staticmethod
    def generate_unique_id():
        """生成唯一ID"""
        api = UtilsAPI()
        return api.generate_unique_id()

    # 聊天流相关
    @staticmethod
    def get_chat_stream_by_group_id(group_id: str, platform: str = "qq"):
        """通过群ID获取聊天流"""
        api = StreamAPI()
        api.log_prefix = "[StaticAPI]"
        return api.get_chat_stream_by_group_id(group_id, platform)

    @staticmethod
    def get_all_group_chat_streams(platform: str = "qq"):
        """获取所有群聊聊天流"""
        api = StreamAPI()
        api.log_prefix = "[StaticAPI]"
        return api.get_all_group_chat_streams(platform)

    # 心流相关
    @staticmethod
    async def get_sub_hearflow_by_chat_id(chat_id: str):
        """获取子心流"""
        api = HearflowAPI()
        api.log_prefix = "[StaticAPI]"
        return await api.get_sub_hearflow_by_chat_id(chat_id)

    @staticmethod
    async def set_sub_hearflow_chat_state(chat_id: str, target_state):
        """设置子心流状态"""
        api = HearflowAPI()
        api.log_prefix = "[StaticAPI]"
        return await api.set_sub_hearflow_chat_state(chat_id, target_state)
