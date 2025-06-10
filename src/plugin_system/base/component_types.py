from enum import Enum
from typing import Dict, Any, List
from dataclasses import dataclass

# 组件类型枚举
class ComponentType(Enum):
    """组件类型枚举"""
    ACTION = "action"       # 动作组件
    COMMAND = "command"     # 命令组件
    SCHEDULER = "scheduler" # 定时任务组件（预留）
    LISTENER = "listener"   # 事件监听组件（预留）

# 动作激活类型枚举
class ActionActivationType(Enum):
    """动作激活类型枚举"""
    NEVER = "never"           # 从不激活（默认关闭）
    ALWAYS = "always"         # 默认参与到planner
    LLM_JUDGE = "llm_judge"   # LLM判定是否启动该action到planner  
    RANDOM = "random"         # 随机启用action到planner
    KEYWORD = "keyword"       # 关键词触发启用action到planner

# 聊天模式枚举
class ChatMode(Enum):
    """聊天模式枚举"""
    FOCUS = "focus"    # Focus聊天模式
    NORMAL = "normal"  # Normal聊天模式
    ALL = "all"        # 所有聊天模式

@dataclass
class ComponentInfo:
    """组件信息"""
    name: str                           # 组件名称
    component_type: ComponentType       # 组件类型
    description: str                    # 组件描述
    enabled: bool = True                # 是否启用
    plugin_name: str = ""              # 所属插件名称
    is_built_in: bool = False          # 是否为内置组件
    metadata: Dict[str, Any] = None     # 额外元数据
    
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
    command_pattern: str = ""           # 命令匹配模式（正则表达式）
    command_help: str = ""              # 命令帮助信息
    command_examples: List[str] = None  # 命令使用示例
    
    def __post_init__(self):
        super().__post_init__()
        if self.command_examples is None:
            self.command_examples = []
        self.component_type = ComponentType.COMMAND

@dataclass
class PluginInfo:
    """插件信息"""
    name: str                           # 插件名称
    description: str                    # 插件描述
    version: str = "1.0.0"             # 插件版本
    author: str = ""                    # 插件作者
    enabled: bool = True                # 是否启用
    is_built_in: bool = False          # 是否为内置插件
    components: List[ComponentInfo] = None  # 包含的组件列表
    dependencies: List[str] = None      # 依赖的其他插件
    config_file: str = ""              # 配置文件路径
    metadata: Dict[str, Any] = None     # 额外元数据
    
    def __post_init__(self):
        if self.components is None:
            self.components = []
        if self.dependencies is None:
            self.dependencies = []
        if self.metadata is None:
            self.metadata = {} 