# MaiBot 插件快速开始指南

## 🚀 5分钟创建你的第一个插件

本指南将带你快速创建一个功能完整的插件，体验MaiBot插件开发的简单和强大。

## 📋 前置要求

- 已克隆MaiBot项目到本地
- Python 3.8+ 环境
- 基本的Python编程知识

## 🎯 我们要做什么

我们将创建一个名为 `my_first_plugin` 的插件，包含：
- 一个Action组件：自动回应"Hello"
- 一个Command组件：计算器功能

## 📁 第一步：创建插件目录

在 `src/plugins/examples/` 下创建你的插件目录：

```bash
mkdir src/plugins/examples/my_first_plugin
```

## 📝 第二步：创建插件文件

在插件目录中创建 `plugin.py` 文件：

```python
# src/plugins/examples/my_first_plugin/plugin.py

from typing import List, Tuple, Type, Optional
import re

# 导入插件系统核心
from src.plugin_system import (
    BasePlugin, register_plugin, BaseAction, BaseCommand,
    ComponentInfo, ActionInfo, CommandInfo, ActionActivationType, ChatMode
)
from src.common.logger_manager import get_logger

logger = get_logger("my_first_plugin")


class HelloAction(BaseAction):
    """自动问候Action - 当用户说Hello时自动回应"""
    
    # 🎯 声明式配置：只需设置类属性
    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD
    activation_keywords = ["hello", "Hello", "HELLO"]
    keyword_case_sensitive = False
    mode_enable = ChatMode.ALL
    parallel_action = False
    
    async def execute(self) -> Tuple[bool, str]:
        """执行问候动作"""
        username = self.action_data.get("username", "朋友")
        response = f"Hello, {username}! 很高兴见到你！ 🎉"
        
        logger.info(f"向 {username} 发送问候")
        return True, response


class CalculatorCommand(BaseCommand):
    """计算器命令 - 执行简单数学运算"""
    
    # 🎯 声明式配置：定义命令模式
    command_pattern = r"^/calc\s+(?P<expression>[\d\+\-\*/\(\)\s\.]+)$"
    command_help = "计算器，用法：/calc <数学表达式>"
    command_examples = ["/calc 1+1", "/calc 2*3+4", "/calc (10-5)*2"]
    
    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行计算命令"""
        # 获取匹配的表达式
        expression = self.matched_groups.get("expression", "").strip()
        
        if not expression:
            await self.send_reply("❌ 请提供数学表达式！")
            return False, None
        
        try:
            # 安全计算（只允许基本数学运算）
            allowed_chars = set("0123456789+-*/.() ")
            if not all(c in allowed_chars for c in expression):
                await self.send_reply("❌ 表达式包含不允许的字符！")
                return False, None
            
            # 执行计算
            result = eval(expression)  # 在实际项目中应使用更安全的计算方法
            
            response = f"🧮 计算结果：\n`{expression} = {result}`"
            await self.send_reply(response)
            
            logger.info(f"计算: {expression} = {result}")
            return True, response
            
        except Exception as e:
            error_msg = f"❌ 计算错误: {str(e)}"
            await self.send_reply(error_msg)
            logger.error(f"计算失败: {expression}, 错误: {e}")
            return False, error_msg


@register_plugin
class MyFirstPlugin(BasePlugin):
    """我的第一个插件 - 展示基本功能"""
    
    # 🏷️ 插件基本信息
    plugin_name = "my_first_plugin"
    plugin_description = "我的第一个MaiBot插件，包含问候和计算功能"
    plugin_version = "1.0.0"
    plugin_author = "你的名字"
    enable_plugin = True
    
    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件"""
        
        return [
            # Action组件：自动问候
            (HelloAction.get_action_info(
                name="hello_action", 
                description="自动回应Hello问候"
            ), HelloAction),
            
            # Command组件：计算器
            (CalculatorCommand.get_command_info(
                name="calculator_command",
                description="简单计算器，支持基础数学运算"
            ), CalculatorCommand)
        ]
```

## 📊 第三步：创建配置文件（可选）

创建 `config.toml` 文件来配置插件：

```toml
# src/plugins/examples/my_first_plugin/config.toml

[plugin]
name = "my_first_plugin"
description = "我的第一个插件"
enabled = true

[hello_action]
enable_emoji = true
greeting_message = "Hello, {username}! 很高兴见到你！"

[calculator]
max_expression_length = 100
allow_complex_math = false
```

如果你创建了配置文件，需要在插件类中指定：

```python
@register_plugin
class MyFirstPlugin(BasePlugin):
    # ... 其他属性 ...
    config_file_name = "config.toml"  # 添加这一行
```

## 🔄 第四步：测试插件

1. **启动MaiBot**：
   ```bash
   cd /path/to/MaiBot-Core
   python -m src.main
   ```

2. **测试Action组件**：
   - 在聊天中发送 "Hello" 或 "hello"
   - 应该收到自动回复："Hello, [用户名]! 很高兴见到你！ 🎉"

3. **测试Command组件**：
   - 发送 `/calc 1+1`
   - 应该收到回复："🧮 计算结果：\n`1+1 = 2`"

## 🎉 恭喜！

你已经成功创建了第一个MaiBot插件！插件包含：

✅ **一个Action组件** - 智能响应用户问候  
✅ **一个Command组件** - 提供计算器功能  
✅ **完整的配置** - 支持自定义行为  
✅ **错误处理** - 优雅处理异常情况  

## 🔍 代码解析

### Action组件关键点

```python
# 声明激活条件
focus_activation_type = ActionActivationType.KEYWORD
activation_keywords = ["hello", "Hello", "HELLO"]

# 执行逻辑
async def execute(self) -> Tuple[bool, str]:
    # 处理逻辑
    return True, response  # (成功状态, 回复内容)
```

### Command组件关键点

```python
# 声明命令模式（正则表达式）
command_pattern = r"^/calc\s+(?P<expression>[\d\+\-\*/\(\)\s\.]+)$"

# 执行逻辑
async def execute(self) -> Tuple[bool, Optional[str]]:
    expression = self.matched_groups.get("expression")  # 获取匹配参数
    await self.send_reply(response)  # 发送回复
    return True, response
```

### 插件注册

```python
@register_plugin  # 装饰器注册插件
class MyFirstPlugin(BasePlugin):
    # 基本信息
    plugin_name = "my_first_plugin"
    plugin_description = "插件描述"
    
    # 返回组件列表
    def get_plugin_components(self):
        return [(组件信息, 组件类), ...]
```

## 🎯 下一步学习

现在你已经掌握了基础，可以继续学习：

1. **深入API** - 探索[详细解析](plugin_detailed_guide.md)了解更多API功能
2. **参考示例** - 查看 `simple_plugin` 了解更复杂的功能
3. **自定义扩展** - 尝试添加更多组件和功能

## 🛠️ 常见问题

### Q: 插件没有被加载？
A: 检查：
- 插件目录是否在 `src/plugins/` 下
- 文件名是否为 `plugin.py`
- 类是否有 `@register_plugin` 装饰器
- 是否有语法错误

### Q: Action组件没有触发？
A: 检查：
- `activation_keywords` 是否正确设置
- `focus_activation_type` 和 `normal_activation_type` 是否设置
- 消息内容是否包含关键词

### Q: Command组件不响应？
A: 检查：
- `command_pattern` 正则表达式是否正确
- 用户输入是否完全匹配模式
- 是否有语法错误

## 📚 相关文档

- [系统总览](plugin_guide_overview.md) - 了解整体架构
- [详细解析](plugin_detailed_guide.md) - 深入学习各个组件
- [示例插件](../src/plugins/examples/simple_plugin/) - 完整功能示例

---

> 🎉 **恭喜完成快速开始！** 现在你已经是MaiBot插件开发者了！ 