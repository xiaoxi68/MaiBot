# API使用指南

插件系统提供了多种API访问方式，根据使用场景选择合适的API类。

## 📊 API分类

### 🔗 ActionAPI - 需要Action依赖
**适用场景**：在Action组件中使用，需要访问聊天上下文
```python
from src.plugin_system.apis import ActionAPI

class MyAction(BaseAction):
    async def execute(self):
        # Action已内置ActionAPI，可以直接使用
        await self.api.send_message("text", "Hello")
        await self.api.store_action_info(action_prompt_display="执行了动作")
```

**包含功能**：
- ✅ 发送消息（需要chat_stream、expressor等）
- ✅ 数据库操作（需要thinking_id、action_data等）

### 🔧 IndependentAPI - 独立功能
**适用场景**：在Command组件中使用，或需要独立工具功能
```python
from src.plugin_system.apis import IndependentAPI

class MyCommand(BaseCommand):
    async def execute(self):
        # 创建独立API实例
        api = IndependentAPI(log_prefix="[MyCommand]")
        
        # 使用独立功能
        models = api.get_available_models()
        config = api.get_global_config("some_key")
        timestamp = api.get_timestamp()
```

**包含功能**：
- ✅ LLM模型调用
- ✅ 配置读取
- ✅ 工具函数（时间、文件、ID生成等）
- ✅ 聊天流查询
- ✅ 心流状态控制

### ⚡ StaticAPI - 静态访问
**适用场景**：简单工具调用，不需要实例化
```python
from src.plugin_system.apis import StaticAPI

# 直接调用静态方法
models = StaticAPI.get_available_models()
config = StaticAPI.get_global_config("bot.nickname")
timestamp = StaticAPI.get_timestamp()
unique_id = StaticAPI.generate_unique_id()

# 异步方法
result = await StaticAPI.generate_with_model(prompt, model_config)
chat_stream = StaticAPI.get_chat_stream_by_group_id("123456")
```

## 🎯 使用建议

### Action组件开发
```python
class MyAction(BaseAction):
    # 激活条件直接在类中定义
    focus_activation_type = ActionActivationType.KEYWORD
    activation_keywords = ["测试"]
    
    async def execute(self):
        # 使用内置的ActionAPI
        success = await self.api.send_message("text", "处理中...")
        
        # 存储执行记录
        await self.api.store_action_info(
            action_prompt_display="执行了测试动作"
        )
        
        return True, "完成"
```

### Command组件开发
```python
class MyCommand(BaseCommand):
    # 命令模式直接在类中定义
    command_pattern = r"^/test\s+(?P<param>\w+)$"
    command_help = "测试命令"
    
    async def execute(self):
        # 使用独立API
        api = IndependentAPI(log_prefix="[TestCommand]")
        
        # 获取配置
        max_length = api.get_global_config("test.max_length", 100)
        
        # 生成内容（如果需要）
        if api.get_available_models():
            models = api.get_available_models()
            first_model = list(models.values())[0]
            
            success, response, _, _ = await api.generate_with_model(
                "生成测试回复", first_model
            )
            
            if success:
                await self.send_reply(response)
```

### 独立工具使用
```python
# 不在插件环境中的独立使用
from src.plugin_system.apis import StaticAPI

def some_utility_function():
    # 获取配置
    bot_name = StaticAPI.get_global_config("bot.nickname", "Bot")
    
    # 生成ID
    request_id = StaticAPI.generate_unique_id()
    
    # 格式化时间
    current_time = StaticAPI.format_time()
    
    return f"{bot_name}_{request_id}_{current_time}"
```

## 🔄 迁移指南

### 从原PluginAPI迁移

**原来的用法**：
```python
# 原来需要导入完整PluginAPI
from src.plugin_system.apis import PluginAPI

api = PluginAPI(chat_stream=..., expressor=...)
await api.send_message("text", "Hello")
config = api.get_global_config("key")
```

**新的用法**：
```python
# 方式1：继续使用原PluginAPI（不变）
from src.plugin_system.apis import PluginAPI

# 方式2：使用分类API（推荐）
from src.plugin_system.apis import ActionAPI, IndependentAPI

# Action相关功能
action_api = ActionAPI(chat_stream=..., expressor=...)
await action_api.send_message("text", "Hello")

# 独立功能
config = IndependentAPI().get_global_config("key")
# 或者
config = StaticAPI.get_global_config("key")
```

## 📋 API对照表

| 功能类别 | 原PluginAPI | ActionAPI | IndependentAPI | StaticAPI |
|---------|-------------|-----------|----------------|-----------|
| 发送消息 | ✅ | ✅ | ❌ | ❌ |
| 数据库操作 | ✅ | ✅ | ❌ | ❌ |
| LLM调用 | ✅ | ❌ | ✅ | ✅ |
| 配置读取 | ✅ | ❌ | ✅ | ✅ |
| 工具函数 | ✅ | ❌ | ✅ | ✅ |
| 聊天流查询 | ✅ | ❌ | ✅ | ✅ |
| 心流控制 | ✅ | ❌ | ✅ | ✅ |

这样的分类让插件开发者可以更明确地知道需要什么样的API，避免不必要的依赖注入。 