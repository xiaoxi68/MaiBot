from typing import Dict, List, Optional, Type, Any
from src.plugin_system.base.base_action import BaseAction
from src.chat.message_receive.chat_stream import ChatStream
from src.common.logger import get_logger
from src.plugin_system.core.component_registry import component_registry
from src.plugin_system.base.component_types import ComponentType, ActionActivationType, ChatMode, ActionInfo

logger = get_logger("action_manager")

class ActionManager:
    """
    动作管理器，用于管理各种类型的动作

    现在统一使用新插件系统，简化了原有的新旧兼容逻辑。
    """

    # 类常量
    DEFAULT_RANDOM_PROBABILITY = 0.3
    DEFAULT_MODE = ChatMode.ALL
    DEFAULT_ACTIVATION_TYPE = ActionActivationType.ALWAYS

    def __init__(self):
        """初始化动作管理器"""
        # 所有注册的动作集合
        self._registered_actions: Dict[str, ActionInfo] = {}
        # 当前正在使用的动作集合，默认加载默认动作
        self._using_actions: Dict[str, ActionInfo] = {}

        # 默认动作集，仅作为快照，用于恢复默认
        self._default_actions: Dict[str, ActionInfo] = {}

        # 加载插件动作
        self._load_plugin_actions()

        # 初始化时将默认动作加载到使用中的动作
        self._using_actions = self._default_actions.copy()

    def _load_plugin_actions(self) -> None:
        """
        加载所有插件系统中的动作
        """
        try:
            # 从新插件系统获取Action组件
            self._load_plugin_system_actions()
            logger.debug("从插件系统加载Action组件成功")

        except Exception as e:
            logger.error(f"加载插件动作失败: {e}")

    def _load_plugin_system_actions(self) -> None:
        """从插件系统的component_registry加载Action组件"""
        try:
            # 获取所有Action组件
            action_components: Dict[str, ActionInfo] = component_registry.get_components_by_type(ComponentType.ACTION)

            for action_name, action_info in action_components.items():
                if action_name in self._registered_actions:
                    logger.debug(f"Action组件 {action_name} 已存在，跳过")
                    continue

                # 将插件系统的ActionInfo转换为ActionManager格式
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
                    # 插件信息
                    "_plugin_name": getattr(action_info, "plugin_name", ""),
                }

                self._registered_actions[action_name] = converted_action_info

                # 如果启用，也添加到默认动作集
                if action_info.enabled:
                    self._default_actions[action_name] = converted_action_info

                logger.debug(
                    f"从插件系统加载Action组件: {action_name} (插件: {getattr(action_info, 'plugin_name', 'unknown')})"
                )

            logger.info(f"加载了 {len(action_components)} 个Action动作")

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
        chat_stream: ChatStream,
        log_prefix: str,
        shutting_down: bool = False,
    ) -> Optional[BaseAction]:
        """
        创建动作处理器实例

        Args:
            action_name: 动作名称
            action_data: 动作数据
            reasoning: 执行理由
            cycle_timers: 计时器字典
            thinking_id: 思考ID
            chat_stream: 聊天流
            log_prefix: 日志前缀
            shutting_down: 是否正在关闭

        Returns:
            Optional[BaseAction]: 创建的动作处理器实例，如果动作名称未注册则返回None
        """
        try:
            # 获取组件类 - 明确指定查询Action类型
            component_class = component_registry.get_component_class(action_name, ComponentType.ACTION)
            if not component_class:
                logger.warning(f"{log_prefix} 未找到Action组件: {action_name}")
                return None

            # 获取组件信息
            component_info = component_registry.get_component_info(action_name, ComponentType.ACTION)
            if not component_info:
                logger.warning(f"{log_prefix} 未找到Action组件信息: {action_name}")
                return None

            # 获取插件配置
            plugin_config = component_registry.get_plugin_config(component_info.plugin_name)

            # 创建动作实例
            instance = component_class(
                action_data=action_data,
                reasoning=reasoning,
                cycle_timers=cycle_timers,
                thinking_id=thinking_id,
                chat_stream=chat_stream,
                log_prefix=log_prefix,
                shutting_down=shutting_down,
                plugin_config=plugin_config,
            )

            logger.debug(f"创建Action实例成功: {action_name}")
            return instance

        except Exception as e:
            logger.error(f"创建Action实例失败 {action_name}: {e}")
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

    def get_using_actions_for_mode(self, mode: ChatMode) -> Dict[str, ActionInfo]:
        """
        根据聊天模式获取可用的动作集合

        Args:
            mode: 聊天模式 (ChatMode.FOCUS, ChatMode.NORMAL, ChatMode.ALL)

        Returns:
            Dict[str, ActionInfo]: 在指定模式下可用的动作集合
        """
        enabled_actions = {}

        for action_name, action_info in self._using_actions.items():
            action_mode = action_info.mode_enable

            # 检查动作是否在当前模式下启用
            if action_mode in [ChatMode.ALL, mode]:
                enabled_actions[action_name] = action_info
                logger.debug(f"动作 {action_name} 在模式 {mode} 下可用 (mode_enable: {action_mode})")

        logger.debug(f"模式 {mode} 下可用动作: {list(enabled_actions.keys())}")
        return enabled_actions

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

        return component_registry.get_component_class(action_name)
