from src.common.logger import get_logger

logger = get_logger("plugin_register")


def register_plugin(cls):
    from src.plugin_system.core.plugin_manager import plugin_manager
    from src.plugin_system.base.base_plugin import BasePlugin

    """插件注册装饰器

    用法:
        @register_plugin
        class MyPlugin(BasePlugin):
            plugin_name = "my_plugin"
            plugin_description = "我的插件"
            ...
    """
    if not issubclass(cls, BasePlugin):
        logger.error(f"类 {cls.__name__} 不是 BasePlugin 的子类")
        return cls

    # 只是注册插件类，不立即实例化
    # 插件管理器会负责实例化和注册
    plugin_name = cls.plugin_name or cls.__name__
    plugin_manager.plugin_classes[plugin_name] = cls  # type: ignore
    logger.debug(f"插件类已注册: {plugin_name}")

    return cls

def register_event_plugin(cls, *args, **kwargs):
    from src.plugin_system.core.events_manager import events_manager
    from src.plugin_system.base.component_types import EventType

    """事件插件注册装饰器

    用法:
        @register_event_plugin
        class MyEventPlugin:
            event_type = EventType.MESSAGE_RECEIVED
            ...
    """