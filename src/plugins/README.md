# MaiBot 插件系统架构

## 概述

MaiBot 插件系统采用组件化设计，支持插件包含多种组件类型：
- **Action组件**：处理聊天中的动作逻辑
- **Command组件**：处理命令请求
- **未来扩展**：Scheduler（定时任务）、Listener（事件监听）等

## 目录结构

```
src/plugins/
├── core/                          # 插件核心管理
│   ├── plugin_manager.py          # 插件管理器
│   ├── plugin_loader.py           # 插件加载器（预留）
│   └── component_registry.py      # 组件注册中心
├── apis/                          # API模块
│   ├── plugin_api.py              # 统一API聚合
│   ├── message_api.py             # 消息API
│   ├── llm_api.py                 # LLM API
│   ├── database_api.py            # 数据库API
│   ├── config_api.py              # 配置API
│   ├── utils_api.py               # 工具API
│   ├── stream_api.py              # 流API
│   └── hearflow_api.py            # 心流API
├── base/                          # 基础类
│   ├── base_plugin.py             # 插件基类
│   ├── base_action.py             # Action组件基类
│   ├── base_command.py            # Command组件基类
│   └── component_types.py         # 组件类型定义
├── built_in/                      # 内置组件
│   ├── actions/                   # 内置Action
│   └── commands/                  # 内置Command
└── examples/                      # 示例插件
    └── simple_plugin/             # 简单插件示例
        ├── plugin.py
        └── config.toml
```

## 核心特性

### 1. 组件化设计
- 插件可以包含多种组件类型
- 每种组件有明确的职责和接口
- 支持组件的独立启用/禁用

### 2. 统一的API访问
- 所有插件组件通过 `PluginAPI` 访问系统功能
- 包含消息发送、数据库操作、LLM调用等
- 提供统一的错误处理和日志记录

### 3. 灵活的配置系统
- 支持 TOML 格式的配置文件
- 插件可以读取自定义配置
- 支持全局配置和插件特定配置

### 4. 统一的注册管理
- 组件注册中心管理所有组件
- 支持组件的动态启用/禁用
- 提供丰富的查询和统计接口

## 插件开发指南

### 创建基本插件

```python
from src.plugins.base.base_plugin import BasePlugin, register_plugin
from src.plugins.base.base_action import BaseAction
from src.plugins.base.component_types import ActionInfo, ActionActivationType

class MyAction(BaseAction):
    async def execute(self) -> tuple[bool, str]:
        # 使用API发送消息
        response = "Hello from my plugin!"
        return True, response

@register_plugin
class MyPlugin(BasePlugin):
    plugin_name = "my_plugin"
    plugin_description = "我的第一个插件"
    
    def get_plugin_components(self):
        action_info = ActionInfo(
            name="my_action",
            description="我的动作",
            activation_keywords=["hello"]
        )
        return [(action_info, MyAction)]
```

### 创建命令组件

```python
from src.plugins.base.base_command import BaseCommand
from src.plugins.base.component_types import CommandInfo

class MyCommand(BaseCommand):
    async def execute(self) -> tuple[bool, str]:
        # 获取命令参数
        param = self.matched_groups.get("param", "")
        
        # 发送回复
        await self.send_reply(f"收到参数: {param}")
        return True, f"处理完成: {param}"

# 在插件中注册
def get_plugin_components(self):
    command_info = CommandInfo(
        name="my_command",
        description="我的命令",
        command_pattern=r"^/mycmd\s+(?P<param>\w+)$",
        command_help="用法：/mycmd <参数>"
    )
    return [(command_info, MyCommand)]
```

### 使用配置文件

```toml
# config.toml
[plugin]
name = "my_plugin"
enabled = true

[my_settings]
max_items = 10
default_message = "Hello World"
```

```python
class MyPlugin(BasePlugin):
    config_file_name = "config.toml"
    
    def get_plugin_components(self):
        # 读取配置
        max_items = self.get_config("my_settings.max_items", 5)
        message = self.get_config("my_settings.default_message", "Hi")
        
        # 使用配置创建组件...
```

## API使用示例

### 消息操作
```python
# 发送文本消息
await self.api.send_text_to_group(chat_stream, "Hello!")

# 发送图片
await self.api.send_image_to_group(chat_stream, image_path)
```

### 数据库操作
```python
# 查询数据
data = await self.api.db_get("table_name", "key")

# 保存数据
await self.api.db_set("table_name", "key", "value")
```

### LLM调用
```python
# 生成文本
response = await self.api.llm_text_request("你好，请介绍一下自己")

# 生成图片
image_url = await self.api.llm_image_request("一只可爱的猫咪")
```

## 内置组件迁移

现有的内置Action和Command将迁移到新架构：

### Action迁移
- `reply_action.py` → `src/plugins/built_in/actions/reply_action.py`
- `emoji_action.py` → `src/plugins/built_in/actions/emoji_action.py`
- `no_reply_action.py` → `src/plugins/built_in/actions/no_reply_action.py`

### Command迁移
- 现有命令系统将封装为内置Command组件
- 保持现有的命令模式和功能

## 兼容性

新插件系统保持与现有系统的兼容性：
- 现有的Action和Command继续工作
- 提供兼容层和适配器
- 逐步迁移到新架构

## 扩展性

系统设计支持未来扩展：
- 新的组件类型（Scheduler、Listener等）
- 插件间依赖和通信
- 插件热重载
- 插件市场和分发

## 最佳实践

1. **单一职责**：每个组件专注于特定功能
2. **配置驱动**：通过配置文件控制行为
3. **错误处理**：妥善处理异常情况
4. **日志记录**：记录关键操作和错误
5. **测试覆盖**：为插件编写单元测试 