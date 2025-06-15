from abc import ABC, abstractmethod
from typing import Tuple
from src.common.logger import get_logger
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
        plugin_config: dict = None,
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
            plugin_config: 插件配置字典
            **kwargs: 其他参数
        """
        self.action_data = action_data
        self.reasoning = reasoning
        self.cycle_timers = cycle_timers
        self.thinking_id = thinking_id
        self.log_prefix = log_prefix
        self.shutting_down = shutting_down

        # 设置动作基本信息实例属性
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
            plugin_config=plugin_config or kwargs.get("plugin_config"),
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

    async def send_text(self, content: str) -> bool:
        """发送回复消息

        Args:
            content: 回复内容

        Returns:
            bool: 是否发送成功
        """
        chat_stream = self.api.get_service("chat_stream")
        if not chat_stream:
            logger.error(f"{self.log_prefix} 没有可用的聊天流发送回复")
            return False

        if chat_stream.group_info:
            # 群聊
            return await self.api.send_text_to_group(
                text=content, group_id=str(chat_stream.group_info.group_id), platform=chat_stream.platform
            )
        else:
            # 私聊
            return await self.api.send_text_to_user(
                text=content, user_id=str(chat_stream.user_info.user_id), platform=chat_stream.platform
            )

    async def send_type(self, type: str, text: str, typing: bool = False) -> bool:
        """发送回复消息

        Args:
            text: 回复内容

        Returns:
            bool: 是否发送成功
        """
        chat_stream = self.api.get_service("chat_stream")
        if not chat_stream:
            logger.error(f"{self.log_prefix} 没有可用的聊天流发送回复")
            return False

        if chat_stream.group_info:
            # 群聊
            return await self.api.send_message_to_target(
                message_type=type,
                content=text,
                platform=chat_stream.platform,
                target_id=str(chat_stream.group_info.group_id),
                is_group=True,
                typing=typing,
            )
        else:
            # 私聊
            return await self.api.send_message_to_target(
                message_type=type,
                content=text,
                platform=chat_stream.platform,
                target_id=str(chat_stream.user_info.user_id),
                is_group=False,
                typing=typing,
            )

    async def send_command(self, command_name: str, args: dict = None, display_message: str = None) -> bool:
        """发送命令消息

        使用和send_text相同的方式通过MessageAPI发送命令

        Args:
            command_name: 命令名称
            args: 命令参数
            display_message: 显示消息

        Returns:
            bool: 是否发送成功
        """
        try:
            # 构造命令数据
            command_data = {"name": command_name, "args": args or {}}

            # 使用send_message_to_target方法发送命令
            chat_stream = self.api.get_service("chat_stream")
            if not chat_stream:
                logger.error(f"{self.log_prefix} 没有可用的聊天流发送命令")
                return False

            if chat_stream.group_info:
                # 群聊
                success = await self.api.send_message_to_target(
                    message_type="command",
                    content=command_data,
                    platform=chat_stream.platform,
                    target_id=str(chat_stream.group_info.group_id),
                    is_group=True,
                    display_message=display_message or f"执行命令: {command_name}",
                )
            else:
                # 私聊
                success = await self.api.send_message_to_target(
                    message_type="command",
                    content=command_data,
                    platform=chat_stream.platform,
                    target_id=str(chat_stream.user_info.user_id),
                    is_group=False,
                    display_message=display_message or f"执行命令: {command_name}",
                )

            if success:
                logger.info(f"{self.log_prefix} 成功发送命令: {command_name}")
            else:
                logger.error(f"{self.log_prefix} 发送命令失败: {command_name}")

            return success

        except Exception as e:
            logger.error(f"{self.log_prefix} 发送命令时出错: {e}")
            return False

    async def send_message_by_expressor(self, text: str, target: str = "") -> bool:
        """通过expressor发送文本消息的Action专用方法

        Args:
            text: 要发送的消息文本
            target: 目标消息（可选）

        Returns:
            bool: 是否发送成功
        """
        try:
            from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
            from src.chat.focus_chat.hfc_utils import create_empty_anchor_message

            # 获取服务
            expressor = self.api.get_service("expressor")
            chat_stream = self.api.get_service("chat_stream")
            observations = self.api.get_service("observations") or []

            if not expressor or not chat_stream:
                logger.error(f"{self.log_prefix} 无法通过expressor发送消息：缺少必要的服务")
                return False

            # 构造动作数据
            reply_data = {"text": text, "target": target, "emojis": []}

            # 查找 ChattingObservation 实例
            chatting_observation = None
            for obs in observations:
                if isinstance(obs, ChattingObservation):
                    chatting_observation = obs
                    break

            if not chatting_observation:
                logger.warning(f"{self.log_prefix} 未找到 ChattingObservation 实例，创建占位符")
                anchor_message = await create_empty_anchor_message(
                    chat_stream.platform, chat_stream.group_info, chat_stream
                )
            else:
                anchor_message = chatting_observation.search_message_by_text(target)
                if not anchor_message:
                    logger.info(f"{self.log_prefix} 未找到锚点消息，创建占位符")
                    anchor_message = await create_empty_anchor_message(
                        chat_stream.platform, chat_stream.group_info, chat_stream
                    )
                else:
                    anchor_message.update_chat_stream(chat_stream)

            # 使用Action上下文信息发送消息
            success, _ = await expressor.deal_reply(
                cycle_timers=self.cycle_timers,
                action_data=reply_data,
                anchor_message=anchor_message,
                reasoning=self.reasoning,
                thinking_id=self.thinking_id,
            )

            if success:
                logger.info(f"{self.log_prefix} 成功通过expressor发送消息")
            else:
                logger.error(f"{self.log_prefix} 通过expressor发送消息失败")

            return success

        except Exception as e:
            logger.error(f"{self.log_prefix} 通过expressor发送消息时出错: {e}")
            return False

    async def send_message_by_replyer(self, target: str = "", extra_info_block: str = None) -> bool:
        """通过replyer发送消息的Action专用方法

        Args:
            target: 目标消息（可选）
            extra_info_block: 额外信息块（可选）

        Returns:
            bool: 是否发送成功
        """
        try:
            from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
            from src.chat.focus_chat.hfc_utils import create_empty_anchor_message

            # 获取服务
            replyer = self.api.get_service("replyer")
            chat_stream = self.api.get_service("chat_stream")
            observations = self.api.get_service("observations") or []

            if not replyer or not chat_stream:
                logger.error(f"{self.log_prefix} 无法通过replyer发送消息：缺少必要的服务")
                return False

            # 构造动作数据
            reply_data = {"target": target, "extra_info_block": extra_info_block}

            # 查找 ChattingObservation 实例
            chatting_observation = None
            for obs in observations:
                if isinstance(obs, ChattingObservation):
                    chatting_observation = obs
                    break

            if not chatting_observation:
                logger.warning(f"{self.log_prefix} 未找到 ChattingObservation 实例，创建占位符")
                anchor_message = await create_empty_anchor_message(
                    chat_stream.platform, chat_stream.group_info, chat_stream
                )
            else:
                anchor_message = chatting_observation.search_message_by_text(target)
                if not anchor_message:
                    logger.info(f"{self.log_prefix} 未找到锚点消息，创建占位符")
                    anchor_message = await create_empty_anchor_message(
                        chat_stream.platform, chat_stream.group_info, chat_stream
                    )
                else:
                    anchor_message.update_chat_stream(chat_stream)

            # 使用Action上下文信息发送消息
            success, _ = await replyer.deal_reply(
                cycle_timers=self.cycle_timers,
                action_data=reply_data,
                anchor_message=anchor_message,
                reasoning=self.reasoning,
                thinking_id=self.thinking_id,
            )

            if success:
                logger.info(f"{self.log_prefix} 成功通过replyer发送消息")
            else:
                logger.error(f"{self.log_prefix} 通过replyer发送消息失败")

            return success

        except Exception as e:
            logger.error(f"{self.log_prefix} 通过replyer发送消息时出错: {e}")
            return False

    @classmethod
    def get_action_info(cls) -> "ActionInfo":
        """从类属性生成ActionInfo
        
        所有信息都从类属性中读取，确保一致性和完整性。
        Action类必须定义所有必要的类属性。

        Returns:
            ActionInfo: 生成的Action信息对象
        """

        # 从类属性读取名称，如果没有定义则使用类名自动生成
        name = getattr(cls, "action_name", cls.__name__.lower().replace("action", ""))
        
        # 从类属性读取描述，如果没有定义则使用文档字符串的第一行
        description = getattr(cls, "action_description", None)
        if description is None:
            description = "Action动作"

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
