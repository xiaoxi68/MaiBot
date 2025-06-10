# MaiBot 插件编写指南 - 总览

## 📋 目录结构

本指南分为三个部分：

- **[总览](plugin_guide_overview.md)** - 插件系统架构和设计理念（当前文档）
- **[快速开始](plugin_quick_start.md)** - 5分钟创建你的第一个插件
- **[详细解析](plugin_detailed_guide.md)** - 深入理解各个组件和API

## 🎯 插件系统概述

MaiBot 采用组件化的插件系统，让开发者可以轻松扩展机器人功能。系统支持两种主要组件类型：

- **Action组件** - 智能动作，基于关键词、LLM判断等条件自动触发
- **Command组件** - 命令处理，基于正则表达式匹配用户输入的命令

## 🏗️ 系统架构

```
src/
├── plugin_system/          # 🔧 系统核心（框架代码）
│   ├── core/               # 插件管理和注册中心
│   ├── apis/               # 统一API接口（7大模块）
│   ├── base/               # 插件和组件基类
│   └── registry/           # 组件注册和查询
└── plugins/                # 🔌 插件内容（用户代码）
    ├── built_in/           # 内置插件
    └── examples/           # 示例插件
```

### 核心设计理念

1. **分离关注点** - 系统框架与插件内容完全分离
2. **组件化设计** - 一个插件可包含多个Action和Command组件
3. **统一API访问** - 通过PluginAPI统一访问所有系统功能
4. **声明式配置** - 通过类属性声明组件行为，简化开发
5. **类型安全** - 完整的类型定义，IDE友好

## 🧩 组件类型详解

### Action组件 - 智能动作

Action用于实现智能交互逻辑，支持多种激活方式：

- **关键词激活** - 消息包含特定关键词时触发
- **LLM判断激活** - 使用大模型智能判断是否需要触发
- **随机激活** - 按概率随机触发
- **始终激活** - 每条消息都触发（谨慎使用）

**适用场景：**
- 智能问候、闲聊互动
- 情感分析和回应
- 内容审核和提醒
- 数据统计和分析

### Command组件 - 命令处理

Command用于处理结构化的用户命令，基于正则表达式匹配：

- **精确匹配** - 支持参数提取和验证
- **灵活模式** - 正则表达式的完整威力
- **帮助系统** - 自动生成命令帮助信息

**适用场景：**
- 功能性操作（查询、设置、管理）
- 工具类命令（计算、转换、搜索）
- 系统管理命令
- 游戏和娱乐功能

## 🔌 API系统概览

系统提供7大API模块，涵盖插件开发的所有需求：

| API模块 | 功能描述 | 主要用途 |
|---------|----------|----------|
| **MessageAPI** | 消息发送和交互 | 发送文本、图片、语音等消息 |
| **LLMAPI** | 大模型调用 | 文本生成、智能判断、创意创作 |
| **DatabaseAPI** | 数据库操作 | 存储用户数据、配置、历史记录 |
| **ConfigAPI** | 配置访问 | 读取全局配置和用户信息 |
| **UtilsAPI** | 工具函数 | 文件操作、时间处理、ID生成 |
| **StreamAPI** | 流管理 | 聊天流控制和状态管理 |
| **HearflowAPI** | 心流系统 | 与消息处理流程集成 |

## 🎨 开发体验

### 简化的导入接口

```python
from src.plugin_system import (
    BasePlugin, register_plugin, BaseAction, BaseCommand,
    ComponentInfo, ActionInfo, CommandInfo, ActionActivationType, ChatMode
)
```

### 声明式组件定义

```python
class HelloAction(BaseAction):
    # 🎯 直接通过类属性定义行为
    focus_activation_type = ActionActivationType.KEYWORD
    activation_keywords = ["你好", "hello", "hi"]
    mode_enable = ChatMode.ALL
    
    async def execute(self) -> Tuple[bool, str]:
        return True, "你好！我是MaiBot 😊"
```

### 统一的API访问

```python
class MyCommand(BaseCommand):
    async def execute(self) -> Tuple[bool, Optional[str]]:
        # 💡 通过self.api访问所有系统功能
        await self.api.send_message("text", "处理中...")
        models = self.api.get_available_models()
        await self.api.store_user_data("key", "value")
        return True, "完成！"
```

## 🚀 开发流程

1. **创建插件目录** - 在 `src/plugins/` 下创建插件文件夹
2. **定义插件类** - 继承 `BasePlugin`，设置基本信息
3. **创建组件类** - 继承 `BaseAction` 或 `BaseCommand`
4. **注册组件** - 在插件的 `get_plugin_components()` 中返回组件列表
5. **测试验证** - 启动系统测试插件功能

## 📚 学习路径建议

1. **初学者** - 从[快速开始](plugin_quick_start.md)开始，5分钟体验插件开发
2. **进阶开发** - 阅读[详细解析](plugin_detailed_guide.md)，深入理解各个组件
3. **实战练习** - 参考 `simple_plugin` 示例，尝试开发自己的插件
4. **API探索** - 逐步尝试各个API模块的功能

## 💡 设计亮点

- **零配置启动** - 插件放入目录即可自动加载
- **热重载支持** - 开发过程中可动态重载插件（规划中）
- **依赖管理** - 支持插件间依赖关系声明
- **配置系统** - 支持TOML配置文件，灵活可定制
- **完整API** - 覆盖机器人开发的各个方面
- **类型安全** - 完整的类型注解，IDE智能提示

## 🎯 下一步

选择适合你的起点：

- 🚀 [立即开始 →](plugin_quick_start.md) 
- 📖 [深入学习 →](plugin_detailed_guide.md)
- 🔍 [查看示例 →](../src/plugins/examples/simple_plugin/)

---

> 💡 **提示**: 插件系统仍在持续改进中，欢迎提出建议和反馈！ 