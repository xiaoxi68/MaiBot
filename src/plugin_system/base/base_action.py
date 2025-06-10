from abc import ABC, abstractmethod
from typing import Tuple
from src.common.logger_manager import get_logger
from src.plugin_system.apis.plugin_api import PluginAPI
from src.plugin_system.base.component_types import ActionActivationType, ChatMode, ActionInfo, ComponentType

logger = get_logger("base_action")


class BaseAction(ABC):
    """Action组件基类

    Action是插件的一种组件类型，用于处理聊天中的动作逻辑

    子类可以通过类属性定义激活条件，这些会在实例化时转换为实例属性：
    - focus_activation_type: 专注模式激活类型
    - normal_activation_type: 普通模式激活类型
    - activation_keywords: 激活关键词列表
    - keyword_case_sensitive: 关键词是否区分大小写
    - mode_enable: 启用的聊天模式
    - parallel_action: 是否允许并行执行
    - random_activation_probability: 随机激活概率
    - llm_judge_prompt: LLM判断提示词
    """

    def __init__(
        self,
        action_data: dict,
        reasoning: str,
        cycle_timers: dict,
        thinking_id: str,
        observations: list = None,
        expressor=None,
        replyer=None,
        chat_stream=None,
        log_prefix: str = "",
        shutting_down: bool = False,
        **kwargs,
    ):
        """初始化Action组件

        Args:
            action_data: 动作数据
            reasoning: 执行该动作的理由
            cycle_timers: 计时器字典
            thinking_id: 思考ID
            observations: 观察列表
            expressor: 表达器对象
            replyer: 回复器对象
            chat_stream: 聊天流对象
            log_prefix: 日志前缀
            shutting_down: 是否正在关闭
            **kwargs: 其他参数
        """
        self.action_data = action_data
        self.reasoning = reasoning
        self.cycle_timers = cycle_timers
        self.thinking_id = thinking_id
        self.log_prefix = log_prefix
        self.shutting_down = shutting_down

        # 设置动作基本信息实例属性（兼容旧系统）
        self.action_name: str = getattr(self, "action_name", self.__class__.__name__.lower().replace("action", ""))
        self.action_description: str = getattr(self, "action_description", self.__doc__ or "Action组件")
        self.action_parameters: dict = getattr(self.__class__, "action_parameters", {}).copy()
        self.action_require: list[str] = getattr(self.__class__, "action_require", []).copy()

        # 设置激活类型实例属性（从类属性复制，提供默认值）
        self.focus_activation_type: str = self._get_activation_type_value("focus_activation_type", "never")
        self.normal_activation_type: str = self._get_activation_type_value("normal_activation_type", "never")
        self.random_activation_probability: float = getattr(self.__class__, "random_activation_probability", 0.0)
        self.llm_judge_prompt: str = getattr(self.__class__, "llm_judge_prompt", "")
        self.activation_keywords: list[str] = getattr(self.__class__, "activation_keywords", []).copy()
        self.keyword_case_sensitive: bool = getattr(self.__class__, "keyword_case_sensitive", False)
        self.mode_enable: str = self._get_mode_value("mode_enable", "all")
        self.parallel_action: bool = getattr(self.__class__, "parallel_action", True)
        self.associated_types: list[str] = getattr(self.__class__, "associated_types", []).copy()
        self.enable_plugin: bool = True  # 默认启用

        # 创建API实例，传递所有服务对象
        self.api = PluginAPI(
            chat_stream=chat_stream or kwargs.get("chat_stream"),
            expressor=expressor or kwargs.get("expressor"),
            replyer=replyer or kwargs.get("replyer"),
            observations=observations or kwargs.get("observations", []),
            log_prefix=log_prefix,
        )

        # 设置API的action上下文
        self.api.set_action_context(thinking_id=thinking_id, shutting_down=shutting_down)

        logger.debug(f"{self.log_prefix} Action组件初始化完成")

    def _get_activation_type_value(self, attr_name: str, default: str) -> str:
        """获取激活类型的字符串值"""
        attr = getattr(self.__class__, attr_name, None)
        if attr is None:
            return default
        if hasattr(attr, "value"):
            return attr.value
        return str(attr)

    def _get_mode_value(self, attr_name: str, default: str) -> str:
        """获取模式的字符串值"""
        attr = getattr(self.__class__, attr_name, None)
        if attr is None:
            return default
        if hasattr(attr, "value"):
            return attr.value
        return str(attr)

    async def send_reply(self, content: str) -> bool:
        """发送回复消息

        Args:
            content: 回复内容

        Returns:
            bool: 是否发送成功
        """
        return await self.api.send_message("text", content)

    @classmethod
    def get_action_info(cls, name: str = None, description: str = None) -> "ActionInfo":
        """从类属性生成ActionInfo

        Args:
            name: Action名称，如果不提供则使用类名
            description: Action描述，如果不提供则使用类文档字符串

        Returns:
            ActionInfo: 生成的Action信息对象
        """

        # 自动生成名称和描述
        if name is None:
            name = cls.__name__.lower().replace("action", "")
        if description is None:
            description = cls.__doc__ or f"{cls.__name__} Action组件"
            description = description.strip().split("\n")[0]  # 取第一行作为描述

        # 安全获取激活类型值
        def get_enum_value(attr_name, default):
            attr = getattr(cls, attr_name, None)
            if attr is None:
                # 如果没有定义，返回默认的枚举值
                return getattr(ActionActivationType, default.upper(), ActionActivationType.NEVER)
            return attr

        def get_mode_value(attr_name, default):
            attr = getattr(cls, attr_name, None)
            if attr is None:
                return getattr(ChatMode, default.upper(), ChatMode.ALL)
            return attr

        return ActionInfo(
            name=name,
            component_type=ComponentType.ACTION,
            description=description,
            focus_activation_type=get_enum_value("focus_activation_type", "never"),
            normal_activation_type=get_enum_value("normal_activation_type", "never"),
            activation_keywords=getattr(cls, "activation_keywords", []).copy(),
            keyword_case_sensitive=getattr(cls, "keyword_case_sensitive", False),
            mode_enable=get_mode_value("mode_enable", "all"),
            parallel_action=getattr(cls, "parallel_action", True),
            random_activation_probability=getattr(cls, "random_activation_probability", 0.0),
            llm_judge_prompt=getattr(cls, "llm_judge_prompt", ""),
            # 使用正确的字段名
            action_parameters=getattr(cls, "action_parameters", {}).copy(),
            action_require=getattr(cls, "action_require", []).copy(),
            associated_types=getattr(cls, "associated_types", []).copy(),
        )

    @abstractmethod
    async def execute(self) -> Tuple[bool, str]:
        """执行Action的抽象方法，子类必须实现

        Returns:
            Tuple[bool, str]: (是否执行成功, 回复文本)
        """
        pass

    async def handle_action(self) -> Tuple[bool, str]:
        """兼容旧系统的handle_action接口，委托给execute方法

        为了保持向后兼容性，旧系统的代码可能会调用handle_action方法。
        此方法将调用委托给新的execute方法。

        Returns:
            Tuple[bool, str]: (是否执行成功, 回复文本)
        """
        return await self.execute()
