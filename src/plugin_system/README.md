# MaiBot 插件系统 - 重构版

## 目录结构说明

经过重构，插件系统现在采用清晰的**系统核心**与**插件内容**分离的架构：

```
src/
├── plugin_system/          # 🔧 系统核心 - 插件框架本身
│   ├── __init__.py         # 统一导出接口
│   ├── core/               # 核心管理
│   │   ├── plugin_manager.py
│   │   ├── component_registry.py
│   │   └── __init__.py
│   ├── apis/               # API接口
│   │   ├── plugin_api.py   # 统一API聚合
│   │   ├── message_api.py
│   │   ├── llm_api.py
│   │   ├── database_api.py
│   │   ├── config_api.py
│   │   ├── utils_api.py
│   │   ├── stream_api.py
│   │   ├── hearflow_api.py
│   │   └── __init__.py
│   ├── base/               # 基础类
│   │   ├── base_plugin.py
│   │   ├── base_action.py
│   │   ├── base_command.py
│   │   ├── component_types.py
│   │   └── __init__.py
│   └── registry/           # 注册相关（预留）
└── plugins/                # 🔌 插件内容 - 具体的插件实现
    ├── built_in/           # 内置插件
    │   ├── system_actions/ # 系统内置Action
    │   └── system_commands/# 系统内置Command
    └── examples/           # 示例插件
        └── simple_plugin/
            ├── plugin.py
            └── config.toml
```

## 架构优势

### 1. 职责清晰
- **`src/plugin_system/`** - 系统提供的框架、API和基础设施
- **`src/plugins/`** - 用户开发或使用的具体插件

### 2. 导入简化
```python
# 统一导入接口
from src.plugin_system import (
    BasePlugin, register_plugin, BaseAction, BaseCommand,
    ActionInfo, CommandInfo, PluginAPI
)
```

### 3. 模块化设计
- 各个子模块都有清晰的职责和接口
- 支持按需导入特定功能
- 便于维护和扩展

## 快速开始

### 创建简单插件

```python
from src.plugin_system import BasePlugin, register_plugin, BaseAction, ActionInfo

class MyAction(BaseAction):
    async def execute(self):
        return True, "Hello from my plugin!"

@register_plugin
class MyPlugin(BasePlugin):
    plugin_name = "my_plugin" 
    plugin_description = "我的第一个插件"
    
    def get_plugin_components(self):
        return [(
            ActionInfo(name="my_action", description="我的动作"),
            MyAction
        )]
```

### 使用系统API

```python
class MyAction(BaseAction):
    async def execute(self):
        # 发送消息
        await self.api.send_text_to_group(
            self.api.get_service("chat_stream"), 
            "Hello World!"
        )
        
        # 数据库操作
        data = await self.api.db_get("table", "key")
        
        # LLM调用
        response = await self.api.llm_text_request("你好")
        
        return True, response
```

## 兼容性迁移

### 现有Action迁移
```python
# 旧方式
from src.chat.actions.base_action import BaseAction, register_action

# 新方式  
from src.plugin_system import BaseAction, register_plugin
from src.plugin_system.base.component_types import ActionInfo

# 将Action封装到Plugin中
@register_plugin
class MyActionPlugin(BasePlugin):
    plugin_name = "my_action_plugin"
    
    def get_plugin_components(self):
        return [(ActionInfo(...), MyAction)]
```

### 现有Command迁移
```python
# 旧方式
from src.chat.command.command_handler import BaseCommand, register_command

# 新方式
from src.plugin_system import BaseCommand, register_plugin
from src.plugin_system.base.component_types import CommandInfo

# 将Command封装到Plugin中
@register_plugin  
class MyCommandPlugin(BasePlugin):
    plugin_name = "my_command_plugin"
    
    def get_plugin_components(self):
        return [(CommandInfo(...), MyCommand)]
```

## 扩展指南

### 添加新的组件类型
1. 在 `component_types.py` 中定义新的组件类型
2. 在 `component_registry.py` 中添加对应的注册逻辑
3. 创建对应的基类

### 添加新的API
1. 在 `apis/` 目录下创建新的API模块
2. 在 `plugin_api.py` 中集成新API
3. 更新 `__init__.py` 导出接口

## 最佳实践

1. **单一插件包含相关组件** - 一个插件可以包含多个相关的Action和Command
2. **使用配置文件** - 通过TOML配置文件管理插件行为
3. **合理的组件命名** - 使用描述性的组件名称
4. **充分的错误处理** - 在组件中妥善处理异常
5. **详细的文档** - 为插件和组件编写清晰的文档

## 内置插件规划

- **系统核心插件** - 将现有的内置Action/Command迁移为系统插件
- **工具插件** - 常用的工具和实用功能
- **示例插件** - 帮助开发者学习的示例代码

这个重构保持了向后兼容性，同时提供了更清晰、更易维护的架构。 