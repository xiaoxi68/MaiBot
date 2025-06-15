# 📖 插件配置访问完整示例

> 这个示例展示了如何在Action和Command组件中正确访问插件的配置文件。

## 🎯 问题背景

在插件开发过程中，你可能遇到这样的问题：
- `get_config`方法只在`BasePlugin`类中
- `BaseAction`和`BaseCommand`无法直接继承这个方法
- 想要在Action或Command中访问插件配置

## ✅ 解决方案

通过`self.api.get_config()`方法访问配置，系统会自动将插件配置传递给组件。

## 📁 完整示例

### 1. 插件配置文件

创建 `config.toml`：

```toml
[greeting]
default_style = "casual"
enable_emoji = true
custom_messages = [
    "你好呀！",
    "嗨！很高兴见到你！",
    "哈喽！"
]

[database]
enabled = true
table_prefix = "hello_"
max_records = 1000

[features]
enable_weather = false
enable_jokes = true
api_timeout = 30

[advanced.logging]
level = "INFO"
file_path = "logs/hello_plugin.log"

[advanced.cache]
enabled = true
ttl_seconds = 3600
max_size = 100
```

### 2. 插件主文件

创建 `plugin.py`：

```python
"""
配置访问示例插件
展示如何在Action和Command中访问配置
"""

from src.plugin_system import (
    BasePlugin, 
    BaseAction, 
    BaseCommand,
    register_plugin,
    ActionInfo,
    CommandInfo,
    PythonDependency,
    ActionActivationType
)
from src.common.logger import get_logger

logger = get_logger("config_example_plugin")


@register_plugin
class ConfigExamplePlugin(BasePlugin):
    """配置访问示例插件"""
    
    plugin_name = "config_example_plugin"
    plugin_description = "展示如何在组件中访问配置的示例插件"
    plugin_version = "1.0.0"
    plugin_author = "MaiBot Team"
    config_file_name = "config.toml"
    
    def get_plugin_components(self):
        """返回插件组件"""
        return [
            (ActionInfo(
                name="config_greeting_action",
                description="使用配置的问候Action",
                focus_activation_type=ActionActivationType.KEYWORD,
                normal_activation_type=ActionActivationType.KEYWORD,
                activation_keywords=["配置问候", "config hello"],
            ), ConfigGreetingAction),
            
            (CommandInfo(
                name="config_status",
                description="显示配置状态",
                command_pattern=r"^/config\s*(status|show)?$",
                command_help="显示插件配置状态",
                command_examples=["/config", "/config status"],
            ), ConfigStatusCommand),
            
            (CommandInfo(
                name="config_test",
                description="测试配置访问",
                command_pattern=r"^/config\s+test\s+(?P<key>\S+)$",
                command_help="测试访问指定配置项",
                command_examples=["/config test greeting.default_style"],
            ), ConfigTestCommand),
        ]


class ConfigGreetingAction(BaseAction):
    """使用配置的问候Action"""
    
    async def execute(self):
        """执行配置化的问候"""
        try:
            # 方法1: 直接访问配置项
            style = self.api.get_config("greeting.default_style", "casual")
            enable_emoji = self.api.get_config("greeting.enable_emoji", True)
            
            # 方法2: 检查配置是否存在
            if self.api.has_config("greeting.custom_messages"):
                messages = self.api.get_config("greeting.custom_messages", [])
                if messages:
                    # 随机选择一个问候语
                    import random
                    message = random.choice(messages)
                else:
                    message = "你好！"
            else:
                # 使用默认问候语
                if style == "formal":
                    message = "您好！很高兴为您服务！"
                else:
                    message = "嗨！很开心见到你！"
            
            # 添加表情符号
            if enable_emoji:
                emoji = "😊" if style == "casual" else "🙏"
                message += emoji
            
            # 发送问候消息
            await self.send_text(message)
            
            # 记录到数据库（如果启用）
            await self._save_greeting_record(style, message)
            
            return True, f"发送了{style}风格的配置化问候"
            
        except Exception as e:
            logger.error(f"配置问候执行失败: {e}")
            await self.send_text("抱歉，问候功能遇到了问题")
            return False, f"执行失败: {str(e)}"
    
    async def _save_greeting_record(self, style: str, message: str):
        """保存问候记录到数据库"""
        try:
            # 检查数据库功能是否启用
            if not self.api.get_config("database.enabled", False):
                return
            
            # 获取数据库配置
            table_prefix = self.api.get_config("database.table_prefix", "hello_")
            max_records = self.api.get_config("database.max_records", 1000)
            
            # 构造记录数据
            record_data = {
                "style": style,
                "message": message,
                "timestamp": "now",  # 实际应用中使用datetime
                "user_id": "demo_user"  # 从context获取真实用户ID
            }
            
            # 这里应该调用数据库API保存记录
            logger.info(f"保存问候记录到 {table_prefix}greetings: {record_data}")
            
        except Exception as e:
            logger.error(f"保存问候记录失败: {e}")


class ConfigStatusCommand(BaseCommand):
    """显示配置状态Command"""
    
    async def execute(self):
        """显示插件配置状态"""
        try:
            # 获取所有配置
            all_config = self.api.get_all_config()
            
            if not all_config:
                await self.send_text("❌ 没有找到配置文件")
                return True, "没有配置文件"
            
            # 构建状态报告
            status_lines = ["📋 插件配置状态:", ""]
            
            # 问候配置
            greeting_config = all_config.get("greeting", {})
            if greeting_config:
                status_lines.append("🎯 问候配置:")
                status_lines.append(f"  - 默认风格: {greeting_config.get('default_style', 'N/A')}")
                status_lines.append(f"  - 启用表情: {'✅' if greeting_config.get('enable_emoji') else '❌'}")
                custom_msgs = greeting_config.get('custom_messages', [])
                status_lines.append(f"  - 自定义消息: {len(custom_msgs)}条")
                status_lines.append("")
            
            # 数据库配置
            db_config = all_config.get("database", {})
            if db_config:
                status_lines.append("🗄️ 数据库配置:")
                status_lines.append(f"  - 状态: {'✅ 启用' if db_config.get('enabled') else '❌ 禁用'}")
                status_lines.append(f"  - 表前缀: {db_config.get('table_prefix', 'N/A')}")
                status_lines.append(f"  - 最大记录: {db_config.get('max_records', 'N/A')}")
                status_lines.append("")
            
            # 功能配置
            features_config = all_config.get("features", {})
            if features_config:
                status_lines.append("🔧 功能配置:")
                for feature, enabled in features_config.items():
                    if isinstance(enabled, bool):
                        status_lines.append(f"  - {feature}: {'✅' if enabled else '❌'}")
                    else:
                        status_lines.append(f"  - {feature}: {enabled}")
                status_lines.append("")
            
            # 高级配置
            advanced_config = all_config.get("advanced", {})
            if advanced_config:
                status_lines.append("⚙️ 高级配置:")
                for section, config in advanced_config.items():
                    status_lines.append(f"  - {section}: {len(config) if isinstance(config, dict) else 1}项")
            
            # 发送状态报告
            status_text = "\n".join(status_lines)
            await self.send_text(status_text)
            
            return True, "显示了配置状态"
            
        except Exception as e:
            logger.error(f"获取配置状态失败: {e}")
            await self.send_text(f"❌ 获取配置状态失败: {str(e)}")
            return False, f"获取失败: {str(e)}"


class ConfigTestCommand(BaseCommand):
    """测试配置访问Command"""
    
    async def execute(self):
        """测试访问指定的配置项"""
        try:
            # 获取要测试的配置键
            config_key = self.matched_groups.get("key", "")
            
            if not config_key:
                await self.send_text("❌ 请指定要测试的配置项\n用法: /config test <key>")
                return True, "缺少配置键参数"
            
            # 测试配置访问的不同方法
            result_lines = [f"🔍 测试配置项: `{config_key}`", ""]
            
            # 方法1: 检查是否存在
            exists = self.api.has_config(config_key)
            result_lines.append(f"📋 配置存在: {'✅ 是' if exists else '❌ 否'}")
            
            if exists:
                # 方法2: 获取配置值
                config_value = self.api.get_config(config_key)
                value_type = type(config_value).__name__
                
                result_lines.append(f"📊 数据类型: {value_type}")
                
                # 根据类型显示值
                if isinstance(config_value, (str, int, float, bool)):
                    result_lines.append(f"💾 配置值: {config_value}")
                elif isinstance(config_value, list):
                    result_lines.append(f"📝 列表长度: {len(config_value)}")
                    if config_value:
                        result_lines.append(f"📋 首项: {config_value[0]}")
                elif isinstance(config_value, dict):
                    result_lines.append(f"🗂️ 字典大小: {len(config_value)}项")
                    if config_value:
                        keys = list(config_value.keys())[:3]
                        result_lines.append(f"🔑 键示例: {', '.join(keys)}")
                else:
                    result_lines.append(f"💾 配置值: {str(config_value)[:100]}...")
                
                # 方法3: 测试默认值
                test_default = self.api.get_config(config_key, "DEFAULT_VALUE")
                if test_default != "DEFAULT_VALUE":
                    result_lines.append("✅ 默认值机制正常")
                else:
                    result_lines.append("⚠️ 配置值为空或等于测试默认值")
            else:
                # 测试默认值返回
                default_value = self.api.get_config(config_key, "NOT_FOUND")
                result_lines.append(f"🔄 默认值返回: {default_value}")
            
            # 显示相关配置项
            if "." in config_key:
                section = config_key.split(".")[0]
                all_config = self.api.get_all_config()
                section_config = all_config.get(section, {})
                if section_config and isinstance(section_config, dict):
                    related_keys = list(section_config.keys())[:5]
                    result_lines.append("")
                    result_lines.append(f"🔗 相关配置项 ({section}):")
                    for key in related_keys:
                        full_key = f"{section}.{key}"
                        status = "✅" if self.api.has_config(full_key) else "❌"
                        result_lines.append(f"  {status} {full_key}")
            
            # 发送测试结果
            result_text = "\n".join(result_lines)
            await self.send_text(result_text)
            
            return True, f"测试了配置项: {config_key}"
            
        except Exception as e:
            logger.error(f"配置测试失败: {e}")
            await self.send_text(f"❌ 配置测试失败: {str(e)}")
            return False, f"测试失败: {str(e)}"


# 演示代码
async def demo_config_access():
    """演示配置访问功能"""
    
    print("🔧 插件配置访问演示")
    print("=" * 50)
    
    # 模拟插件配置
    mock_config = {
        "greeting": {
            "default_style": "casual",
            "enable_emoji": True,
            "custom_messages": ["你好呀！", "嗨！很高兴见到你！"]
        },
        "database": {
            "enabled": True,
            "table_prefix": "hello_",
            "max_records": 1000
        },
        "advanced": {
            "logging": {
                "level": "INFO",
                "file_path": "logs/hello_plugin.log"
            }
        }
    }
    
    # 创建模拟API
    from src.plugin_system.apis.plugin_api import PluginAPI
    api = PluginAPI(plugin_config=mock_config)
    
    print("\n📋 配置访问测试:")
    
    # 测试1: 基本配置访问
    style = api.get_config("greeting.default_style", "unknown")
    print(f"  问候风格: {style}")
    
    # 测试2: 布尔值配置
    enable_emoji = api.get_config("greeting.enable_emoji", False)
    print(f"  启用表情: {enable_emoji}")
    
    # 测试3: 列表配置
    messages = api.get_config("greeting.custom_messages", [])
    print(f"  自定义消息: {len(messages)}条")
    
    # 测试4: 深层嵌套配置
    log_level = api.get_config("advanced.logging.level", "INFO")
    print(f"  日志级别: {log_level}")
    
    # 测试5: 不存在的配置
    unknown = api.get_config("unknown.config", "default")
    print(f"  未知配置: {unknown}")
    
    # 测试6: 配置存在检查
    exists1 = api.has_config("greeting.default_style")
    exists2 = api.has_config("nonexistent.config")
    print(f"  greeting.default_style 存在: {exists1}")
    print(f"  nonexistent.config 存在: {exists2}")
    
    # 测试7: 获取所有配置
    all_config = api.get_all_config()
    print(f"  总配置节数: {len(all_config)}")
    
    print("\n✅ 配置访问测试完成！")


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo_config_access())
```

## 🎯 核心要点

### 1. 在Action中访问配置

```python
class MyAction(BaseAction):
    async def execute(self):
        # 基本配置访问
        value = self.api.get_config("section.key", "default")
        
        # 检查配置是否存在
        if self.api.has_config("section.key"):
            # 配置存在，执行相应逻辑
            pass
        
        # 获取所有配置
        all_config = self.api.get_all_config()
```

### 2. 在Command中访问配置

```python
class MyCommand(BaseCommand):
    async def execute(self):
        # 访问配置的方法与Action完全相同
        value = self.api.get_config("section.key", "default")
        
        # 支持嵌套键访问
        nested_value = self.api.get_config("section.subsection.key")
```

### 3. 配置传递机制

系统会自动处理配置传递：
1. `BasePlugin`加载配置文件到`self.config`
2. 组件注册时，系统通过`component_registry.get_plugin_config()`获取配置
3. Action/Command实例化时，配置作为`plugin_config`参数传递
4. `PluginAPI`初始化时保存配置到`self._plugin_config`
5. 组件通过`self.api.get_config()`访问配置

## 🔧 使用这个示例

### 1. 创建插件目录

```bash
mkdir plugins/config_example_plugin
cd plugins/config_example_plugin
```

### 2. 复制文件

- 将配置文件保存为 `config.toml`
- 将插件代码保存为 `plugin.py`

### 3. 测试功能

```bash
# 启动MaiBot后测试以下命令：

# 测试配置状态显示
/config status

# 测试特定配置项
/config test greeting.default_style
/config test database.enabled
/config test advanced.logging.level

# 触发配置化问候
配置问候
```

## 💡 最佳实践

### 1. 提供合理的默认值

```python
# 总是提供默认值
timeout = self.api.get_config("api.timeout", 30)
enabled = self.api.get_config("feature.enabled", False)
```

### 2. 验证配置类型

```python
# 验证配置类型
max_items = self.api.get_config("list.max_items", 10)
if not isinstance(max_items, int) or max_items <= 0:
    max_items = 10  # 使用安全的默认值
```

### 3. 缓存复杂配置

```python
class MyAction(BaseAction):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 缓存复杂配置避免重复解析
        self._cached_config = self._parse_complex_config()
    
    def _parse_complex_config(self):
        # 解析复杂配置逻辑
        return processed_config
```

### 4. 配置变更检测

```python
# 对于支持热更新的配置
last_config_hash = None

def check_config_changes(self):
    current_config = self.api.get_all_config()
    current_hash = hash(str(current_config))
    
    if current_hash != self.last_config_hash:
        self.last_config_hash = current_hash
        self._reload_config()
```

通过这种方式，你的Action和Command组件可以灵活地访问插件配置，实现更加强大和可定制的功能！ 