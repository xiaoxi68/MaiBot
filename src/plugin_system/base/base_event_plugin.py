from abc import abstractmethod

from .plugin_base import PluginBase
from src.common.logger import get_logger


class BaseEventPlugin(PluginBase):
    """基于事件的插件基类

    所有事件类型的插件都应该继承这个基类
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
