# 📋 开发标准规范

## 🎯 概述

本文档定义了MaiBot插件开发的标准规范，包括Action组件、Command组件和Tool组件的开发规范，确保代码质量、可维护性和性能。

## 🧩 组件开发规范

### Tool组件开发

**工具基本要求**：
- 继承 `BaseTool` 基类
- 定义唯一的工具名称
- 提供清晰的功能描述
- 使用JSONSchema定义参数
- 实现 `execute` 异步方法
- 使用 `register_tool()` 注册

**工具开发模板**：
```python
from src.tools.tool_can_use.base_tool import BaseTool, register_tool

class MyTool(BaseTool):
    """工具类文档字符串"""
    
    name = "my_tool"
    description = "详细的工具功能描述，告诉LLM这个工具的用途"
    
    parameters = {
        "type": "object",
        "properties": {
            "param": {
                "type": "string",
                "description": "参数详细描述"
            }
        },
        "required": ["param"]
    }
    
    async def execute(self, function_args, message_txt=""):
        """执行工具逻辑
        
        Args:
            function_args: 工具调用参数
            message_txt: 原始消息文本
            
        Returns:
            dict: 包含name和content字段的结果
        """
        # 实现工具功能逻辑
        result = "处理结果"
        
        return {
            "name": self.name,
            "content": result
        }

# 注册工具
register_tool(MyTool)
```

**工具命名规范**：
- 使用描述性的英文名称
- 采用下划线命名法（snake_case）
- 体现工具的核心功能
- 避免过于简短或复杂的名称

**示例**：
```python
# ✅ 好的命名
name = "weather_query"        # 天气查询
name = "knowledge_search"     # 知识搜索
name = "stock_price_check"    # 股价检查

# ❌ 避免的命名
name = "tool1"               # 无意义
name = "wq"                  # 过于简短
name = "weather_and_news"    # 功能复杂
```

### Action组件开发

**Action必需字段检查表**：

**激活控制字段**：
- ✅ `activation_type`：激活类型（KEYWORD/LLM_JUDGE/RANDOM/ALWAYS/NEVER）
- ✅ `activation_config`：激活配置参数

**基本信息字段**：
- ✅ `name`：Action唯一标识名称
- ✅ `description`：功能描述
- ✅ `usage_tip`：使用提示

**功能定义字段**：
- ✅ `func`：执行函数
- ✅ `llm_function_tips`：LLM调用提示

**Action开发模板**：
```python
from src.plugin_system.base_actions import BaseAction

class MyAction(BaseAction):
    """Action类文档字符串"""
    
    # 激活控制
    activation_type = "KEYWORD"  # 或 LLM_JUDGE/RANDOM/ALWAYS/NEVER
    activation_config = {
        "keywords": ["关键词1", "关键词2"],
        "priority": 1
    }
    
    # 基本信息
    name = "my_action"
    description = "Action功能描述"
    usage_tip = "使用场景和方法提示"
    
    # 功能定义
    func = "执行函数名"
    llm_function_tips = "告诉LLM何时以及如何使用这个Action"
    
    async def 执行函数名(self, message_txt, sender_name, chat_stream):
        """Action执行逻辑"""
        # 实现Action功能
        await chat_stream.send_message("执行结果")
```

**激活类型使用规范**：
- `KEYWORD`：适用于有明确关键词的功能，性能最优
- `LLM_JUDGE`：适用于需要智能判断的复杂场景
- `RANDOM`：适用于随机触发的功能
- `ALWAYS`：适用于总是可用的基础功能
- `NEVER`：适用于临时禁用的功能

### Command组件开发

**Command开发模板**：
```python
from src.plugin_system.base_commands import BaseCommand

class MyCommand(BaseCommand):
    """Command类文档字符串"""
    
    # 命令基本信息
    command_name = "my_command"
    description = "命令功能描述"
    usage = "/my_command <参数> - 命令使用说明"
    
    # 匹配模式
    pattern = r"^/my_command\s+(.*)"
    
    async def execute(self, match, message_txt, sender_name, chat_stream):
        """Command执行逻辑"""
        params = match.group(1) if match.group(1) else ""
        
        # 实现命令功能
        await chat_stream.send_message(f"命令执行结果: {params}")
```

## 📝 代码结构标准

### 文件组织结构

```
plugins/my_plugin/
├── __init__.py          # 插件入口
├── plugin.py           # 插件主文件
├── config.toml         # 插件配置
├── actions/            # Action组件目录
│   ├── __init__.py
│   └── my_action.py
├── commands/           # Command组件目录
│   ├── __init__.py
│   └── my_command.py
├── utils/              # 工具函数目录
│   ├── __init__.py
│   └── helpers.py
└── README.md           # 插件说明文档
```

### 插件主文件模板

```python
"""
插件名称：My Plugin
插件描述：插件功能描述
作者：作者名称
版本：1.0.0
"""

from src.plugin_system.plugin_interface import PluginInterface
from .actions.my_action import MyAction
from .commands.my_command import MyCommand

class MyPlugin(PluginInterface):
    """插件主类"""
    
    def get_action_info(self):
        """获取Action信息"""
        return [MyAction()]
    
    def get_command_info(self):
        """获取Command信息"""
        return [MyCommand()]

# 插件实例
plugin_instance = MyPlugin()
```

## 🔧 命名规范

### 类命名
- **Action类**：使用 `Action` 后缀，如 `GreetingAction`
- **Command类**：使用 `Command` 后缀，如 `HelpCommand`
- **Tool类**：使用 `Tool` 后缀，如 `WeatherTool`
- **插件类**：使用 `Plugin` 后缀，如 `ExamplePlugin`

### 变量命名
- 使用小写字母和下划线（snake_case）
- 布尔变量使用 `is_`、`has_`、`can_` 前缀
- 常量使用全大写字母

### 函数命名
- 使用小写字母和下划线（snake_case）
- 异步函数不需要特殊前缀
- 私有方法使用单下划线前缀

## 📊 性能优化规范

### Action激活类型选择
1. **首选KEYWORD**：明确知道触发关键词时
2. **谨慎使用LLM_JUDGE**：仅在必须智能判断时使用
3. **合理设置优先级**：避免过多高优先级Action

### 异步编程规范
- 所有I/O操作必须使用异步
- 避免在异步函数中使用阻塞操作
- 合理使用 `asyncio.gather()` 并发执行

### 资源管理
- 及时关闭文件、网络连接等资源
- 使用上下文管理器（`async with`）
- 避免内存泄漏

## 🚨 错误处理规范

### 异常处理模板

```python
async def my_function(self, message_txt, sender_name, chat_stream):
    """函数文档字符串"""
    try:
        # 核心逻辑
        result = await some_operation()
        
        # 成功处理
        await chat_stream.send_message(f"操作成功: {result}")
        
    except ValueError as e:
        # 具体异常处理
        await chat_stream.send_message(f"参数错误: {str(e)}")
        
    except Exception as e:
        # 通用异常处理
        await chat_stream.send_message(f"操作失败: {str(e)}")
        # 记录错误日志
        logger.error(f"Function my_function failed: {str(e)}")
```

### 错误信息规范
- 使用用户友好的错误提示
- 避免暴露系统内部信息
- 提供解决建议或替代方案
- 记录详细的错误日志

## 🧪 测试标准

### 单元测试模板

```python
import unittest
import asyncio
from unittest.mock import Mock, AsyncMock
from plugins.my_plugin.actions.my_action import MyAction

class TestMyAction(unittest.TestCase):
    """MyAction测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.action = MyAction()
        self.mock_chat_stream = AsyncMock()
    
    def test_action_properties(self):
        """测试Action属性"""
        self.assertEqual(self.action.name, "my_action")
        self.assertIsNotNone(self.action.description)
        self.assertIsNotNone(self.action.activation_type)
    
    async def test_action_execution(self):
        """测试Action执行"""
        await self.action.执行函数名("测试消息", "测试用户", self.mock_chat_stream)
        
        # 验证消息发送
        self.mock_chat_stream.send_message.assert_called()
    
    def test_action_execution_sync(self):
        """同步测试包装器"""
        asyncio.run(self.test_action_execution())

if __name__ == '__main__':
    unittest.main()
```

### 测试覆盖率要求
- 核心功能必须有测试覆盖
- 异常处理路径需要测试
- 边界条件需要验证

## 📚 文档规范

### 代码文档
- 所有类和函数必须有文档字符串
- 使用Google风格的docstring
- 包含参数说明和返回值说明

### README文档模板

```markdown
# 插件名称

## 📖 插件描述
简要描述插件的功能和用途

## ✨ 功能特性
- 功能1：功能描述
- 功能2：功能描述

## 🚀 快速开始
### 安装配置
1. 步骤1
2. 步骤2

### 使用方法
具体的使用说明和示例

## 📝 配置说明
配置文件的详细说明

## 🔧 开发信息
- 作者：作者名称
- 版本：版本号
- 许可证：许可证类型
```

## 🔍 代码审查清单

### 基础检查
- [ ] 代码符合命名规范
- [ ] 类和函数有完整文档字符串
- [ ] 异常处理覆盖完整
- [ ] 没有硬编码的配置信息

### Action组件检查
- [ ] 包含所有必需字段
- [ ] 激活类型选择合理
- [ ] LLM函数提示清晰
- [ ] 执行函数实现正确

### Command组件检查
- [ ] 正则表达式模式正确
- [ ] 参数提取和验证完整
- [ ] 使用说明准确

### Tool组件检查
- [ ] 继承BaseTool基类
- [ ] 参数定义遵循JSONSchema
- [ ] 返回值格式正确
- [ ] 工具已正确注册

### 性能检查
- [ ] 避免不必要的LLM_JUDGE激活
- [ ] 异步操作使用正确
- [ ] 资源管理合理

### 安全检查
- [ ] 输入参数验证
- [ ] SQL注入防护
- [ ] 敏感信息保护

## 🎯 最佳实践总结

### 设计原则
1. **单一职责**：每个组件专注单一功能
2. **松耦合**：减少组件间依赖
3. **高内聚**：相关功能聚合在一起
4. **可扩展**：易于添加新功能

### 性能优化
1. **合理选择激活类型**：优先使用KEYWORD
2. **避免阻塞操作**：使用异步编程
3. **缓存重复计算**：提高响应速度
4. **资源池化**：复用连接和对象

### 用户体验
1. **友好的错误提示**：帮助用户理解问题
2. **清晰的使用说明**：降低学习成本
3. **一致的交互方式**：统一的命令格式
4. **及时的反馈**：让用户知道操作状态

---

🎉 **遵循这些标准可以确保插件的质量、性能和用户体验！** 