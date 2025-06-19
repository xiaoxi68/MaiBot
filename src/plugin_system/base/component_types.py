from enum import Enum
from typing import Dict, Any, List
from dataclasses import dataclass


# 组件类型枚举
class ComponentType(Enum):
    """组件类型枚举"""

    ACTION = "action"  # 动作组件
    COMMAND = "command"  # 命令组件
    SCHEDULER = "scheduler"  # 定时任务组件（预留）
    LISTENER = "listener"  # 事件监听组件（预留）


# 动作激活类型枚举
class ActionActivationType(Enum):
    """动作激活类型枚举"""

    NEVER = "never"  # 从不激活（默认关闭）
    ALWAYS = "always"  # 默认参与到planner
    LLM_JUDGE = "llm_judge"  # LLM判定是否启动该action到planner
    RANDOM = "random"  # 随机启用action到planner
    KEYWORD = "keyword"  # 关键词触发启用action到planner


# 聊天模式枚举
class ChatMode(Enum):
    """聊天模式枚举"""

    FOCUS = "focus"  # Focus聊天模式
    NORMAL = "normal"  # Normal聊天模式
    ALL = "all"  # 所有聊天模式


@dataclass
class PythonDependency:
    """Python包依赖信息"""

    package_name: str  # 包名称
    version: str = ""  # 版本要求，例如: ">=1.0.0", "==2.1.3", ""表示任意版本
    optional: bool = False  # 是否为可选依赖
    description: str = ""  # 依赖描述
    install_name: str = ""  # 安装时的包名（如果与import名不同）

    def __post_init__(self):
        if not self.install_name:
            self.install_name = self.package_name

    def get_pip_requirement(self) -> str:
        """获取pip安装格式的依赖字符串"""
        if self.version:
            return f"{self.install_name}{self.version}"
        return self.install_name


@dataclass
class ComponentInfo:
    """组件信息"""

    name: str  # 组件名称
    component_type: ComponentType  # 组件类型
    description: str  # 组件描述
    enabled: bool = True  # 是否启用
    plugin_name: str = ""  # 所属插件名称
    is_built_in: bool = False  # 是否为内置组件
    metadata: Dict[str, Any] = None  # 额外元数据

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ActionInfo(ComponentInfo):
    """动作组件信息"""

    focus_activation_type: ActionActivationType = ActionActivationType.ALWAYS
    normal_activation_type: ActionActivationType = ActionActivationType.ALWAYS
    random_activation_probability: float = 0.3
    llm_judge_prompt: str = ""
    activation_keywords: List[str] = None
    keyword_case_sensitive: bool = False
    mode_enable: ChatMode = ChatMode.ALL
    parallel_action: bool = False
    action_parameters: Dict[str, Any] = None
    action_require: List[str] = None
    associated_types: List[str] = None

    def __post_init__(self):
        super().__post_init__()
        if self.activation_keywords is None:
            self.activation_keywords = []
        if self.action_parameters is None:
            self.action_parameters = {}
        if self.action_require is None:
            self.action_require = []
        if self.associated_types is None:
            self.associated_types = []
        self.component_type = ComponentType.ACTION


@dataclass
class CommandInfo(ComponentInfo):
    """命令组件信息"""

    command_pattern: str = ""  # 命令匹配模式（正则表达式）
    command_help: str = ""  # 命令帮助信息
    command_examples: List[str] = None  # 命令使用示例
    intercept_message: bool = True  # 是否拦截消息处理（默认拦截）

    def __post_init__(self):
        super().__post_init__()
        if self.command_examples is None:
            self.command_examples = []
        self.component_type = ComponentType.COMMAND


@dataclass
class PluginInfo:
    """插件信息"""

    name: str  # 插件名称
    description: str  # 插件描述
    version: str = "1.0.0"  # 插件版本
    author: str = ""  # 插件作者
    enabled: bool = True  # 是否启用
    is_built_in: bool = False  # 是否为内置插件
    components: List[ComponentInfo] = None  # 包含的组件列表
    dependencies: List[str] = None  # 依赖的其他插件
    python_dependencies: List[PythonDependency] = None  # Python包依赖
    config_file: str = ""  # 配置文件路径
    metadata: Dict[str, Any] = None  # 额外元数据
    # 新增：manifest相关信息
    manifest_data: Dict[str, Any] = None  # manifest文件数据
    license: str = ""  # 插件许可证
    homepage_url: str = ""  # 插件主页
    repository_url: str = ""  # 插件仓库地址
    keywords: List[str] = None  # 插件关键词
    categories: List[str] = None  # 插件分类
    min_host_version: str = ""  # 最低主机版本要求
    max_host_version: str = ""  # 最高主机版本要求

    def __post_init__(self):
        if self.components is None:
            self.components = []
        if self.dependencies is None:
            self.dependencies = []
        if self.python_dependencies is None:
            self.python_dependencies = []
        if self.metadata is None:
            self.metadata = {}
        if self.manifest_data is None:
            self.manifest_data = {}
        if self.keywords is None:
            self.keywords = []
        if self.categories is None:
            self.categories = []

    def get_missing_packages(self) -> List[PythonDependency]:
        """检查缺失的Python包"""
        missing = []
        for dep in self.python_dependencies:
            try:
                __import__(dep.package_name)
            except ImportError:
                if not dep.optional:
                    missing.append(dep)
        return missing

    def get_pip_requirements(self) -> List[str]:
        """获取所有pip安装格式的依赖"""
        return [dep.get_pip_requirement() for dep in self.python_dependencies]
