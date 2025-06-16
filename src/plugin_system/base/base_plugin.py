from abc import ABC, abstractmethod
from typing import Dict, List, Type, Optional, Any, Union
import os
import inspect
import toml
from src.common.logger import get_logger
from src.plugin_system.base.component_types import (
    PluginInfo,
    ComponentInfo,
    PythonDependency,
)
from src.plugin_system.base.config_types import ConfigField
from src.plugin_system.core.component_registry import component_registry

logger = get_logger("base_plugin")

# 全局插件类注册表
_plugin_classes: Dict[str, Type["BasePlugin"]] = {}


class BasePlugin(ABC):
    """插件基类

    所有插件都应该继承这个基类，一个插件可以包含多种组件：
    - Action组件：处理聊天中的动作
    - Command组件：处理命令请求
    - 未来可扩展：Scheduler、Listener等
    """

    # 插件基本信息（子类必须定义）
    plugin_name: str = ""  # 插件名称
    plugin_description: str = ""  # 插件描述
    plugin_version: str = "1.0.0"  # 插件版本
    plugin_author: str = ""  # 插件作者
    enable_plugin: bool = False  # 是否启用插件
    dependencies: List[str] = []  # 依赖的其他插件
    python_dependencies: List[PythonDependency] = []  # Python包依赖
    config_file_name: Optional[str] = None  # 配置文件名

    # 新增：配置定义
    config_schema: Dict[str, Union[Dict[str, ConfigField], str]] = {}
    config_section_descriptions: Dict[str, str] = {}

    def __init__(self, plugin_dir: str = None):
        """初始化插件

        Args:
            plugin_dir: 插件目录路径，由插件管理器传递
        """
        self.config: Dict[str, Any] = {}  # 插件配置
        self.plugin_dir = plugin_dir  # 插件目录路径
        self.log_prefix = f"[Plugin:{self.plugin_name}]"

        # 验证插件信息
        self._validate_plugin_info()

        # 加载插件配置
        self._load_plugin_config()

        # 创建插件信息对象
        self.plugin_info = PluginInfo(
            name=self.plugin_name,
            description=self.plugin_description,
            version=self.plugin_version,
            author=self.plugin_author,
            enabled=self.enable_plugin,
            is_built_in=False,
            config_file=self.config_file_name or "",
            dependencies=self.dependencies.copy(),
            python_dependencies=self.python_dependencies.copy(),
        )

        logger.debug(f"{self.log_prefix} 插件基类初始化完成")

    def _validate_plugin_info(self):
        """验证插件基本信息"""
        if not self.plugin_name:
            raise ValueError(f"插件类 {self.__class__.__name__} 必须定义 plugin_name")
        if not self.plugin_description:
            raise ValueError(f"插件 {self.plugin_name} 必须定义 plugin_description")

    def _generate_and_save_default_config(self, config_file_path: str):
        """根据插件的Schema生成并保存默认配置文件"""
        if not self.config_schema:
            logger.debug(f"{self.log_prefix} 插件未定义config_schema，不生成配置文件")
            return

        toml_str = f"# {self.plugin_name} - 自动生成的配置文件\n"
        toml_str += f"# {self.plugin_description}\n\n"

        # 遍历每个配置节
        for section, fields in self.config_schema.items():
            # 添加节描述
            if section in self.config_section_descriptions:
                toml_str += f"# {self.config_section_descriptions[section]}\n"

            toml_str += f"[{section}]\n\n"

            # 遍历节内的字段
            if isinstance(fields, dict):
                for field_name, field in fields.items():
                    if isinstance(field, ConfigField):
                        # 添加字段描述
                        toml_str += f"# {field.description}"
                        if field.required:
                            toml_str += " (必需)"
                        toml_str += "\n"

                        # 如果有示例值，添加示例
                        if field.example:
                            toml_str += f"# 示例: {field.example}\n"

                        # 如果有可选值，添加说明
                        if field.choices:
                            choices_str = ", ".join(map(str, field.choices))
                            toml_str += f"# 可选值: {choices_str}\n"

                        # 添加字段值
                        value = field.default
                        if isinstance(value, str):
                            toml_str += f'{field_name} = "{value}"\n'
                        elif isinstance(value, bool):
                            toml_str += f"{field_name} = {str(value).lower()}\n"
                        else:
                            toml_str += f"{field_name} = {value}\n"

                        toml_str += "\n"
            toml_str += "\n"

        try:
            with open(config_file_path, "w", encoding="utf-8") as f:
                f.write(toml_str)
            logger.info(f"{self.log_prefix} 已生成默认配置文件: {config_file_path}")
        except IOError as e:
            logger.error(f"{self.log_prefix} 保存默认配置文件失败: {e}", exc_info=True)

    def _load_plugin_config(self):
        """加载插件配置文件"""
        if not self.config_file_name:
            logger.debug(f"{self.log_prefix} 未指定配置文件，跳过加载")
            return

        # 优先使用传入的插件目录路径
        if self.plugin_dir:
            plugin_dir = self.plugin_dir
        else:
            # fallback：尝试从类的模块信息获取路径
            try:
                plugin_module_path = inspect.getfile(self.__class__)
                plugin_dir = os.path.dirname(plugin_module_path)
            except (TypeError, OSError):
                # 最后的fallback：从模块的__file__属性获取
                module = inspect.getmodule(self.__class__)
                if module and hasattr(module, "__file__") and module.__file__:
                    plugin_dir = os.path.dirname(module.__file__)
                else:
                    logger.warning(f"{self.log_prefix} 无法获取插件目录路径，跳过配置加载")
                    return

        config_file_path = os.path.join(plugin_dir, self.config_file_name)

        if not os.path.exists(config_file_path):
            logger.info(f"{self.log_prefix} 配置文件 {config_file_path} 不存在，将生成默认配置。")
            self._generate_and_save_default_config(config_file_path)

        if not os.path.exists(config_file_path):
            logger.warning(f"{self.log_prefix} 配置文件 {config_file_path} 不存在且无法生成。")
            return

        file_ext = os.path.splitext(self.config_file_name)[1].lower()

        if file_ext == ".toml":
            with open(config_file_path, "r", encoding="utf-8") as f:
                self.config = toml.load(f) or {}
            logger.debug(f"{self.log_prefix} 配置已从 {config_file_path} 加载")

            # 从配置中更新 enable_plugin
            if "plugin" in self.config and "enabled" in self.config["plugin"]:
                self.enable_plugin = self.config["plugin"]["enabled"]
                logger.debug(f"{self.log_prefix} 从配置更新插件启用状态: {self.enable_plugin}")
        else:
            logger.warning(f"{self.log_prefix} 不支持的配置文件格式: {file_ext}，仅支持 .toml")
            self.config = {}

    @abstractmethod
    def get_plugin_components(self) -> List[tuple[ComponentInfo, Type]]:
        """获取插件包含的组件列表

        子类必须实现此方法，返回组件信息和组件类的列表

        Returns:
            List[tuple[ComponentInfo, Type]]: [(组件信息, 组件类), ...]
        """
        pass

    def register_plugin(self) -> bool:
        """注册插件及其所有组件"""
        if not self.enable_plugin:
            logger.info(f"{self.log_prefix} 插件已禁用，跳过注册")
            return False

        components = self.get_plugin_components()

        # 检查依赖
        if not self._check_dependencies():
            logger.error(f"{self.log_prefix} 依赖检查失败，跳过注册")
            return False

        # 注册所有组件
        registered_components = []
        for component_info, component_class in components:
            component_info.plugin_name = self.plugin_name
            if component_registry.register_component(component_info, component_class):
                registered_components.append(component_info)
            else:
                logger.warning(f"{self.log_prefix} 组件 {component_info.name} 注册失败")

        # 更新插件信息中的组件列表
        self.plugin_info.components = registered_components

        # 注册插件
        if component_registry.register_plugin(self.plugin_info):
            logger.debug(f"{self.log_prefix} 插件注册成功，包含 {len(registered_components)} 个组件")
            return True
        else:
            logger.error(f"{self.log_prefix} 插件注册失败")
            return False

    def _check_dependencies(self) -> bool:
        """检查插件依赖"""
        if not self.dependencies:
            return True

        for dep in self.dependencies:
            if not component_registry.get_plugin_info(dep):
                logger.error(f"{self.log_prefix} 缺少依赖插件: {dep}")
                return False

        return True

    def get_config(self, key: str, default: Any = None) -> Any:
        """获取插件配置值，支持嵌套键访问

        Args:
            key: 配置键名，支持嵌套访问如 "section.subsection.key"
            default: 默认值

        Returns:
            Any: 配置值或默认值
        """
        # 支持嵌套键访问
        keys = key.split(".")
        current = self.config

        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default

        return current


def register_plugin(cls):
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
    _plugin_classes[plugin_name] = cls
    logger.debug(f"插件类已注册: {plugin_name}")

    return cls


def get_registered_plugin_classes() -> Dict[str, Type["BasePlugin"]]:
    """获取所有已注册的插件类"""
    return _plugin_classes.copy()


def instantiate_and_register_plugin(plugin_class: Type["BasePlugin"], plugin_dir: str = None) -> bool:
    """实例化并注册插件

    Args:
        plugin_class: 插件类
        plugin_dir: 插件目录路径

    Returns:
        bool: 是否成功
    """
    try:
        plugin_instance = plugin_class(plugin_dir=plugin_dir)
        return plugin_instance.register_plugin()
    except Exception as e:
        logger.error(f"注册插件 {plugin_class.__name__} 时出错: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False
