from abc import ABC, abstractmethod

class BaseEventsPlugin(ABC):
    """
    事件触发型插件基类
    
    所有事件触发型插件都应该继承这个基类而不是 BasePlugin
    """
    
    @property
    @abstractmethod
    def plugin_name(self) -> str:
        return ""  # 插件内部标识符（如 "hello_world_plugin"）
    
    @property
    @abstractmethod
    def enable_plugin(self) -> bool:
        return False