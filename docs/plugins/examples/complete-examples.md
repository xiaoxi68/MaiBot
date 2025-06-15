# 📚 完整示例

## 📖 概述

这里收集了各种类型的完整插件示例，展示了MaiBot插件系统的最佳实践和高级用法。每个示例都包含完整的代码、配置和说明。

## 🎯 示例列表

### 🌟 基础示例
- [Hello World插件](#hello-world插件) - 快速入门示例
- [简单计算器](#简单计算器) - Command基础用法
- [智能问答](#智能问答) - Action基础用法

### 🔧 实用示例
- [用户管理系统](#用户管理系统) - 数据库操作示例
- [定时提醒插件](#定时提醒插件) - 定时任务示例
- [天气查询插件](#天气查询插件) - 外部API调用示例

### 🛠️ 工具系统示例
- [天气查询工具](#天气查询工具) - Focus模式信息获取工具
- [知识搜索工具](#知识搜索工具) - 百科知识查询工具

### 🚀 高级示例
- [多功能聊天助手](#多功能聊天助手) - 综合功能插件
- [游戏管理插件](#游戏管理插件) - 复杂状态管理
- [数据分析插件](#数据分析插件) - 数据处理和可视化

---

## Hello World插件

最基础的入门插件，展示Action和Command的基本用法。

### 功能说明
- **HelloAction**: 响应问候语，展示关键词激活
- **TimeCommand**: 查询当前时间，展示命令处理

### 完整代码

`plugins/hello_world_plugin/plugin.py`:

```python
from typing import List, Tuple, Type
from src.plugin_system import (
    BasePlugin, register_plugin, BaseAction, BaseCommand,
    ComponentInfo, ActionActivationType, ChatMode
)

class HelloAction(BaseAction):
    """问候Action"""

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
        style = self.action_data.get("greeting_style", "casual")
        
        if style == "formal":
            message = "您好！很高兴为您服务！"
            emoji = "🙏"
        else:
            message = "嗨！很开心见到你！"
            emoji = "😊"
        
        await self.send_text(message)
        await self.send_type("emoji", emoji)
        
        return True, f"发送了{style}风格的问候"

class TimeCommand(BaseCommand):
    """时间查询Command"""

    command_pattern = r"^/time$"
    command_help = "查询当前时间"
    command_examples = ["/time"]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str]:
        import datetime
        
        now = datetime.datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        await self.send_text(f"⏰ 当前时间：{time_str}")
        
        return True, f"显示了当前时间: {time_str}"

@register_plugin
class HelloWorldPlugin(BasePlugin):
    """Hello World插件"""

    plugin_name = "hello_world_plugin"
    plugin_description = "Hello World演示插件"
    plugin_version = "1.0.0"
    plugin_author = "MaiBot Team"
    enable_plugin = True

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        return [
            (HelloAction.get_action_info(), HelloAction),
            (TimeCommand.get_command_info(
                name="time_query", 
                description="查询当前系统时间"
            ), TimeCommand),
        ]
```

### 配置文件

`plugins/hello_world_plugin/config.toml`:

```toml
[plugin]
name = "hello_world_plugin"
version = "1.0.0"
enabled = true

[greeting]
default_style = "casual"
enable_emoji = true

[time]
timezone = "Asia/Shanghai"
format = "%Y-%m-%d %H:%M:%S"
```

---

## 天气查询工具

展示如何创建Focus模式下的信息获取工具，专门用于扩展麦麦的信息获取能力。

### 功能说明
- **Focus模式专用**：仅在专注聊天模式下工作
- **自动调用**：LLM根据用户查询自动判断是否使用
- **信息增强**：为麦麦提供实时天气数据
- **必须启用工具处理器**

### 完整代码

`src/tools/tool_can_use/weather_tool.py`:

```python
from src.tools.tool_can_use.base_tool import BaseTool, register_tool
import aiohttp
import json

class WeatherTool(BaseTool):
    """天气查询工具 - 获取指定城市的实时天气信息"""
    
    # 工具名称，必须唯一
    name = "weather_query"
    
    # 工具描述，告诉LLM这个工具的用途
    description = "查询指定城市的实时天气信息，包括温度、湿度、天气状况等"
    
    # 参数定义，遵循JSONSchema格式
    parameters = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "要查询天气的城市名称，如：北京、上海、纽约"
            },
            "country": {
                "type": "string",
                "description": "国家代码，如：CN、US，可选参数"
            }
        },
        "required": ["city"]
    }
    
    async def execute(self, function_args, message_txt=""):
        """执行天气查询"""
        try:
            city = function_args.get("city")
            country = function_args.get("country", "")
            
            # 构建查询参数
            location = f"{city},{country}" if country else city
            
            # 调用天气API
            weather_data = await self._fetch_weather(location)
            
            # 格式化结果
            result = self._format_weather_data(weather_data)
            
            return {
                "name": self.name,
                "content": result
            }
            
        except Exception as e:
            return {
                "name": self.name,
                "content": f"天气查询失败: {str(e)}"
            }
    
    async def _fetch_weather(self, location: str) -> dict:
        """获取天气数据"""
        # 这里是示例，实际需要接入真实的天气API
        # 例如：OpenWeatherMap、和风天气等
        api_url = f"http://api.weather.com/v1/current?q={location}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                return await response.json()
    
    def _format_weather_data(self, data: dict) -> str:
        """格式化天气数据"""
        if not data:
            return "暂无天气数据"
        
        # 提取关键信息
        city = data.get("location", {}).get("name", "未知城市")
        temp = data.get("current", {}).get("temp_c", "未知")
        condition = data.get("current", {}).get("condition", {}).get("text", "未知")
        humidity = data.get("current", {}).get("humidity", "未知")
        
        # 格式化输出
        return f"""
🌤️ {city} 实时天气
━━━━━━━━━━━━━━━━━━
🌡️ 温度: {temp}°C
☁️ 天气: {condition}
💧 湿度: {humidity}%
━━━━━━━━━━━━━━━━━━
        """.strip()

# 注册工具（重要！必须调用）
register_tool(WeatherTool)
```

### 使用说明

1. **部署位置**：将文件放在 `src/tools/tool_can_use/` 目录下
2. **模式要求**：仅在Focus模式下可用
3. **配置要求**：必须开启工具处理器 `enable_tool_processor = True`
4. **自动调用**：用户发送"今天北京天气怎么样？"时，麦麦会自动调用此工具

---

## 知识搜索工具

展示如何创建知识查询工具，为麦麦提供百科知识和专业信息。

### 功能说明
- **知识增强**：扩展麦麦的知识获取能力
- **分类搜索**：支持科学、历史、技术等分类
- **多语言支持**：支持中英文结果
- **智能调用**：LLM自动判断何时需要知识查询

### 完整代码

`src/tools/tool_can_use/knowledge_search_tool.py`:

```python
from src.tools.tool_can_use.base_tool import BaseTool, register_tool
import aiohttp
import json

class KnowledgeSearchTool(BaseTool):
    """知识搜索工具 - 查询百科知识和专业信息"""
    
    name = "knowledge_search"
    description = "搜索百科知识、专业术语解释、历史事件等信息"
    
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要搜索的知识关键词或问题"
            },
            "category": {
                "type": "string",
                "description": "知识分类：science(科学)、history(历史)、technology(技术)、general(通用)等",
                "enum": ["science", "history", "technology", "general"]
            },
            "language": {
                "type": "string",
                "description": "结果语言：zh(中文)、en(英文)",
                "enum": ["zh", "en"]
            }
        },
        "required": ["query"]
    }
    
    async def execute(self, function_args, message_txt=""):
        """执行知识搜索"""
        try:
            query = function_args.get("query")
            category = function_args.get("category", "general")
            language = function_args.get("language", "zh")
            
            # 执行搜索逻辑
            search_results = await self._search_knowledge(query, category, language)
            
            # 格式化结果
            result = self._format_search_results(query, search_results)
            
            return {
                "name": self.name,
                "content": result
            }
            
        except Exception as e:
            return {
                "name": self.name,
                "content": f"知识搜索失败: {str(e)}"
            }
    
    async def _search_knowledge(self, query: str, category: str, language: str) -> list:
        """执行知识搜索"""
        # 这里实现实际的搜索逻辑
        # 可以对接维基百科API、百度百科API等
        
        # 示例API调用
        if language == "zh":
            api_url = f"https://zh.wikipedia.org/api/rest_v1/page/summary/{query}"
        else:
            api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{query}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    return [
                        {
                            "title": data.get("title", "无标题"),
                            "summary": data.get("extract", "无摘要"),
                            "source": "Wikipedia"
                        }
                    ]
                else:
                    return []
    
    def _format_search_results(self, query: str, results: list) -> str:
        """格式化搜索结果"""
        if not results:
            return f"未找到关于 '{query}' 的相关信息"
        
        formatted_text = f"📚 关于 '{query}' 的搜索结果:\n\n"
        
        for i, result in enumerate(results[:3], 1):  # 限制显示前3条
            title = result.get("title", "无标题")
            summary = result.get("summary", "无摘要")
            source = result.get("source", "未知来源")
            
            formatted_text += f"{i}. **{title}**\n"
            formatted_text += f"   {summary}\n"
            formatted_text += f"   📖 来源: {source}\n\n"
        
        return formatted_text.strip()

# 注册工具
register_tool(KnowledgeSearchTool)
```

### 配置示例

Focus模式配置文件示例：

```python
# 在Focus模式配置中
focus_config = {
    "enable_tool_processor": True,  # 必须启用工具处理器
    "tool_timeout": 30,             # 工具执行超时时间（秒）
    "max_tools_per_message": 3      # 单次消息最大工具调用数
}
```

### 使用流程

1. **用户查询**：用户在Focus模式下发送"什么是量子计算？"
2. **LLM判断**：麦麦识别这是知识查询需求
3. **工具调用**：自动调用 `knowledge_search` 工具
4. **信息获取**：工具查询相关知识信息
5. **整合回复**：麦麦将获取的信息整合到回复中

### 工具系统特点

- **🎯 专用性**：仅在Focus模式下工作，专注信息获取
- **🔍 智能性**：LLM自动判断何时需要使用工具
- **📊 丰富性**：为麦麦提供外部数据和实时信息
- **⚡ 高效性**：系统自动发现和注册工具
- **🔧 独立性**：目前需要单独编写，未来将更好融入插件系统

---

🎉 **这些示例展示了MaiBot插件系统的强大功能！根据你的需求选择合适的示例作为起点。**