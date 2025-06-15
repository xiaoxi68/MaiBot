# 🚀 快速开始指南

## 📖 概述

这个指南将带你在5分钟内创建你的第一个MaiBot插件。我们将创建一个简单的问候插件，展示插件系统的基本概念。

## 🎯 学习目标

- 理解插件的基本结构
- 创建你的第一个Action组件
- 创建你的第一个Command组件
- 学会配置插件

## 📂 准备工作

确保你已经：
1. 克隆了MaiBot项目
2. 安装了Python依赖
3. 了解基本的Python语法

## 🏗️ 创建插件

### 1. 创建插件目录

在项目根目录的 `plugins/` 文件夹下创建你的插件目录：

```bash
mkdir plugins/hello_world_plugin
cd plugins/hello_world_plugin
```

### 2. 创建插件主文件

创建 `plugin.py` 文件：

```python
from typing import List, Tuple, Type
from src.plugin_system import (
    BasePlugin, register_plugin, BaseAction, BaseCommand,
    ComponentInfo, ActionActivationType, ChatMode
)

# ===== Action组件 =====

class HelloAction(BaseAction):
    """问候Action - 展示智能动作的基本用法"""

    # ===== 激活控制必须项 =====
    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD
    mode_enable = ChatMode.ALL
    parallel_action = False

    # ===== 基本信息必须项 =====
    action_name = "hello_greeting"
    action_description = "向用户发送友好的问候消息"

    # 关键词配置
    activation_keywords = ["你好", "hello", "hi"]
    keyword_case_sensitive = False

    # ===== 功能定义必须项 =====
    action_parameters = {
        "greeting_style": "问候风格：casual(随意) 或 formal(正式)"
    }

    action_require = [
        "用户发送问候语时使用",
        "营造友好的聊天氛围"
    ]

    associated_types = ["text", "emoji"]

    async def execute(self) -> Tuple[bool, str]:
        """执行问候动作"""
        # 获取参数
        style = self.action_data.get("greeting_style", "casual")
        
        # 根据风格生成问候语
        if style == "formal":
            message = "您好！很高兴为您服务！"
            emoji = "🙏"
        else:
            message = "嗨！很开心见到你！"
            emoji = "😊"
        
        # 发送消息
        await self.send_text(message)
        await self.send_type("emoji", emoji)
        
        return True, f"发送了{style}风格的问候"

# ===== Command组件 =====

class TimeCommand(BaseCommand):
    """时间查询Command - 展示命令的基本用法"""

    command_pattern = r"^/time$"
    command_help = "查询当前时间"
    command_examples = ["/time"]
    intercept_message = True  # 拦截消息处理

    async def execute(self) -> Tuple[bool, str]:
        """执行时间查询"""
        import datetime
        
        now = datetime.datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        await self.send_text(f"⏰ 当前时间：{time_str}")
        
        return True, f"显示了当前时间: {time_str}"

# ===== 插件注册 =====

@register_plugin
class HelloWorldPlugin(BasePlugin):
    """Hello World插件 - 你的第一个MaiBot插件"""

    # 插件基本信息
    plugin_name = "hello_world_plugin"
    plugin_description = "Hello World演示插件，展示基本的Action和Command用法"
    plugin_version = "1.0.0"
    plugin_author = "你的名字"
    enable_plugin = True
    config_file_name = "config.toml"

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""
        return [
            # Action组件 - 使用类中定义的所有属性
            (HelloAction.get_action_info(), HelloAction),
            
            # Command组件 - 需要指定name和description
            (TimeCommand.get_command_info(
                name="time_query", 
                description="查询当前系统时间"
            ), TimeCommand),
        ]
```

### 3. 创建配置文件

创建 `config.toml` 文件：

```toml
[plugin]
name = "hello_world_plugin"
version = "1.0.0"
enabled = true
description = "Hello World演示插件"

[greeting]
default_style = "casual"
enable_emoji = true

[time]
timezone = "Asia/Shanghai"
format = "%Y-%m-%d %H:%M:%S"

[logging]
level = "INFO"
```

### 4. 创建说明文档

创建 `README.md` 文件：

```markdown
# Hello World 插件

## 概述

这是一个简单的Hello World插件，演示了MaiBot插件系统的基本用法。

## 功能

- **HelloAction**: 智能问候动作，响应用户的问候语
- **TimeCommand**: 时间查询命令，显示当前时间

## 使用方法

### Action使用
当用户发送包含"你好"、"hello"或"hi"的消息时，插件会自动触发问候动作。

### Command使用
发送 `/time` 查询当前时间。

## 配置

可以通过 `config.toml` 调整插件行为。
```

## 🎮 测试插件

### 1. 启动MaiBot

将插件放入 `plugins/` 目录后，启动MaiBot：

```bash
python main.py
```

### 2. 测试Action

发送消息：
```
你好
```

期望输出：
```
嗨！很开心见到你！😊
```

### 3. 测试Command

发送命令：
```
/time
```

期望输出：
```
⏰ 当前时间：2024-01-01 12:00:00
```

## 🔍 解析代码

### Action组件重点

1. **激活控制**: 使用 `KEYWORD` 激活类型，当检测到指定关键词时触发
2. **必须项完整**: 包含所有必须的类属性
3. **智能决策**: 麦麦会根据情境决定是否使用这个Action

### Command组件重点

1. **正则匹配**: 使用 `^/time$` 精确匹配 `/time` 命令
2. **消息拦截**: 设置 `intercept_message = True` 防止命令继续处理
3. **即时响应**: 匹配到命令立即执行

### 插件注册重点

1. **@register_plugin**: 装饰器自动注册插件
2. **组件列表**: `get_plugin_components()` 返回所有组件
3. **配置加载**: 自动加载 `config.toml` 文件

## 🎯 下一步

恭喜！你已经创建了第一个MaiBot插件。接下来可以：

1. 学习 [Action组件详解](action-components.md) 掌握更复杂的Action开发
2. 学习 [Command组件详解](command-components.md) 创建更强大的命令
3. 查看 [API参考](api/) 了解所有可用的接口
4. 参考 [完整示例](examples/complete-examples.md) 学习最佳实践

## 🐛 常见问题

### Q: 插件没有加载怎么办？
A: 检查：
1. 插件是否放在 `plugins/` 目录下
2. `plugin.py` 文件语法是否正确
3. 查看启动日志中的错误信息

### Q: Action没有触发怎么办？
A: 检查：
1. 关键词是否正确配置
2. 消息是否包含激活关键词
3. 聊天模式是否匹配

### Q: Command无响应怎么办？
A: 检查：
1. 正则表达式是否正确
2. 命令格式是否精确匹配
3. 是否有其他插件拦截了消息

---

🎉 **成功！你已经掌握了MaiBot插件开发的基础！** 