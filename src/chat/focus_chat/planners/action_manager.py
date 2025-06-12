from typing import Dict, List, Optional, Type, Any
from src.plugin_system.base.base_action import BaseAction
from src.chat.heart_flow.observation.observation import Observation
from src.chat.focus_chat.replyer.default_replyer import DefaultReplyer
from src.chat.focus_chat.expressors.default_expressor import DefaultExpressor
from src.chat.message_receive.chat_stream import ChatStream
from src.common.logger import get_logger

# 不再需要导入动作类，因为已经在main.py中导入
# import src.chat.actions.default_actions  # noqa

logger = get_logger("action_manager")

# 定义动作信息类型
ActionInfo = Dict[str, Any]


class PluginActionWrapper(BaseAction):
    """
    新插件系统Action组件的兼容性包装器

    将新插件系统的Action组件包装为旧系统兼容的BaseAction接口
    """

    def __init__(
        self, plugin_action, action_name: str, action_data: dict, reasoning: str, cycle_timers: dict, thinking_id: str
    ):
        """初始化包装器"""
        # 调用旧系统BaseAction初始化，只传递它能接受的参数
        super().__init__(
            action_data=action_data, reasoning=reasoning, cycle_timers=cycle_timers, thinking_id=thinking_id
        )

        # 存储插件Action实例（它已经包含了所有必要的服务对象）
        self.plugin_action = plugin_action
        self.action_name = action_name

        # 从插件Action实例复制属性到包装器
        self._sync_attributes_from_plugin_action()

    def _sync_attributes_from_plugin_action(self):
        """从插件Action实例同步属性到包装器"""
        # 基本属性
        self.action_name = getattr(self.plugin_action, "action_name", self.action_name)

        # 设置兼容的默认值
        self.action_description = f"插件Action: {self.action_name}"
        self.action_parameters = {}
        self.action_require = []

        # 激活类型属性（从新插件系统转换）
        plugin_focus_type = getattr(self.plugin_action, "focus_activation_type", None)
        plugin_normal_type = getattr(self.plugin_action, "normal_activation_type", None)

        if plugin_focus_type:
            self.focus_activation_type = (
                plugin_focus_type.value if hasattr(plugin_focus_type, "value") else str(plugin_focus_type)
            )
        if plugin_normal_type:
            self.normal_activation_type = (
                plugin_normal_type.value if hasattr(plugin_normal_type, "value") else str(plugin_normal_type)
            )

        # 其他属性
        self.random_activation_probability = getattr(self.plugin_action, "random_activation_probability", 0.0)
        self.llm_judge_prompt = getattr(self.plugin_action, "llm_judge_prompt", "")
        self.activation_keywords = getattr(self.plugin_action, "activation_keywords", [])
        self.keyword_case_sensitive = getattr(self.plugin_action, "keyword_case_sensitive", False)

        # 模式和并行设置
        plugin_mode = getattr(self.plugin_action, "mode_enable", None)
        if plugin_mode:
            self.mode_enable = plugin_mode.value if hasattr(plugin_mode, "value") else str(plugin_mode)

        self.parallel_action = getattr(self.plugin_action, "parallel_action", True)
        self.enable_plugin = True

    async def handle_action(self) -> tuple[bool, str]:
        """兼容旧系统的动作处理接口，委托给插件Action的execute方法"""
        try:
            # 调用插件Action的execute方法
            success, response = await self.plugin_action.execute()

            logger.debug(f"插件Action {self.action_name} 执行{'成功' if success else '失败'}: {response}")
            return success, response

        except Exception as e:
            logger.error(f"插件Action {self.action_name} 执行异常: {e}")
            return False, f"插件Action执行失败: {str(e)}"


class ActionManager:
    """
    动作管理器，用于管理各种类型的动作
    """

    def __init__(self):
        """初始化动作管理器"""
        # 所有注册的动作集合
        self._registered_actions: Dict[str, ActionInfo] = {}
        # 当前正在使用的动作集合，默认加载默认动作
        self._using_actions: Dict[str, ActionInfo] = {}

        # 默认动作集，仅作为快照，用于恢复默认
        self._default_actions: Dict[str, ActionInfo] = {}

        # 加载所有已注册动作
        self._load_registered_actions()

        # 加载插件动作
        self._load_plugin_actions()

        # 初始化时将默认动作加载到使用中的动作
        self._using_actions = self._default_actions.copy()

        # 添加系统核心动作
        self._add_system_core_actions()

    def _load_registered_actions(self) -> None:
        """
        加载所有通过装饰器注册的动作
        """
        try:
            # 从组件注册中心获取所有已注册的action
            from src.plugin_system.core.component_registry import component_registry

            action_registry = component_registry.get_action_registry()

            # 从action_registry获取所有已注册动作
            for action_name, action_class in action_registry.items():
                # 获取动作相关信息

                # 不读取插件动作和基类
                if action_name == "base_action" or action_name == "plugin_action":
                    continue

                action_description: str = getattr(action_class, "action_description", "")
                action_parameters: dict[str:str] = getattr(action_class, "action_parameters", {})
                action_require: list[str] = getattr(action_class, "action_require", [])
                associated_types: list[str] = getattr(action_class, "associated_types", [])
                is_enabled: bool = getattr(action_class, "enable_plugin", True)

                # 获取激活类型相关属性
                focus_activation_type: str = getattr(action_class, "focus_activation_type", "always")
                normal_activation_type: str = getattr(action_class, "normal_activation_type", "always")

                random_probability: float = getattr(action_class, "random_activation_probability", 0.3)
                llm_judge_prompt: str = getattr(action_class, "llm_judge_prompt", "")
                activation_keywords: list[str] = getattr(action_class, "activation_keywords", [])
                keyword_case_sensitive: bool = getattr(action_class, "keyword_case_sensitive", False)

                # 获取模式启用属性
                mode_enable: str = getattr(action_class, "mode_enable", "all")

                # 获取并行执行属性
                parallel_action: bool = getattr(action_class, "parallel_action", False)

                if action_name and action_description:
                    # 创建动作信息字典
                    action_info = {
                        "description": action_description,
                        "parameters": action_parameters,
                        "require": action_require,
                        "associated_types": associated_types,
                        "focus_activation_type": focus_activation_type,
                        "normal_activation_type": normal_activation_type,
                        "random_probability": random_probability,
                        "llm_judge_prompt": llm_judge_prompt,
                        "activation_keywords": activation_keywords,
                        "keyword_case_sensitive": keyword_case_sensitive,
                        "mode_enable": mode_enable,
                        "parallel_action": parallel_action,
                    }

                    # 添加到所有已注册的动作
                    self._registered_actions[action_name] = action_info

                    # 添加到默认动作（如果启用插件）
                    if is_enabled:
                        self._default_actions[action_name] = action_info

            # logger.info(f"所有注册动作: {list(self._registered_actions.keys())}")
            # logger.info(f"默认动作: {list(self._default_actions.keys())}")
            # for action_name, action_info in self._default_actions.items():
            # logger.info(f"动作名称: {action_name}, 动作信息: {action_info}")

        except Exception as e:
            logger.error(f"加载已注册动作失败: {e}")

    def _load_plugin_actions(self) -> None:
        """
        加载所有插件目录中的动作

        注意：插件动作的实际导入已经在main.py中完成，这里只需要从action_registry获取
        同时也从新插件系统的component_registry获取Action组件
        """
        try:
            # 从旧的action_registry获取插件动作
            self._load_registered_actions()
            logger.debug("从旧注册表加载插件动作成功")

            # 从新插件系统获取Action组件
            self._load_plugin_system_actions()
            logger.debug("从新插件系统加载Action组件成功")

        except Exception as e:
            logger.error(f"加载插件动作失败: {e}")

    def _load_plugin_system_actions(self) -> None:
        """从新插件系统的component_registry加载Action组件"""
        try:
            from src.plugin_system.core.component_registry import component_registry
            from src.plugin_system.base.component_types import ComponentType

            # 获取所有Action组件
            action_components = component_registry.get_components_by_type(ComponentType.ACTION)

            for action_name, action_info in action_components.items():
                if action_name in self._registered_actions:
                    logger.debug(f"Action组件 {action_name} 已存在，跳过")
                    continue

                # 将新插件系统的ActionInfo转换为旧系统格式
                converted_action_info = {
                    "description": action_info.description,
                    "parameters": getattr(action_info, "action_parameters", {}),
                    "require": getattr(action_info, "action_require", []),
                    "associated_types": getattr(action_info, "associated_types", []),
                    "enable_plugin": action_info.enabled,
                    # 激活类型相关
                    "focus_activation_type": action_info.focus_activation_type.value,
                    "normal_activation_type": action_info.normal_activation_type.value,
                    "random_activation_probability": action_info.random_activation_probability,
                    "llm_judge_prompt": action_info.llm_judge_prompt,
                    "activation_keywords": action_info.activation_keywords,
                    "keyword_case_sensitive": action_info.keyword_case_sensitive,
                    # 模式和并行设置
                    "mode_enable": action_info.mode_enable.value,
                    "parallel_action": action_info.parallel_action,
                    # 标记这是来自新插件系统的组件
                    "_plugin_system_component": True,
                    "_plugin_name": getattr(action_info, "plugin_name", ""),
                }

                self._registered_actions[action_name] = converted_action_info

                # 如果启用，也添加到默认动作集
                if action_info.enabled:
                    self._default_actions[action_name] = converted_action_info

                logger.debug(
                    f"从插件系统加载Action组件: {action_name} (插件: {getattr(action_info, 'plugin_name', 'unknown')})"
                )

            logger.info(f"从新插件系统加载了 {len(action_components)} 个Action组件")

        except Exception as e:
            logger.error(f"从插件系统加载Action组件失败: {e}")
            import traceback

            logger.error(traceback.format_exc())

    def create_action(
        self,
        action_name: str,
        action_data: dict,
        reasoning: str,
        cycle_timers: dict,
        thinking_id: str,
        observations: List[Observation],
        chat_stream: ChatStream,
        log_prefix: str,
        shutting_down: bool = False,
        expressor: DefaultExpressor = None,
        replyer: DefaultReplyer = None,
    ) -> Optional[BaseAction]:
        """
        创建动作处理器实例

        Args:
            action_name: 动作名称
            action_data: 动作数据
            reasoning: 执行理由
            cycle_timers: 计时器字典
            thinking_id: 思考ID
            observations: 观察列表
            expressor: 表达器
            replyer: 回复器
            chat_stream: 聊天流
            log_prefix: 日志前缀
            shutting_down: 是否正在关闭

        Returns:
            Optional[BaseAction]: 创建的动作处理器实例，如果动作名称未注册则返回None
        """
        # 检查动作是否在当前使用的动作集中
        # if action_name not in self._using_actions:
        # logger.warning(f"当前不可用的动作类型: {action_name}")
        # return None

        # 检查是否是新插件系统的Action组件
        action_info = self._registered_actions.get(action_name)
        if action_info and action_info.get("_plugin_system_component", False):
            return self._create_plugin_system_action(
                action_name,
                action_data,
                reasoning,
                cycle_timers,
                thinking_id,
                observations,
                chat_stream,
                log_prefix,
                shutting_down,
                expressor,
                replyer,
            )

        # 旧系统的动作创建逻辑
        from src.plugin_system.core.component_registry import component_registry

        action_registry = component_registry.get_action_registry()
        handler_class = action_registry.get(action_name)
        if not handler_class:
            logger.warning(f"未注册的动作类型: {action_name}")
            return None

        try:
            # 创建动作实例
            instance = handler_class(
                action_data=action_data,
                reasoning=reasoning,
                cycle_timers=cycle_timers,
                thinking_id=thinking_id,
                observations=observations,
                expressor=expressor,
                replyer=replyer,
                chat_stream=chat_stream,
                log_prefix=log_prefix,
                shutting_down=shutting_down,
            )

            return instance

        except Exception as e:
            logger.error(f"创建动作处理器实例失败: {e}")
            return None

    def _create_plugin_system_action(
        self,
        action_name: str,
        action_data: dict,
        reasoning: str,
        cycle_timers: dict,
        thinking_id: str,
        observations: List[Observation],
        chat_stream: ChatStream,
        log_prefix: str,
        shutting_down: bool = False,
        expressor: DefaultExpressor = None,
        replyer: DefaultReplyer = None,
    ) -> Optional["PluginActionWrapper"]:
        """
        创建新插件系统的Action组件实例，并包装为兼容旧系统的接口

        Returns:
            Optional[PluginActionWrapper]: 包装后的Action实例
        """
        try:
            from src.plugin_system.core.component_registry import component_registry

            # 获取组件类
            component_class = component_registry.get_component_class(action_name)
            if not component_class:
                logger.error(f"未找到插件Action组件类: {action_name}")
                return None

            # 获取插件配置
            component_info = component_registry.get_component_info(action_name)
            plugin_config = None
            if component_info and component_info.plugin_name:
                plugin_config = component_registry.get_plugin_config(component_info.plugin_name)

            # 创建插件Action实例
            plugin_action_instance = component_class(
                action_data=action_data,
                reasoning=reasoning,
                cycle_timers=cycle_timers,
                thinking_id=thinking_id,
                chat_stream=chat_stream,
                expressor=expressor,
                replyer=replyer,
                observations=observations,
                log_prefix=log_prefix,
                plugin_config=plugin_config,
            )

            # 创建兼容性包装器
            wrapper = PluginActionWrapper(
                plugin_action=plugin_action_instance,
                action_name=action_name,
                action_data=action_data,
                reasoning=reasoning,
                cycle_timers=cycle_timers,
                thinking_id=thinking_id,
            )

            logger.debug(f"创建插件Action实例成功: {action_name}")
            return wrapper

        except Exception as e:
            logger.error(f"创建插件Action实例失败 {action_name}: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return None

    def get_registered_actions(self) -> Dict[str, ActionInfo]:
        """获取所有已注册的动作集"""
        return self._registered_actions.copy()

    def get_default_actions(self) -> Dict[str, ActionInfo]:
        """获取默认动作集"""
        return self._default_actions.copy()

    def get_using_actions(self) -> Dict[str, ActionInfo]:
        """获取当前正在使用的动作集合"""
        return self._using_actions.copy()

    def get_using_actions_for_mode(self, mode: str) -> Dict[str, ActionInfo]:
        """
        根据聊天模式获取可用的动作集合

        Args:
            mode: 聊天模式 ("focus", "normal", "all")

        Returns:
            Dict[str, ActionInfo]: 在指定模式下可用的动作集合
        """
        filtered_actions = {}

        for action_name, action_info in self._using_actions.items():
            action_mode = action_info.get("mode_enable", "all")

            # 检查动作是否在当前模式下启用
            if action_mode == "all" or action_mode == mode:
                filtered_actions[action_name] = action_info
                logger.debug(f"动作 {action_name} 在模式 {mode} 下可用 (mode_enable: {action_mode})")
            else:
                logger.debug(f"动作 {action_name} 在模式 {mode} 下不可用 (mode_enable: {action_mode})")

        logger.debug(f"模式 {mode} 下可用动作: {list(filtered_actions.keys())}")
        return filtered_actions

    def add_action_to_using(self, action_name: str) -> bool:
        """
        添加已注册的动作到当前使用的动作集

        Args:
            action_name: 动作名称

        Returns:
            bool: 添加是否成功
        """
        if action_name not in self._registered_actions:
            logger.warning(f"添加失败: 动作 {action_name} 未注册")
            return False

        if action_name in self._using_actions:
            logger.info(f"动作 {action_name} 已经在使用中")
            return True

        self._using_actions[action_name] = self._registered_actions[action_name]
        logger.info(f"添加动作 {action_name} 到使用集")
        return True

    def remove_action_from_using(self, action_name: str) -> bool:
        """
        从当前使用的动作集中移除指定动作

        Args:
            action_name: 动作名称

        Returns:
            bool: 移除是否成功
        """
        if action_name not in self._using_actions:
            logger.warning(f"移除失败: 动作 {action_name} 不在当前使用的动作集中")
            return False

        del self._using_actions[action_name]
        logger.debug(f"已从使用集中移除动作 {action_name}")
        return True

    def add_action(self, action_name: str, description: str, parameters: Dict = None, require: List = None) -> bool:
        """
        添加新的动作到注册集

        Args:
            action_name: 动作名称
            description: 动作描述
            parameters: 动作参数定义，默认为空字典
            require: 动作依赖项，默认为空列表

        Returns:
            bool: 添加是否成功
        """
        if action_name in self._registered_actions:
            return False

        if parameters is None:
            parameters = {}
        if require is None:
            require = []

        action_info = {"description": description, "parameters": parameters, "require": require}

        self._registered_actions[action_name] = action_info
        return True

    def remove_action(self, action_name: str) -> bool:
        """从注册集移除指定动作"""
        if action_name not in self._registered_actions:
            return False
        del self._registered_actions[action_name]
        # 如果在使用集中也存在，一并移除
        if action_name in self._using_actions:
            del self._using_actions[action_name]
        return True

    def temporarily_remove_actions(self, actions_to_remove: List[str]) -> None:
        """临时移除使用集中的指定动作"""
        for name in actions_to_remove:
            self._using_actions.pop(name, None)

    def restore_actions(self) -> None:
        """恢复到默认动作集"""
        logger.debug(
            f"恢复动作集: 从 {list(self._using_actions.keys())} 恢复到默认动作集 {list(self._default_actions.keys())}"
        )
        self._using_actions = self._default_actions.copy()

    def restore_default_actions(self) -> None:
        """恢复默认动作集到使用集"""
        self._using_actions = self._default_actions.copy()
        # 添加系统核心动作（即使enable_plugin为False的系统动作）
        self._add_system_core_actions()

    def _add_system_core_actions(self) -> None:
        """
        添加系统核心动作到使用集
        系统核心动作是那些enable_plugin为False但是系统必需的动作
        """
        system_core_actions = ["exit_focus_chat"]  # 可以根据需要扩展

        for action_name in system_core_actions:
            if action_name in self._registered_actions and action_name not in self._using_actions:
                self._using_actions[action_name] = self._registered_actions[action_name]
                logger.debug(f"添加系统核心动作到使用集: {action_name}")

    def add_system_action_if_needed(self, action_name: str) -> bool:
        """
        根据需要添加系统动作到使用集

        Args:
            action_name: 动作名称

        Returns:
            bool: 是否成功添加
        """
        if action_name in self._registered_actions and action_name not in self._using_actions:
            self._using_actions[action_name] = self._registered_actions[action_name]
            logger.info(f"临时添加系统动作到使用集: {action_name}")
            return True
        return False

    def get_action(self, action_name: str) -> Optional[Type[BaseAction]]:
        """
        获取指定动作的处理器类

        Args:
            action_name: 动作名称

        Returns:
            Optional[Type[BaseAction]]: 动作处理器类，如果不存在则返回None
        """
        from src.plugin_system.core.component_registry import component_registry

        action_registry = component_registry.get_action_registry()
        return action_registry.get(action_name)
