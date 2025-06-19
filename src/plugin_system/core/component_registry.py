from typing import Dict, List, Type, Optional, Any, Pattern
import re
from src.common.logger import get_logger
from src.plugin_system.base.component_types import (
    ComponentInfo,
    ActionInfo,
    CommandInfo,
    PluginInfo,
    ComponentType,
)

logger = get_logger("component_registry")


class ComponentRegistry:
    """统一的组件注册中心

    负责管理所有插件组件的注册、查询和生命周期管理
    """

    def __init__(self):
        # 组件注册表
        self._components: Dict[str, ComponentInfo] = {}  # 组件名 -> 组件信息
        self._components_by_type: Dict[ComponentType, Dict[str, ComponentInfo]] = {
            ComponentType.ACTION: {},
            ComponentType.COMMAND: {},
        }
        self._component_classes: Dict[str, Type] = {}  # 组件名 -> 组件类

        # 插件注册表
        self._plugins: Dict[str, PluginInfo] = {}  # 插件名 -> 插件信息

        # Action特定注册表
        self._action_registry: Dict[str, Type] = {}  # action名 -> action类
        self._default_actions: Dict[str, str] = {}  # 启用的action名 -> 描述

        # Command特定注册表
        self._command_registry: Dict[str, Type] = {}  # command名 -> command类
        self._command_patterns: Dict[Pattern, Type] = {}  # 编译后的正则 -> command类

        logger.info("组件注册中心初始化完成")

    # === 通用组件注册方法 ===

    def register_component(self, component_info: ComponentInfo, component_class: Type) -> bool:
        """注册组件

        Args:
            component_info: 组件信息
            component_class: 组件类

        Returns:
            bool: 是否注册成功
        """
        component_name = component_info.name
        component_type = component_info.component_type
        plugin_name = getattr(component_info, 'plugin_name', 'unknown')

        # 🔥 系统级别自动区分：为不同类型的组件添加命名空间前缀
        if component_type == ComponentType.ACTION:
            namespaced_name = f"action.{component_name}"
        elif component_type == ComponentType.COMMAND:
            namespaced_name = f"command.{component_name}"
        else:
            # 未来扩展的组件类型
            namespaced_name = f"{component_type.value}.{component_name}"

        # 检查命名空间化的名称是否冲突
        if namespaced_name in self._components:
            existing_info = self._components[namespaced_name]
            existing_plugin = getattr(existing_info, 'plugin_name', 'unknown')
            
            logger.warning(
                f"组件冲突: {component_type.value}组件 '{component_name}' "
                f"已被插件 '{existing_plugin}' 注册，跳过插件 '{plugin_name}' 的注册"
            )
            return False

        # 注册到通用注册表（使用命名空间化的名称）
        self._components[namespaced_name] = component_info
        self._components_by_type[component_type][component_name] = component_info  # 类型内部仍使用原名
        self._component_classes[namespaced_name] = component_class

        # 根据组件类型进行特定注册（使用原始名称）
        if component_type == ComponentType.ACTION:
            self._register_action_component(component_info, component_class)
        elif component_type == ComponentType.COMMAND:
            self._register_command_component(component_info, component_class)

        logger.debug(
            f"已注册{component_type.value}组件: '{component_name}' -> '{namespaced_name}' "
            f"({component_class.__name__}) [插件: {plugin_name}]"
        )
        return True

    def _register_action_component(self, action_info: ActionInfo, action_class: Type):
        """注册Action组件到Action特定注册表"""
        action_name = action_info.name
        self._action_registry[action_name] = action_class

        # 如果启用，添加到默认动作集
        if action_info.enabled:
            self._default_actions[action_name] = action_info.description

    def _register_command_component(self, command_info: CommandInfo, command_class: Type):
        """注册Command组件到Command特定注册表"""
        command_name = command_info.name
        self._command_registry[command_name] = command_class

        # 编译正则表达式并注册
        if command_info.command_pattern:
            pattern = re.compile(command_info.command_pattern, re.IGNORECASE | re.DOTALL)
            self._command_patterns[pattern] = command_class

    # === 组件查询方法 ===

    def get_component_info(self, component_name: str, component_type: ComponentType = None) -> Optional[ComponentInfo]:
        """获取组件信息，支持自动命名空间解析
        
        Args:
            component_name: 组件名称，可以是原始名称或命名空间化的名称
            component_type: 组件类型，如果提供则优先在该类型中查找
            
        Returns:
            Optional[ComponentInfo]: 组件信息或None
        """
        # 1. 如果已经是命名空间化的名称，直接查找
        if '.' in component_name:
            return self._components.get(component_name)
        
        # 2. 如果指定了组件类型，构造命名空间化的名称查找
        if component_type:
            if component_type == ComponentType.ACTION:
                namespaced_name = f"action.{component_name}"
            elif component_type == ComponentType.COMMAND:
                namespaced_name = f"command.{component_name}"
            else:
                namespaced_name = f"{component_type.value}.{component_name}"
            
            return self._components.get(namespaced_name)
        
        # 3. 如果没有指定类型，尝试在所有命名空间中查找
        candidates = []
        for namespace_prefix in ["action", "command"]:
            namespaced_name = f"{namespace_prefix}.{component_name}"
            component_info = self._components.get(namespaced_name)
            if component_info:
                candidates.append((namespace_prefix, namespaced_name, component_info))
        
        if len(candidates) == 1:
            # 只有一个匹配，直接返回
            return candidates[0][2]
        elif len(candidates) > 1:
            # 多个匹配，记录警告并返回第一个
            namespaces = [ns for ns, _, _ in candidates]
            logger.warning(
                f"组件名称 '{component_name}' 在多个命名空间中存在: {namespaces}，"
                f"使用第一个匹配项: {candidates[0][1]}"
            )
            return candidates[0][2]
        
        # 4. 都没找到
        return None

    def get_component_class(self, component_name: str, component_type: ComponentType = None) -> Optional[Type]:
        """获取组件类，支持自动命名空间解析
        
        Args:
            component_name: 组件名称，可以是原始名称或命名空间化的名称
            component_type: 组件类型，如果提供则优先在该类型中查找
            
        Returns:
            Optional[Type]: 组件类或None
        """
        # 1. 如果已经是命名空间化的名称，直接查找
        if '.' in component_name:
            return self._component_classes.get(component_name)
        
        # 2. 如果指定了组件类型，构造命名空间化的名称查找
        if component_type:
            if component_type == ComponentType.ACTION:
                namespaced_name = f"action.{component_name}"
            elif component_type == ComponentType.COMMAND:
                namespaced_name = f"command.{component_name}"
            else:
                namespaced_name = f"{component_type.value}.{component_name}"
            
            return self._component_classes.get(namespaced_name)
        
        # 3. 如果没有指定类型，尝试在所有命名空间中查找
        candidates = []
        for namespace_prefix in ["action", "command"]:
            namespaced_name = f"{namespace_prefix}.{component_name}"
            component_class = self._component_classes.get(namespaced_name)
            if component_class:
                candidates.append((namespace_prefix, namespaced_name, component_class))
        
        if len(candidates) == 1:
            # 只有一个匹配，直接返回
            namespace, full_name, cls = candidates[0]
            logger.debug(f"自动解析组件: '{component_name}' -> '{full_name}'")
            return cls
        elif len(candidates) > 1:
            # 多个匹配，记录警告并返回第一个
            namespaces = [ns for ns, _, _ in candidates]
            logger.warning(
                f"组件名称 '{component_name}' 在多个命名空间中存在: {namespaces}，"
                f"使用第一个匹配项: {candidates[0][1]}"
            )
            return candidates[0][2]
        
        # 4. 都没找到
        return None

    def get_components_by_type(self, component_type: ComponentType) -> Dict[str, ComponentInfo]:
        """获取指定类型的所有组件"""
        return self._components_by_type.get(component_type, {}).copy()

    def get_enabled_components_by_type(self, component_type: ComponentType) -> Dict[str, ComponentInfo]:
        """获取指定类型的所有启用组件"""
        components = self.get_components_by_type(component_type)
        return {name: info for name, info in components.items() if info.enabled}

    # === Action特定查询方法 ===

    def get_action_registry(self) -> Dict[str, Type]:
        """获取Action注册表（用于兼容现有系统）"""
        return self._action_registry.copy()

    def get_default_actions(self) -> Dict[str, str]:
        """获取默认启用的Action列表（用于兼容现有系统）"""
        return self._default_actions.copy()

    def get_action_info(self, action_name: str) -> Optional[ActionInfo]:
        """获取Action信息"""
        info = self.get_component_info(action_name, ComponentType.ACTION)
        return info if isinstance(info, ActionInfo) else None

    # === Command特定查询方法 ===

    def get_command_registry(self) -> Dict[str, Type]:
        """获取Command注册表（用于兼容现有系统）"""
        return self._command_registry.copy()

    def get_command_patterns(self) -> Dict[Pattern, Type]:
        """获取Command模式注册表（用于兼容现有系统）"""
        return self._command_patterns.copy()

    def get_command_info(self, command_name: str) -> Optional[CommandInfo]:
        """获取Command信息"""
        info = self.get_component_info(command_name, ComponentType.COMMAND)
        return info if isinstance(info, CommandInfo) else None

    def find_command_by_text(self, text: str) -> Optional[tuple[Type, dict, bool, str]]:
        """根据文本查找匹配的命令

        Args:
            text: 输入文本

        Returns:
            Optional[tuple[Type, dict, bool, str]]: (命令类, 匹配的命名组, 是否拦截消息, 插件名) 或 None
        """

        for pattern, command_class in self._command_patterns.items():
            
            match = pattern.match(text)
            if match:
                command_name = None
                # 查找对应的组件信息
                for name, cls in self._command_registry.items():
                    if cls == command_class:
                        command_name = name
                        break
                
                # 检查命令是否启用
                if command_name:
                    command_info = self.get_command_info(command_name)
                    if command_info:
                        if command_info.enabled:
                            return (
                                command_class,
                                match.groupdict(),
                                command_info.intercept_message,
                                command_info.plugin_name,
                            )
        return None

    # === 插件管理方法 ===

    def register_plugin(self, plugin_info: PluginInfo) -> bool:
        """注册插件

        Args:
            plugin_info: 插件信息

        Returns:
            bool: 是否注册成功
        """
        plugin_name = plugin_info.name

        if plugin_name in self._plugins:
            logger.warning(f"插件 {plugin_name} 已存在，跳过注册")
            return False

        self._plugins[plugin_name] = plugin_info
        logger.debug(f"已注册插件: {plugin_name} (组件数量: {len(plugin_info.components)})")
        return True

    def get_plugin_info(self, plugin_name: str) -> Optional[PluginInfo]:
        """获取插件信息"""
        return self._plugins.get(plugin_name)

    def get_all_plugins(self) -> Dict[str, PluginInfo]:
        """获取所有插件"""
        return self._plugins.copy()

    def get_enabled_plugins(self) -> Dict[str, PluginInfo]:
        """获取所有启用的插件"""
        return {name: info for name, info in self._plugins.items() if info.enabled}

    def get_plugin_components(self, plugin_name: str) -> List[ComponentInfo]:
        """获取插件的所有组件"""
        plugin_info = self.get_plugin_info(plugin_name)
        return plugin_info.components if plugin_info else []

    def get_plugin_config(self, plugin_name: str) -> Optional[dict]:
        """获取插件配置

        Args:
            plugin_name: 插件名称

        Returns:
            Optional[dict]: 插件配置字典或None
        """
        # 从插件管理器获取插件实例的配置
        from src.plugin_system.core.plugin_manager import plugin_manager

        plugin_instance = plugin_manager.get_plugin_instance(plugin_name)
        return plugin_instance.config if plugin_instance else None

    # === 状态管理方法 ===

    def enable_component(self, component_name: str, component_type: ComponentType = None) -> bool:
        """启用组件，支持命名空间解析"""
        # 首先尝试找到正确的命名空间化名称
        component_info = self.get_component_info(component_name, component_type)
        if not component_info:
            return False
        
        # 根据组件类型构造正确的命名空间化名称
        if component_info.component_type == ComponentType.ACTION:
            namespaced_name = f"action.{component_name}" if '.' not in component_name else component_name
        elif component_info.component_type == ComponentType.COMMAND:
            namespaced_name = f"command.{component_name}" if '.' not in component_name else component_name
        else:
            namespaced_name = f"{component_info.component_type.value}.{component_name}" if '.' not in component_name else component_name
        
        if namespaced_name in self._components:
            self._components[namespaced_name].enabled = True
            # 如果是Action，更新默认动作集
            if isinstance(component_info, ActionInfo):
                self._default_actions[component_name] = component_info.description
            logger.debug(f"已启用组件: {component_name} -> {namespaced_name}")
            return True
        return False

    def disable_component(self, component_name: str, component_type: ComponentType = None) -> bool:
        """禁用组件，支持命名空间解析"""
        # 首先尝试找到正确的命名空间化名称
        component_info = self.get_component_info(component_name, component_type)
        if not component_info:
            return False
        
        # 根据组件类型构造正确的命名空间化名称
        if component_info.component_type == ComponentType.ACTION:
            namespaced_name = f"action.{component_name}" if '.' not in component_name else component_name
        elif component_info.component_type == ComponentType.COMMAND:
            namespaced_name = f"command.{component_name}" if '.' not in component_name else component_name
        else:
            namespaced_name = f"{component_info.component_type.value}.{component_name}" if '.' not in component_name else component_name
        
        if namespaced_name in self._components:
            self._components[namespaced_name].enabled = False
            # 如果是Action，从默认动作集中移除
            if component_name in self._default_actions:
                del self._default_actions[component_name]
            logger.debug(f"已禁用组件: {component_name} -> {namespaced_name}")
            return True
        return False

    def get_registry_stats(self) -> Dict[str, Any]:
        """获取注册中心统计信息"""
        action_components: int = 0
        command_components: int = 0
        for component in self._components.values():
            if component.component_type == ComponentType.ACTION:
                action_components += 1
            elif component.component_type == ComponentType.COMMAND:
                command_components += 1
        return {
            "action_components": action_components,
            "command_components": command_components,
            "total_components": len(self._components),
            "total_plugins": len(self._plugins),
            "components_by_type": {
                component_type.value: len(components) for component_type, components in self._components_by_type.items()
            },
            "enabled_components": len([c for c in self._components.values() if c.enabled]),
            "enabled_plugins": len([p for p in self._plugins.values() if p.enabled]),
        }


# 全局组件注册中心实例
component_registry = ComponentRegistry()
