# MaiBot 插件详细解析指南

## 📋 目录

1. [插件基类详解](#插件基类详解)
2. [Action组件深入](#action组件深入)
3. [Command组件深入](#command组件深入)
4. [API系统详解](#api系统详解)
5. [配置系统](#配置系统)
6. [注册中心机制](#注册中心机制)
7. [高级功能](#高级功能)
8. [最佳实践](#最佳实践)

---

## 插件基类详解

### BasePlugin 核心功能

`BasePlugin` 是所有插件的基类，提供插件的生命周期管理和基础功能。

```python
@register_plugin
class MyPlugin(BasePlugin):
    # 必需的基本信息
    plugin_name = "my_plugin"                    # 插件唯一标识
    plugin_description = "插件功能描述"           # 简短描述
    plugin_version = "1.0.0"                    # 版本号
    plugin_author = "作者名称"                   # 作者信息
    enable_plugin = True                         # 是否启用
    
    # 可选配置
    dependencies = ["other_plugin"]              # 依赖的其他插件
    config_file_name = "config.toml"             # 配置文件名
    
    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表（必须实现）"""
        return [
            (MyAction.get_action_info(), MyAction),
            (MyCommand.get_command_info(), MyCommand)
        ]
```

### 插件生命周期

1. **加载阶段** - 插件管理器扫描插件目录
2. **实例化阶段** - 创建插件实例，传入 `plugin_dir`
3. **配置加载** - 自动加载配置文件（如果指定）
4. **依赖检查** - 验证依赖的插件是否存在
5. **组件注册** - 注册所有组件到注册中心
6. **运行阶段** - 组件响应用户交互

### 配置访问

```python
class MyPlugin(BasePlugin):
    config_file_name = "config.toml"
    
    def some_method(self):
        # 获取配置值
        max_retry = self.get_config("network.max_retry", 3)
        api_key = self.get_config("api.key", "")
        
        # 配置支持嵌套结构
        db_config = self.get_config("database", {})
```

---

## Action组件深入

### Action激活机制

Action组件支持多种激活方式，可以组合使用：

#### 1. 关键词激活

```python
class KeywordAction(BaseAction):
    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD
    activation_keywords = ["天气", "weather", "温度"]
    keyword_case_sensitive = False  # 是否区分大小写
    
    async def execute(self) -> Tuple[bool, str]:
        # 获取触发的关键词
        triggered_keyword = self.action_data.get("triggered_keyword")
        return True, f"检测到关键词: {triggered_keyword}"
```

#### 2. LLM智能判断

```python
class SmartAction(BaseAction):
    focus_activation_type = ActionActivationType.LLM_JUDGE
    llm_judge_prompt = """
    判断用户消息是否表达了情感支持的需求。
    如果用户显得沮丧、焦虑或需要安慰，返回True，否则返回False。
    """
    
    async def execute(self) -> Tuple[bool, str]:
        # LLM判断为需要情感支持
        user_emotion = self.action_data.get("emotion", "neutral")
        return True, "我理解你现在的感受，有什么可以帮助你的吗？ 🤗"
```

#### 3. 随机激活

```python
class RandomAction(BaseAction):
    focus_activation_type = ActionActivationType.RANDOM
    random_activation_probability = 0.1  # 10%概率触发
    
    async def execute(self) -> Tuple[bool, str]:
        import random
        responses = ["今天天气不错呢！", "你知道吗，刚才想到一个有趣的事...", "随便聊聊吧！"]
        return True, random.choice(responses)
```

#### 4. 始终激活

```python
class AlwaysAction(BaseAction):
    focus_activation_type = ActionActivationType.ALWAYS
    parallel_action = True  # 允许与其他Action并行
    
    async def execute(self) -> Tuple[bool, str]:
        # 记录所有消息到数据库
        await self.api.store_user_data("last_message", self.action_data.get("message"))
        return True, ""  # 静默执行，不发送回复
```

### Action数据访问

```python
class DataAction(BaseAction):
    async def execute(self) -> Tuple[bool, str]:
        # 访问消息数据
        message = self.action_data.get("message", "")
        username = self.action_data.get("username", "用户")
        user_id = self.action_data.get("user_id", "")
        platform = self.action_data.get("platform", "")
        
        # 访问系统数据
        thinking_id = self.thinking_id
        reasoning = self.reasoning  # 执行该动作的理由
        
        # 访问计时器信息
        timers = self.cycle_timers
        
        return True, f"处理来自 {platform} 的用户 {username} 的消息"
```

### 聊天模式支持

```python
class ModeAwareAction(BaseAction):
    mode_enable = ChatMode.PRIVATE  # 只在私聊中启用
    # mode_enable = ChatMode.GROUP   # 只在群聊中启用
    # mode_enable = ChatMode.ALL     # 在所有模式中启用
    
    async def execute(self) -> Tuple[bool, str]:
        current_mode = self.action_data.get("chat_mode", ChatMode.PRIVATE)
        return True, f"当前聊天模式: {current_mode.name}"
```

---

## Command组件深入

### 高级正则表达式模式

Command使用正则表达式进行精确匹配，支持复杂的参数提取：

#### 1. 基础命令

```python
class BasicCommand(BaseCommand):
    command_pattern = r"^/hello$"
    command_help = "简单的问候命令"
    
    async def execute(self) -> Tuple[bool, Optional[str]]:
        await self.send_reply("Hello!")
        return True, "Hello!"
```

#### 2. 带参数命令

```python
class ParameterCommand(BaseCommand):
    command_pattern = r"^/user\s+(?P<action>add|remove|list)\s+(?P<name>\w+)?$"
    command_help = "用户管理命令，用法：/user <add|remove|list> [用户名]"
    command_examples = ["/user add alice", "/user remove bob", "/user list"]
    
    async def execute(self) -> Tuple[bool, Optional[str]]:
        action = self.matched_groups.get("action")
        name = self.matched_groups.get("name")
        
        if action == "add" and name:
            # 添加用户逻辑
            await self.api.store_user_data(f"user_{name}", {"name": name, "created": self.api.get_current_time()})
            response = f"用户 {name} 已添加"
        elif action == "remove" and name:
            # 删除用户逻辑
            await self.api.delete_user_data(f"user_{name}")
            response = f"用户 {name} 已删除"
        elif action == "list":
            # 列出用户逻辑
            users = await self.api.get_user_data_pattern("user_*")
            response = f"用户列表: {', '.join(users.keys())}"
        else:
            response = "参数错误，请查看帮助信息"
        
        await self.send_reply(response)
        return True, response
```

#### 3. 复杂参数解析

```python
class AdvancedCommand(BaseCommand):
    command_pattern = r"^/remind\s+(?P<time>\d{1,2}:\d{2})\s+(?P<date>\d{4}-\d{2}-\d{2})?\s+(?P<message>.+)$"
    command_help = "设置提醒，用法：/remind <时间> [日期] <消息>"
    command_examples = [
        "/remind 14:30 买牛奶",
        "/remind 09:00 2024-12-25 圣诞节快乐"
    ]
    
    async def execute(self) -> Tuple[bool, Optional[str]]:
        time_str = self.matched_groups.get("time")
        date_str = self.matched_groups.get("date")
        message = self.matched_groups.get("message")
        
        # 解析时间
        from datetime import datetime, date
        try:
            hour, minute = map(int, time_str.split(":"))
            if date_str:
                reminder_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            else:
                reminder_date = date.today()
            
            # 创建提醒
            reminder_time = datetime.combine(reminder_date, datetime.min.time().replace(hour=hour, minute=minute))
            
            await self.api.store_user_data("reminder", {
                "time": reminder_time.isoformat(),
                "message": message,
                "user_id": self.api.get_current_user_id()
            })
            
            response = f"已设置提醒：{reminder_time.strftime('%Y-%m-%d %H:%M')} - {message}"
            
        except ValueError as e:
            response = f"时间格式错误: {e}"
        
        await self.send_reply(response)
        return True, response
```

### 命令权限控制

```python
class AdminCommand(BaseCommand):
    command_pattern = r"^/admin\s+(?P<operation>\w+)"
    command_help = "管理员命令（需要权限）"
    
    async def execute(self) -> Tuple[bool, Optional[str]]:
        # 检查用户权限
        user_id = self.api.get_current_user_id()
        user_role = await self.api.get_user_info(user_id, "role", "user")
        
        if user_role != "admin":
            await self.send_reply("❌ 权限不足，需要管理员权限")
            return False, "权限不足"
        
        operation = self.matched_groups.get("operation")
        # 执行管理员操作...
        
        return True, f"管理员操作 {operation} 已执行"
```

---

## API系统详解

### MessageAPI - 消息发送

```python
class MessageExampleAction(BaseAction):
    async def execute(self) -> Tuple[bool, str]:
        # 发送文本消息
        await self.api.send_message("text", "这是一条文本消息")
        
        # 发送带格式的消息
        await self.api.send_message("text", "**粗体文本** *斜体文本*")
        
        # 发送图片（如果支持）
        await self.api.send_message("image", "/path/to/image.jpg")
        
        # 发送文件（如果支持）
        await self.api.send_message("file", "/path/to/document.pdf")
        
        # 获取消息发送状态
        success = await self.api.send_message("text", "测试消息")
        if success:
            logger.info("消息发送成功")
        
        return True, "消息发送演示完成"
```

### LLMAPI - 大模型调用

```python
class LLMExampleAction(BaseAction):
    async def execute(self) -> Tuple[bool, str]:
        # 获取可用模型
        models = self.api.get_available_models()
        
        if not models:
            return False, "没有可用的模型"
        
        # 选择第一个可用模型
        model_name, model_config = next(iter(models.items()))
        
        # 生成文本
        prompt = "写一首关于春天的诗"
        success, response, usage, model_used = await self.api.generate_with_model(
            prompt=prompt,
            model_config=model_config,
            max_tokens=200,
            temperature=0.7
        )
        
        if success:
            logger.info(f"使用模型 {model_used} 生成了 {usage.get('total_tokens', 0)} 个token")
            return True, f"生成的诗歌：\n{response}"
        else:
            return False, f"生成失败：{response}"
```

### DatabaseAPI - 数据库操作

```python
class DatabaseExampleAction(BaseAction):
    async def execute(self) -> Tuple[bool, str]:
        user_id = self.api.get_current_user_id()
        
        # 存储用户数据
        await self.api.store_user_data("user_score", 100)
        await self.api.store_user_data("user_level", "beginner")
        
        # 存储复杂数据结构
        user_profile = {
            "name": "Alice",
            "age": 25,
            "interests": ["music", "reading", "coding"],
            "settings": {
                "theme": "dark",
                "language": "zh-CN"
            }
        }
        await self.api.store_user_data("profile", user_profile)
        
        # 读取数据
        score = await self.api.get_user_data("user_score", 0)
        profile = await self.api.get_user_data("profile", {})
        
        # 删除数据
        await self.api.delete_user_data("old_key")
        
        # 批量查询
        all_user_data = await self.api.get_user_data_pattern("user_*")
        
        # 存储Action执行记录
        await self.api.store_action_info(
            action_build_into_prompt=True,
            action_prompt_display="用户查询了个人信息",
            action_done=True
        )
        
        return True, f"用户数据操作完成，当前积分：{score}"
```

### ConfigAPI - 配置访问

```python
class ConfigExampleAction(BaseAction):
    async def execute(self) -> Tuple[bool, str]:
        # 读取全局配置
        bot_name = self.api.get_global_config("bot.name", "MaiBot")
        debug_mode = self.api.get_global_config("system.debug", False)
        
        # 获取用户信息
        current_user = self.api.get_current_user_id()
        platform, user_id = await self.api.get_user_id_by_person_name("Alice")
        
        # 获取特定用户信息
        user_nickname = await self.api.get_person_info(current_user, "nickname", "未知用户")
        user_language = await self.api.get_person_info(current_user, "language", "zh-CN")
        
        return True, f"配置信息获取完成，机器人名称：{bot_name}"
```

### UtilsAPI - 工具函数

```python
class UtilsExampleAction(BaseAction):
    async def execute(self) -> Tuple[bool, str]:
        # 时间相关
        current_time = self.api.get_current_time()
        formatted_time = self.api.format_time(current_time, "%Y-%m-%d %H:%M:%S")
        
        # ID生成
        unique_id = self.api.generate_unique_id()
        random_string = self.api.generate_random_string(length=8)
        
        # 文件操作
        if self.api.file_exists("/path/to/file.txt"):
            content = self.api.read_file("/path/to/file.txt")
            self.api.write_file("/path/to/backup.txt", content)
        
        # JSON处理
        data = {"key": "value", "number": 42}
        json_str = self.api.to_json(data)
        parsed_data = self.api.from_json(json_str)
        
        # 安全字符串处理
        safe_filename = self.api.sanitize_filename("用户文件 (1).txt")
        
        return True, f"工具函数演示完成，时间：{formatted_time}"
```

---

## 配置系统

### TOML配置文件

```toml
# config.toml

[plugin]
name = "my_plugin"
description = "插件描述"
enabled = true
debug = false

[features]
enable_ai = true
enable_voice = false
max_users = 100

[api]
timeout = 30
retry_count = 3
base_url = "https://api.example.com"

[database]
cache_size = 1000
auto_cleanup = true

[messages]
welcome = "欢迎使用插件！"
error = "操作失败，请重试"
success = "操作成功完成"

[advanced]
custom_settings = { theme = "dark", language = "zh-CN" }
feature_flags = ["beta_feature", "experimental_ui"]
```

### 配置使用示例

```python
class ConfigurablePlugin(BasePlugin):
    config_file_name = "config.toml"
    
    def get_plugin_components(self):
        # 根据配置决定加载哪些组件
        components = []
        
        if self.get_config("features.enable_ai", False):
            components.append((AIAction.get_action_info(), AIAction))
        
        if self.get_config("features.enable_voice", False):
            components.append((VoiceCommand.get_command_info(), VoiceCommand))
        
        return components

class ConfigurableAction(BaseAction):
    async def execute(self) -> Tuple[bool, str]:
        # 注意：这里不能直接创建插件实例获取配置
        # 应该通过其他方式访问配置，比如从API或全局配置中获取
        
        # 使用默认值或硬编码配置
        welcome_message = "欢迎使用插件！"  # 应该从配置获取
        timeout = 30  # 应该从配置获取
        
        return True, welcome_message
```

---

## 注册中心机制

### 组件查询

```python
from src.plugin_system.core.component_registry import component_registry

# 获取所有注册的Action
actions = component_registry.get_components_by_type(ComponentType.ACTION)

# 获取所有注册的Command
commands = component_registry.get_components_by_type(ComponentType.COMMAND)

# 查找特定命令
command_info = component_registry.find_command_by_text("/help")

# 获取插件信息
plugin_info = component_registry.get_plugin_info("simple_plugin")

# 获取插件的所有组件
plugin_components = component_registry.get_plugin_components("simple_plugin")
```

### 动态组件操作

```python
# 注册新组件
component_info = ActionInfo(name="dynamic_action", ...)
component_registry.register_component(component_info, DynamicAction)

# 注销组件
component_registry.unregister_component("dynamic_action")

# 检查组件是否存在
exists = component_registry.component_exists("my_action")
```

---

## 高级功能

### 组件依赖管理

```python
class DependentPlugin(BasePlugin):
    plugin_name = "dependent_plugin"
    dependencies = ["simple_plugin", "core_plugin"]  # 依赖其他插件
    
    def get_plugin_components(self):
        # 只有在依赖满足时才会被调用
        return [(MyAction.get_action_info(), MyAction)]
```

### 动态组件创建

```python
def create_dynamic_action(keyword: str, response: str):
    """动态创建Action组件"""
    
    class DynamicAction(BaseAction):
        focus_activation_type = ActionActivationType.KEYWORD
        activation_keywords = [keyword]
        
        async def execute(self) -> Tuple[bool, str]:
            return True, response
    
    return DynamicAction

# 使用
WeatherAction = create_dynamic_action("天气", "今天天气很好！")
```

### 组件生命周期钩子

```python
class LifecycleAction(BaseAction):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.on_initialize()
    
    def on_initialize(self):
        """组件初始化时调用"""
        logger.info("Action组件初始化")
    
    async def execute(self) -> Tuple[bool, str]:
        result = await self.on_execute()
        self.on_complete()
        return result
    
    async def on_execute(self) -> Tuple[bool, str]:
        """实际执行逻辑"""
        return True, "执行完成"
    
    def on_complete(self):
        """执行完成后调用"""
        logger.info("Action执行完成")
```

---

## 最佳实践

### 1. 错误处理

```python
class RobustAction(BaseAction):
    async def execute(self) -> Tuple[bool, str]:
        try:
            # 主要逻辑
            result = await self.process_main_logic()
            return True, result
            
        except ValueError as e:
            # 参数错误
            logger.warning(f"参数错误: {e}")
            return False, "参数格式不正确"
            
        except ConnectionError as e:
            # 网络错误
            logger.error(f"网络连接失败: {e}")
            return False, "网络连接异常，请稍后重试"
            
        except Exception as e:
            # 未知错误
            logger.error(f"未知错误: {e}", exc_info=True)
            return False, "处理失败，请联系管理员"
    
    async def process_main_logic(self):
        # 具体业务逻辑
        pass
```

### 2. 性能优化

```python
class OptimizedAction(BaseAction):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}  # 本地缓存
    
    async def execute(self) -> Tuple[bool, str]:
        cache_key = self.generate_cache_key()
        
        # 检查缓存
        if cache_key in self._cache:
            logger.debug("使用缓存结果")
            return True, self._cache[cache_key]
        
        # 计算结果
        result = await self.compute_result()
        
        # 存储到缓存
        self._cache[cache_key] = result
        
        return True, result
    
    def generate_cache_key(self) -> str:
        # 根据输入生成缓存键
        message = self.action_data.get("message", "")
        return f"result_{hash(message)}"
```

### 3. 资源管理

```python
class ResourceAction(BaseAction):
    async def execute(self) -> Tuple[bool, str]:
        # 使用上下文管理器确保资源正确释放
        async with self.api.get_resource_manager() as resources:
            # 获取资源
            db_connection = await resources.get_database()
            file_handle = await resources.get_file("data.txt")
            
            # 使用资源进行处理
            result = await self.process_with_resources(db_connection, file_handle)
            
            return True, result
        # 资源会自动释放
```

### 4. 测试友好设计

```python
class TestableAction(BaseAction):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dependencies = self.create_dependencies()
    
    def create_dependencies(self):
        """创建依赖对象，便于测试时注入mock"""
        return {
            'weather_service': WeatherService(),
            'user_service': UserService()
        }
    
    async def execute(self) -> Tuple[bool, str]:
        weather = await self.dependencies['weather_service'].get_weather()
        user = await self.dependencies['user_service'].get_current_user()
        
        return True, f"今天{weather}，{user}！"
```

### 5. 日志记录

```python
class LoggedAction(BaseAction):
    async def execute(self) -> Tuple[bool, str]:
        start_time = self.api.get_current_time()
        
        logger.info(f"{self.log_prefix} 开始执行，用户: {self.action_data.get('username')}")
        
        try:
            result = await self.process()
            
            duration = self.api.get_current_time() - start_time
            logger.info(f"{self.log_prefix} 执行成功，耗时: {duration}ms")
            
            return True, result
            
        except Exception as e:
            logger.error(f"{self.log_prefix} 执行失败: {e}", exc_info=True)
            raise
```

---

## 总结

通过本详细指南，你已经深入了解了MaiBot插件系统的各个方面：

- **插件基类** - 生命周期管理和配置系统
- **Action组件** - 多种激活机制和智能交互
- **Command组件** - 强大的正则表达式匹配和参数处理
- **API系统** - 7大模块提供完整功能支持
- **高级功能** - 依赖管理、动态创建、生命周期钩子
- **最佳实践** - 错误处理、性能优化、资源管理

现在你已经具备了开发复杂插件的所有知识！

## 📚 相关文档

- [系统总览](plugin_guide_overview.md) - 了解整体架构
- [快速开始](plugin_quick_start.md) - 5分钟创建第一个插件
- [示例插件](../src/plugins/examples/simple_plugin/) - 完整功能参考

---

> 💡 **持续学习**: 插件开发是一个实践的过程，建议边学边做，逐步掌握各种高级特性！ 