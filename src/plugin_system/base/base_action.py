from abc import ABC, abstractmethod
from typing import Tuple, Optional
from src.common.logger import get_logger
from src.plugin_system.base.component_types import ActionActivationType, ChatMode, ActionInfo, ComponentType
from src.plugin_system.apis import send_api, database_api, message_api
import time
import asyncio

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

        # 保存插件配置
        self.plugin_config = plugin_config or {}

        # 设置动作基本信息实例属性
        self.action_name: str = getattr(self, "action_name", self.__class__.__name__.lower().replace("action", ""))
        self.action_description: str = getattr(self, "action_description", self.__doc__ or "Action组件")
        self.action_parameters: dict = getattr(self.__class__, "action_parameters", {}).copy()
        self.action_require: list[str] = getattr(self.__class__, "action_require", []).copy()

        # 设置激活类型实例属性（从类属性复制，提供默认值）
        self.focus_activation_type: str = self._get_activation_type_value("focus_activation_type", "always")
        self.normal_activation_type: str = self._get_activation_type_value("normal_activation_type", "always")
        self.random_activation_probability: float = getattr(self.__class__, "random_activation_probability", 0.0)
        self.llm_judge_prompt: str = getattr(self.__class__, "llm_judge_prompt", "")
        self.activation_keywords: list[str] = getattr(self.__class__, "activation_keywords", []).copy()
        self.keyword_case_sensitive: bool = getattr(self.__class__, "keyword_case_sensitive", False)
        self.mode_enable: str = self._get_mode_value("mode_enable", "all")
        self.parallel_action: bool = getattr(self.__class__, "parallel_action", True)
        self.associated_types: list[str] = getattr(self.__class__, "associated_types", []).copy()

        # =============================================================================
        # 便捷属性 - 直接在初始化时获取常用聊天信息（带类型注解）
        # =============================================================================

        # 获取聊天流对象
        self.chat_stream = chat_stream or kwargs.get("chat_stream")

        self.chat_id = self.chat_stream.stream_id
        # 初始化基础信息（带类型注解）
        self.is_group: bool = False
        self.platform: Optional[str] = None
        self.group_id: Optional[str] = None
        self.user_id: Optional[str] = None
        self.target_id: Optional[str] = None
        self.group_name: Optional[str] = None
        self.user_nickname: Optional[str] = None

        # 如果有聊天流，提取所有信息
        if self.chat_stream:
            self.platform = getattr(self.chat_stream, "platform", None)

            # 获取群聊信息
            # print(self.chat_stream)
            # print(self.chat_stream.group_info)
            if self.chat_stream.group_info:
                self.is_group = True
                self.group_id = str(self.chat_stream.group_info.group_id)
                self.group_name = getattr(self.chat_stream.group_info, "group_name", None)
            else:
                self.is_group = False
                self.user_id = str(self.chat_stream.user_info.user_id)
                self.user_nickname = getattr(self.chat_stream.user_info, "user_nickname", None)

            # 设置目标ID（群聊用群ID，私聊用户ID）
            self.target_id = self.group_id if self.is_group else self.user_id

        logger.debug(f"{self.log_prefix} Action组件初始化完成")
        logger.debug(
            f"{self.log_prefix} 聊天信息: 类型={'群聊' if self.is_group else '私聊'}, 平台={self.platform}, 目标={self.target_id}"
        )

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

    async def wait_for_new_message(self, timeout: int = 1200) -> Tuple[bool, str]:
        """等待新消息或超时

        在loop_start_time之后等待新消息，如果没有新消息且没有超时，就一直等待。
        使用message_api检查self.chat_id对应的聊天中是否有新消息。

        Args:
            timeout: 超时时间（秒），默认1200秒

        Returns:
            Tuple[bool, str]: (是否收到新消息, 空字符串)
        """
        try:
            # 获取循环开始时间，如果没有则使用当前时间
            loop_start_time = self.action_data.get("loop_start_time", time.time())
            logger.info(f"{self.log_prefix} 开始等待新消息... (最长等待: {timeout}秒, 从时间点: {loop_start_time})")

            # 确保有有效的chat_id
            if not self.chat_id:
                logger.error(f"{self.log_prefix} 等待新消息失败: 没有有效的chat_id")
                return False, "没有有效的chat_id"

            wait_start_time = asyncio.get_event_loop().time()
            while True:
                # 检查关闭标志
                # shutting_down = self.get_action_context("shutting_down", False)
                # if shutting_down:
                # logger.info(f"{self.log_prefix} 等待新消息时检测到关闭信号，中断等待")
                # return False, ""

                # 检查新消息
                current_time = time.time()
                new_message_count = message_api.count_new_messages(
                    chat_id=self.chat_id, start_time=loop_start_time, end_time=current_time
                )

                if new_message_count > 0:
                    logger.info(f"{self.log_prefix} 检测到{new_message_count}条新消息，聊天ID: {self.chat_id}")
                    return True, ""

                # 检查超时
                elapsed_time = asyncio.get_event_loop().time() - wait_start_time
                if elapsed_time > timeout:
                    logger.warning(f"{self.log_prefix} 等待新消息超时({timeout}秒)，聊天ID: {self.chat_id}")
                    return False, ""

                # 每30秒记录一次等待状态
                if int(elapsed_time) % 15 == 0 and int(elapsed_time) > 0:
                    logger.debug(f"{self.log_prefix} 已等待{int(elapsed_time)}秒，继续等待新消息...")

                # 短暂休眠
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info(f"{self.log_prefix} 等待新消息被中断 (CancelledError)")
            return False, ""
        except Exception as e:
            logger.error(f"{self.log_prefix} 等待新消息时发生错误: {e}")
            return False, f"等待新消息失败: {str(e)}"

    async def send_text(self, content: str, reply_to: str = "", typing: bool = False) -> bool:
        """发送文本消息

        Args:
            content: 文本内容
            reply_to: 回复消息，格式为"发送者:消息内容"

        Returns:
            bool: 是否发送成功
        """
        if not self.chat_id:
            logger.error(f"{self.log_prefix} 缺少聊天ID")
            return False

        return await send_api.text_to_stream(text=content, stream_id=self.chat_id, reply_to=reply_to, typing=typing)

    async def send_emoji(self, emoji_base64: str) -> bool:
        """发送表情包

        Args:
            emoji_base64: 表情包的base64编码

        Returns:
            bool: 是否发送成功
        """
        if not self.chat_id:
            logger.error(f"{self.log_prefix} 缺少聊天ID")
            return False

        return await send_api.emoji_to_stream(emoji_base64, self.chat_id)

    async def send_image(self, image_base64: str) -> bool:
        """发送图片

        Args:
            image_base64: 图片的base64编码

        Returns:
            bool: 是否发送成功
        """
        if not self.chat_id:
            logger.error(f"{self.log_prefix} 缺少聊天ID")
            return False

        return await send_api.image_to_stream(image_base64, self.chat_id)

    async def send_custom(self, message_type: str, content: str, typing: bool = False, reply_to: str = "") -> bool:
        """发送自定义类型消息

        Args:
            message_type: 消息类型，如"video"、"file"、"audio"等
            content: 消息内容
            typing: 是否显示正在输入
            reply_to: 回复消息，格式为"发送者:消息内容"

        Returns:
            bool: 是否发送成功
        """
        if not self.chat_id:
            logger.error(f"{self.log_prefix} 缺少聊天ID")
            return False

        return await send_api.custom_to_stream(
            message_type=message_type,
            content=content,
            stream_id=self.chat_id,
            typing=typing,
            reply_to=reply_to,
        )

    async def store_action_info(
        self,
        action_build_into_prompt: bool = False,
        action_prompt_display: str = "",
        action_done: bool = True,
    ) -> None:
        """存储动作信息到数据库

        Args:
            action_build_into_prompt: 是否构建到提示中
            action_prompt_display: 显示的action提示信息
            action_done: action是否完成
        """
        await database_api.store_action_info(
            chat_stream=self.chat_stream,
            action_build_into_prompt=action_build_into_prompt,
            action_prompt_display=action_prompt_display,
            action_done=action_done,
            thinking_id=self.thinking_id,
            action_data=self.action_data,
            action_name=self.action_name,
        )

    async def send_command(
        self, command_name: str, args: dict = None, display_message: str = None, storage_message: bool = True
    ) -> bool:
        """发送命令消息

        使用stream API发送命令

        Args:
            command_name: 命令名称
            args: 命令参数
            display_message: 显示消息
            storage_message: 是否存储消息到数据库

        Returns:
            bool: 是否发送成功
        """
        try:
            if not self.chat_id:
                logger.error(f"{self.log_prefix} 缺少聊天ID")
                return False

            # 构造命令数据
            command_data = {"name": command_name, "args": args or {}}

            success = await send_api.command_to_stream(
                command=command_data,
                stream_id=self.chat_id,
                storage_message=storage_message,
            )

            if success:
                logger.info(f"{self.log_prefix} 成功发送命令: {command_name}")
            else:
                logger.error(f"{self.log_prefix} 发送命令失败: {command_name}")

            return success

        except Exception as e:
            logger.error(f"{self.log_prefix} 发送命令时出错: {e}")
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
            focus_activation_type=get_enum_value("focus_activation_type", "always"),
            normal_activation_type=get_enum_value("normal_activation_type", "always"),
            activation_keywords=getattr(cls, "activation_keywords", []).copy(),
            keyword_case_sensitive=getattr(cls, "keyword_case_sensitive", False),
            mode_enable=get_mode_value("mode_enable", "all"),
            parallel_action=getattr(cls, "parallel_action", True),
            random_activation_probability=getattr(cls, "random_activation_probability", 0.3),
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

    def get_action_context(self, key: str, default=None):
        """获取action上下文信息

        Args:
            key: 上下文键名
            default: 默认值

        Returns:
            Any: 上下文值或默认值
        """
        return self.api.get_action_context(key, default)

    def get_config(self, key: str, default=None):
        """获取插件配置值，支持嵌套键访问

        Args:
            key: 配置键名，支持嵌套访问如 "section.subsection.key"
            default: 默认值

        Returns:
            Any: 配置值或默认值
        """
        if not self.plugin_config:
            return default

        # 支持嵌套键访问
        keys = key.split(".")
        current = self.plugin_config

        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default

        return current
