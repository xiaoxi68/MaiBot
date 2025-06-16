# ⚙️ 插件配置定义指南

本文档将指导你如何为你的插件定义一个健壮、规范且自带文档的配置文件。

## 核心理念：Schema驱动的配置

在新版插件系统中，我们引入了一套 **配置Schema（模式）驱动** 的机制。你不再需要手动创建和维护 `config.toml` 文件，而是通过在插件代码中 **声明配置的结构**，系统将为你完成剩下的工作。

**核心优势:**

- **自动化 (Automation)**: 如果配置文件不存在，系统会根据你的声明 **自动生成** 一份包含默认值和详细注释的 `config.toml` 文件。
- **规范化 (Standardization)**: 所有插件的配置都遵循统一的结构，提升了可维护性。
- **自带文档 (Self-documenting)**: 配置文件中的每一项都包含详细的注释、类型说明、可选值和示例，极大地降低了用户的使用门槛。
- **健壮性 (Robustness)**: 在代码中直接定义配置的类型和默认值，减少了因配置错误导致的运行时问题。
- **易于管理 (Easy Management)**: 生成的配置文件可以方便地加入 `.gitignore`，避免将个人配置（如API Key）提交到版本库。

---

## 如何定义配置

配置的定义在你的插件主类（继承自 `BasePlugin`）中完成，主要通过两个类属性：

1.  `config_section_descriptions`: 一个字典，用于描述配置文件的各个区段（`[section]`）。
2.  `config_schema`: 核心部分，一个嵌套字典，用于定义每个区段下的具体配置项。

### `ConfigField`：配置项的基石

每个配置项都通过一个 `ConfigField` 对象来定义。

```python
from src.plugin_system.base.config_types import ConfigField

@dataclass
class ConfigField:
    """配置字段定义"""
    type: type          # 字段类型 (例如 str, int, float, bool, list)
    default: Any        # 默认值
    description: str    # 字段描述 (将作为注释生成到配置文件中)
    example: Optional[str] = None       # 示例值 (可选)
    required: bool = False              # 是否必需 (可选, 主要用于文档提示)
    choices: Optional[List[Any]] = None # 可选值列表 (可选)
```

---

## 完整示例

让我们以一个功能丰富的 `MutePlugin` 为例，看看如何定义它的配置。

### 1. 插件代码 (`plugin.py`)

```python
# src/plugins/built_in/mute_plugin/plugin.py

# ... 其他导入 ...
from src.plugin_system import BasePlugin, register_plugin
from src.plugin_system.base.config_types import ConfigField
from typing import List, Tuple, Type

@register_plugin
class MutePlugin(BasePlugin):
    """禁言插件"""

    # 插件基本信息
    plugin_name = "mute_plugin"
    plugin_description = "群聊禁言管理插件，提供智能禁言功能"
    plugin_version = "2.0.0"
    plugin_author = "MaiBot开发团队"
    enable_plugin = True
    config_file_name = "config.toml"

    # 步骤1: 定义配置节的描述
    config_section_descriptions = {
        "plugin": "插件基本信息配置",
        "components": "组件启用控制",
        "mute": "核心禁言功能配置",
        "smart_mute": "智能禁言Action的专属配置",
        "logging": "日志记录相关配置"
    }

    # 步骤2: 使用ConfigField定义详细的配置Schema
    config_schema = {
        "plugin": {
            "name": ConfigField(type=str, default="mute_plugin", description="插件名称", required=True),
            "version": ConfigField(type=str, default="2.0.0", description="插件版本号"),
            "enabled": ConfigField(type=bool, default=False, description="是否启用插件"),
            "description": ConfigField(type=str, default="群聊禁言管理插件", description="插件描述", required=True)
        },
        "components": {
            "enable_smart_mute": ConfigField(type=bool, default=True, description="是否启用智能禁言Action"),
            "enable_mute_command": ConfigField(type=bool, default=False, description="是否启用禁言命令Command")
        },
        "mute": {
            "min_duration": ConfigField(type=int, default=60, description="最短禁言时长（秒）"),
            "max_duration": ConfigField(type=int, default=2592000, description="最长禁言时长（秒），默认30天"),
            "templates": ConfigField(
                type=list,
                default=["好的，禁言 {target} {duration}，理由：{reason}", "收到，对 {target} 执行禁言 {duration}"],
                description="成功禁言后发送的随机消息模板"
            )
        },
        "smart_mute": {
            "keyword_sensitivity": ConfigField(
                type=str,
                default="normal",
                description="关键词激活的敏感度",
                choices=["low", "normal", "high"] # 定义可选值
            ),
        },
        "logging": {
            "level": ConfigField(
                type=str,
                default="INFO",
                description="日志记录级别",
                choices=["DEBUG", "INFO", "WARNING", "ERROR"]
            ),
            "prefix": ConfigField(type=str, default="[MutePlugin]", description="日志记录前缀", example="[MyMutePlugin]")
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        # ... 组件注册逻辑 ...
        # 在这里可以通过 self.get_config() 来获取配置值
        pass

```

### 2. 自动生成的配置文件 (`config.toml`)

当 `mute_plugin` 首次加载且其目录中不存在 `config.toml` 时，系统会自动创建以下文件：

```toml
# mute_plugin - 自动生成的配置文件
# 群聊禁言管理插件，提供智能禁言功能

# 插件基本信息配置
[plugin]

# 插件名称 (必需)
name = "mute_plugin"

# 插件版本号
version = "2.0.0"

# 是否启用插件
enabled = false

# 插件描述 (必需)
description = "群聊禁言管理插件"


# 组件启用控制
[components]

# 是否启用智能禁言Action
enable_smart_mute = true

# 是否启用禁言命令Command
enable_mute_command = false


# 核心禁言功能配置
[mute]

# 最短禁言时长（秒）
min_duration = 60

# 最长禁言时长（秒），默认30天
max_duration = 2592000

# 成功禁言后发送的随机消息模板
templates = ["好的，禁言 {target} {duration}，理由：{reason}", "收到，对 {target} 执行禁言 {duration}"]


# 智能禁言Action的专属配置
[smart_mute]

# 关键词激活的敏感度
# 可选值: low, normal, high
keyword_sensitivity = "normal"


# 日志记录相关配置
[logging]

# 日志记录级别
# 可选值: DEBUG, INFO, WARNING, ERROR
level = "INFO"

# 日志记录前缀
# 示例: [MyMutePlugin]
prefix = "[MutePlugin]"

```

## 最佳实践

1.  **定义优于创建**: 始终优先在 `plugin.py` 中定义 `config_schema`，而不是手动创建 `config.toml`。
2.  **描述清晰**: 为每个 `ConfigField` 和 `config_section_descriptions` 编写清晰、准确的描述。这会直接成为你的插件文档的一部分。
3.  **提供合理默认值**: 确保你的插件在默认配置下就能正常运行（或处于一个安全禁用的状态）。
4.  **gitignore**: 将 `plugins/*/config.toml` 或 `src/plugins/built_in/*/config.toml` 加入 `.gitignore`，以避免提交个人敏感信息。
5.  **访问配置**: 在插件的任何地方，统一使用 `self.api.get_config("section.key", "default_value")` 来安全地获取配置值。详细请参考 [**插件配置访问指南**](config-access-guide.md)。 