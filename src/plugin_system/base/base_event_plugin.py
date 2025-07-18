from abc import abstractmethod
from typing import List, Tuple, Type

from src.common.logger import get_logger
from .plugin_base import PluginBase
from .component_types import EventHandlerInfo
from .base_events_handler import BaseEventHandler

logger = get_logger("base_event_plugin")

class BaseEventPlugin(PluginBase):
    """基于事件的插件基类

    所有事件类型的插件都应该继承这个基类
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    @abstractmethod
    def get_plugin_components(self) -> List[Tuple[EventHandlerInfo, Type[BaseEventHandler]]]:
        """获取插件包含的事件组件

        子类必须实现此方法，返回事件组件

        Returns:
            List[Tuple[ComponentInfo, Type]]: [(组件信息, 组件类), ...]
        """
        raise NotImplementedError("子类必须实现 get_plugin_components 方法")

    def register_plugin(self) -> bool:
        """注册事件插件"""
        from src.plugin_system.core.events_manager import events_manager
        
        components = self.get_plugin_components()
        
        # 检查依赖
        if not self._check_dependencies():
            logger.error(f"{self.log_prefix} 依赖检查失败，跳过注册")
            return False
    
        registered_components = []
        for handler_info, handler_class in components:
            handler_info.plugin_name = self.plugin_name
            if events_manager.register_event_subscriber(handler_info, handler_class):
                registered_components.append(handler_info)
            else:
                logger.error(f"{self.log_prefix} 事件处理器 {handler_info.name} 注册失败")

        self.plugin_info.components = registered_components
        
        if events_manager.register_plugins(self.plugin_info):
            logger.debug(f"{self.log_prefix} 插件注册成功，包含 {len(registered_components)} 个事件处理器")
            return True
        else:
            logger.error(f"{self.log_prefix} 插件注册失败")
            return False