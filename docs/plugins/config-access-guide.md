# 🔧 插件配置访问指南

## 问题描述

在插件开发中，你可能遇到这样的问题：
- `get_config`方法只在`BasePlugin`类中
- `BaseAction`和`BaseCommand`无法直接继承这个方法  
- 想要在Action或Command中访问插件配置

## ✅ 解决方案

**直接使用 `self.api.get_config()` 方法！**

系统已经自动为你处理了配置传递，你只需要通过`PluginAPI`访问配置即可。

## 📖 快速示例

### 在Action中访问配置

```python
from src.plugin_system import BaseAction

class MyAction(BaseAction):
    async def execute(self):
        # 方法1: 获取配置值（带默认值）
        api_key = self.api.get_config("api.key", "default_key")
        timeout = self.api.get_config("api.timeout", 30)
        
        # 方法2: 检查配置是否存在
        if self.api.has_config("features.premium"):
            premium_enabled = self.api.get_config("features.premium")
            # 使用高级功能
        
        # 方法3: 支持嵌套键访问
        log_level = self.api.get_config("advanced.logging.level", "INFO")
        
        # 方法4: 获取所有配置
        all_config = self.api.get_all_config()
        
        await self.send_text(f"API密钥: {api_key}")
        return True, "配置访问成功"
```

### 在Command中访问配置

```python
from src.plugin_system import BaseCommand

class MyCommand(BaseCommand):
    async def execute(self):
        # 使用方式与Action完全相同
        welcome_msg = self.api.get_config("messages.welcome", "欢迎！")
        max_results = self.api.get_config("search.max_results", 10)
        
        # 根据配置执行不同逻辑
        if self.api.get_config("features.debug_mode", False):
            await self.send_text(f"调试模式已启用，最大结果数: {max_results}")
        
        await self.send_text(welcome_msg)
        return True, "命令执行完成"
```

## 🔧 API方法详解

### 1. `get_config(key, default=None)`

获取配置值，支持嵌套键访问：

```python
# 简单键
value = self.api.get_config("timeout", 30)

# 嵌套键（用点号分隔）
value = self.api.get_config("database.connection.host", "localhost")
value = self.api.get_config("features.ai.model", "gpt-3.5-turbo")
```

### 2. `has_config(key)`

检查配置项是否存在：

```python
if self.api.has_config("api.secret_key"):
    # 配置存在，可以安全使用
    secret = self.api.get_config("api.secret_key")
else:
    # 配置不存在，使用默认行为
    pass
```

### 3. `get_all_config()`

获取所有配置的副本：

```python
all_config = self.api.get_all_config()
for section, config in all_config.items():
    print(f"配置节: {section}, 包含 {len(config)} 项配置")
```

## 📁 配置文件示例

假设你的插件有这样的配置文件 `config.toml`：

```toml
[api]
key = "your_api_key"
timeout = 30
base_url = "https://api.example.com"

[features]
enable_cache = true
debug_mode = false
max_retries = 3

[messages]
welcome = "欢迎使用我的插件！"
error = "出现了错误，请稍后重试"

[advanced]
[advanced.logging]
level = "INFO"
file_path = "logs/plugin.log"

[advanced.cache]
ttl_seconds = 3600
max_size = 100
```

## 🎯 实际使用案例

### 案例1：API调用配置

```python
class ApiAction(BaseAction):
    async def execute(self):
        # 获取API配置
        api_key = self.api.get_config("api.key")
        if not api_key:
            await self.send_text("❌ API密钥未配置")
            return False, "缺少API密钥"
        
        timeout = self.api.get_config("api.timeout", 30)
        base_url = self.api.get_config("api.base_url", "https://api.example.com")
        
        # 使用配置进行API调用
        # ... API调用逻辑
        
        return True, "API调用完成"
```

### 案例2：功能开关配置

```python
class FeatureCommand(BaseCommand):
    async def execute(self):
        # 检查功能开关
        if not self.api.get_config("features.enable_cache", True):
            await self.send_text("缓存功能已禁用")
            return True, "功能被禁用"
        
        # 检查调试模式
        debug_mode = self.api.get_config("features.debug_mode", False)
        if debug_mode:
            await self.send_text("🐛 调试模式已启用")
        
        max_retries = self.api.get_config("features.max_retries", 3)
        # 使用重试配置
        
        return True, "功能执行完成"
```

### 案例3：个性化消息配置

```python
class WelcomeAction(BaseAction):
    async def execute(self):
        # 获取个性化消息
        welcome_msg = self.api.get_config("messages.welcome", "欢迎！")
        
        # 检查是否有自定义问候语列表
        if self.api.has_config("messages.custom_greetings"):
            greetings = self.api.get_config("messages.custom_greetings", [])
            if greetings:
                import random
                welcome_msg = random.choice(greetings)
        
        await self.send_text(welcome_msg)
        return True, "发送了个性化问候"
```

## 🔄 配置传递机制

系统自动处理配置传递，无需手动操作：

1. **插件初始化** → `BasePlugin`加载`config.toml`到`self.config`
2. **组件注册** → 系统记录插件配置
3. **组件实例化** → 自动传递`plugin_config`参数给Action/Command
4. **API初始化** → 配置保存到`PluginAPI`实例中
5. **组件使用** → 通过`self.api.get_config()`访问

## ⚠️ 注意事项

### 1. 总是提供默认值

```python
# ✅ 好的做法
timeout = self.api.get_config("api.timeout", 30)

# ❌ 避免这样做
timeout = self.api.get_config("api.timeout")  # 可能返回None
```

### 2. 验证配置类型

```python
# 获取配置后验证类型
max_items = self.api.get_config("list.max_items", 10)
if not isinstance(max_items, int) or max_items <= 0:
    max_items = 10  # 使用安全的默认值
```

### 3. 缓存复杂配置解析

```python
class MyAction(BaseAction):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 在初始化时解析复杂配置，避免重复解析
        self._api_config = self._parse_api_config()
    
    def _parse_api_config(self):
        return {
            'key': self.api.get_config("api.key", ""),
            'timeout': self.api.get_config("api.timeout", 30),
            'retries': self.api.get_config("api.max_retries", 3)
        }
```

## 🎉 总结

现在你知道了！在Action和Command中访问配置很简单：

```python
# 这就是你需要的全部代码！
config_value = self.api.get_config("your.config.key", "default_value")
```

不需要继承`BasePlugin`，不需要复杂的配置传递，`PluginAPI`已经为你准备好了一切！ 