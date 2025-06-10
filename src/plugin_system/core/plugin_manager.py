from typing import Dict, List, Optional, Any
import os
import importlib
import importlib.util
from pathlib import Path
from src.common.logger_manager import get_logger
from src.plugin_system.core.component_registry import component_registry
from src.plugin_system.base.component_types import PluginInfo, ComponentType

logger = get_logger("plugin_manager")

class PluginManager:
    """插件管理器
    
    负责加载、初始化和管理所有插件及其组件
    """
    
    def __init__(self):
        self.plugin_directories: List[str] = []
        self.loaded_plugins: Dict[str, Any] = {}
        self.failed_plugins: Dict[str, str] = {}
        
        logger.info("插件管理器初始化完成")
    
    def add_plugin_directory(self, directory: str):
        """添加插件目录"""
        if os.path.exists(directory):
            self.plugin_directories.append(directory)
            logger.info(f"已添加插件目录: {directory}")
        else:
            logger.warning(f"插件目录不存在: {directory}")
    
    def load_all_plugins(self) -> tuple[int, int]:
        """加载所有插件目录中的插件
        
        Returns:
            tuple[int, int]: (插件数量, 组件数量)
        """
        logger.info("开始加载所有插件...")
        
        # 第一阶段：加载所有插件模块（注册插件类）
        total_loaded_modules = 0
        total_failed_modules = 0
        
        for directory in self.plugin_directories:
            loaded, failed = self._load_plugin_modules_from_directory(directory)
            total_loaded_modules += loaded
            total_failed_modules += failed
        
        logger.info(f"插件模块加载完成 - 成功: {total_loaded_modules}, 失败: {total_failed_modules}")
        
        # 第二阶段：实例化所有已注册的插件类
        from src.plugin_system.base.base_plugin import get_registered_plugin_classes, instantiate_and_register_plugin
        
        plugin_classes = get_registered_plugin_classes()
        total_registered = 0
        total_failed_registration = 0
        
        for plugin_name, plugin_class in plugin_classes.items():
            # 尝试找到插件对应的目录
            plugin_dir = self._find_plugin_directory(plugin_class)
            
            if instantiate_and_register_plugin(plugin_class, plugin_dir):
                total_registered += 1
                self.loaded_plugins[plugin_name] = plugin_class
            else:
                total_failed_registration += 1
                self.failed_plugins[plugin_name] = "插件注册失败"
        
        logger.info(f"插件注册完成 - 成功: {total_registered}, 失败: {total_failed_registration}")
        
        # 获取组件统计信息
        stats = component_registry.get_registry_stats()
        logger.info(f"组件注册统计: {stats}")
        
        # 返回插件数量和组件数量
        return total_registered, stats.get('total_components', 0)
    
    def _find_plugin_directory(self, plugin_class) -> Optional[str]:
        """查找插件类对应的目录路径"""
        try:
            import inspect
            module = inspect.getmodule(plugin_class)
            if module and hasattr(module, '__file__') and module.__file__:
                return os.path.dirname(module.__file__)
        except Exception:
            pass
        return None
    
    def _load_plugin_modules_from_directory(self, directory: str) -> tuple[int, int]:
        """从指定目录加载插件模块"""
        loaded_count = 0
        failed_count = 0
        
        if not os.path.exists(directory):
            logger.warning(f"插件目录不存在: {directory}")
            return loaded_count, failed_count
        
        logger.info(f"正在扫描插件目录: {directory}")
        
        # 遍历目录中的所有Python文件和包
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            
            if os.path.isfile(item_path) and item.endswith('.py') and item != '__init__.py':
                # 单文件插件
                if self._load_plugin_module_file(item_path):
                    loaded_count += 1
                else:
                    failed_count += 1
            
            elif os.path.isdir(item_path) and not item.startswith('.') and not item.startswith('__'):
                # 插件包
                plugin_file = os.path.join(item_path, 'plugin.py')
                if os.path.exists(plugin_file):
                    if self._load_plugin_module_file(plugin_file):
                        loaded_count += 1
                    else:
                        failed_count += 1
        
        return loaded_count, failed_count
    
    def _load_plugin_module_file(self, plugin_file: str) -> bool:
        """加载单个插件模块文件"""
        plugin_name = None
        
        # 生成模块名
        plugin_path = Path(plugin_file)
        if plugin_path.parent.name != 'plugins':
            # 插件包格式：parent_dir.plugin
            module_name = f"plugins.{plugin_path.parent.name}.plugin"
        else:
            # 单文件格式：plugins.filename
            module_name = f"plugins.{plugin_path.stem}"
        
        try:
            # 动态导入插件模块
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if spec is None or spec.loader is None:
                logger.error(f"无法创建模块规范: {plugin_file}")
                return False
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 模块加载成功，插件类会自动通过装饰器注册
            plugin_name = plugin_path.parent.name if plugin_path.parent.name != 'plugins' else plugin_path.stem
            
            logger.debug(f"插件模块加载成功: {plugin_file}")
            return True
            
        except Exception as e:
            error_msg = f"加载插件模块 {plugin_file} 失败: {e}"
            logger.error(error_msg)
            if plugin_name:
                self.failed_plugins[plugin_name] = error_msg
            return False
    
    def get_loaded_plugins(self) -> List[PluginInfo]:
        """获取所有已加载的插件信息"""
        return list(component_registry.get_all_plugins().values())
    
    def get_enabled_plugins(self) -> List[PluginInfo]:
        """获取所有启用的插件信息"""
        return list(component_registry.get_enabled_plugins().values())
    
    def enable_plugin(self, plugin_name: str) -> bool:
        """启用插件"""
        plugin_info = component_registry.get_plugin_info(plugin_name)
        if plugin_info:
            plugin_info.enabled = True
            # 启用插件的所有组件
            for component in plugin_info.components:
                component_registry.enable_component(component.name)
            logger.info(f"已启用插件: {plugin_name}")
            return True
        return False
    
    def disable_plugin(self, plugin_name: str) -> bool:
        """禁用插件"""
        plugin_info = component_registry.get_plugin_info(plugin_name)
        if plugin_info:
            plugin_info.enabled = False
            # 禁用插件的所有组件
            for component in plugin_info.components:
                component_registry.disable_component(component.name)
            logger.info(f"已禁用插件: {plugin_name}")
            return True
        return False
    
    def get_plugin_stats(self) -> Dict[str, Any]:
        """获取插件统计信息"""
        all_plugins = component_registry.get_all_plugins()
        enabled_plugins = component_registry.get_enabled_plugins()
        
        action_components = component_registry.get_components_by_type(ComponentType.ACTION)
        command_components = component_registry.get_components_by_type(ComponentType.COMMAND)
        
        return {
            "total_plugins": len(all_plugins),
            "enabled_plugins": len(enabled_plugins),
            "failed_plugins": len(self.failed_plugins),
            "total_components": len(action_components) + len(command_components),
            "action_components": len(action_components),
            "command_components": len(command_components),
            "loaded_plugin_files": len(self.loaded_plugins),
            "failed_plugin_details": self.failed_plugins.copy()
        }
    
    def reload_plugin(self, plugin_name: str) -> bool:
        """重新加载插件（高级功能，需要谨慎使用）"""
        # TODO: 实现插件热重载功能
        logger.warning("插件热重载功能尚未实现")
        return False


# 全局插件管理器实例
plugin_manager = PluginManager()

# 默认插件目录
plugin_manager.add_plugin_directory("src/plugins/built_in")
plugin_manager.add_plugin_directory("src/plugins/examples") 
plugin_manager.add_plugin_directory("plugins")  # 用户插件目录 