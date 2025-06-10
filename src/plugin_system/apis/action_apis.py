"""
Action相关API聚合模块

聚合了需要Action组件依赖的API，这些API需要通过Action初始化时注入的服务对象才能正常工作。
包括：MessageAPI、DatabaseAPI等需要chat_stream、expressor等服务的API。
"""

from src.plugin_system.apis.message_api import MessageAPI
from src.plugin_system.apis.database_api import DatabaseAPI
from src.common.logger_manager import get_logger

logger = get_logger("action_apis")


class ActionAPI(MessageAPI, DatabaseAPI):
    """
    Action相关API聚合类

    聚合了需要Action组件依赖的API功能。这些API需要以下依赖：
    - _services: 包含chat_stream、expressor、replyer、observations等服务对象
    - log_prefix: 日志前缀
    - thinking_id: 思考ID
    - cycle_timers: 计时器
    - action_data: Action数据

    使用场景：
    - 在Action组件中使用，需要发送消息、存储数据等功能
    - 需要访问聊天上下文和执行环境的操作
    """

    def __init__(
        self,
        chat_stream=None,
        expressor=None,
        replyer=None,
        observations=None,
        log_prefix: str = "[ActionAPI]",
        thinking_id: str = "",
        cycle_timers: dict = None,
        action_data: dict = None,
    ):
        """
        初始化Action相关API

        Args:
            chat_stream: 聊天流对象
            expressor: 表达器对象
            replyer: 回复器对象
            observations: 观察列表
            log_prefix: 日志前缀
            thinking_id: 思考ID
            cycle_timers: 计时器字典
            action_data: Action数据
        """
        # 存储依赖对象
        self._services = {
            "chat_stream": chat_stream,
            "expressor": expressor,
            "replyer": replyer,
            "observations": observations or [],
        }

        self.log_prefix = log_prefix
        self.thinking_id = thinking_id
        self.cycle_timers = cycle_timers or {}
        self.action_data = action_data or {}

        logger.debug(f"{self.log_prefix} ActionAPI 初始化完成")

    def set_chat_stream(self, chat_stream):
        """设置聊天流对象"""
        self._services["chat_stream"] = chat_stream
        logger.debug(f"{self.log_prefix} 设置聊天流")

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
        logger.debug(f"{self.log_prefix} 设置观察列表")
