# 📡 消息API

## 📖 概述

消息API提供了发送各种类型消息的接口，支持文本、表情、图片等多种消息类型，以及向不同目标发送消息的功能。

## 🔄 基础消息发送

### 发送文本消息

```python
# 发送普通文本消息
await self.send_text("这是一条文本消息")

# 发送多行文本
message = """
这是第一行
这是第二行
这是第三行
"""
await self.send_text(message.strip())
```

### 发送特定类型消息

```python
# 发送表情
await self.send_type("emoji", "😊")

# 发送图片
await self.send_type("image", "https://example.com/image.jpg")

# 发送音频
await self.send_type("audio", "audio_file_path")
```

### 发送命令消息

```python
# 发送命令类型的消息
await self.send_command("system_command", {"param": "value"})
```

## 🎯 目标消息发送

### 向指定群聊发送消息

```python
# 向指定群聊发送文本消息
success = await self.api.send_text_to_group(
    text="这是发送到群聊的消息",
    group_id="123456789",
    platform="qq"
)

if success:
    print("消息发送成功")
else:
    print("消息发送失败")
```

### 向指定用户发送私聊消息

```python
# 向指定用户发送私聊消息
success = await self.api.send_text_to_user(
    text="这是私聊消息",
    user_id="987654321", 
    platform="qq"
)
```

### 通用目标消息发送

```python
# 向任意目标发送任意类型消息
success = await self.api.send_message_to_target(
    message_type="text",           # 消息类型
    content="消息内容",            # 消息内容
    platform="qq",                # 平台
    target_id="123456789",        # 目标ID
    is_group=True,                # 是否为群聊
    display_message="显示消息"     # 可选：显示消息
)
```

## 📨 消息类型支持

### 支持的消息类型

| 类型 | 说明 | 示例 |
|-----|------|------|
| `text` | 普通文本消息 | "Hello World" |
| `emoji` | 表情消息 | "😊" |
| `image` | 图片消息 | 图片URL或路径 |
| `audio` | 音频消息 | 音频文件路径 |
| `video` | 视频消息 | 视频文件路径 |
| `file` | 文件消息 | 文件路径 |

### 消息类型示例

```python
# 文本消息
await self.send_type("text", "普通文本")

# 表情消息
await self.send_type("emoji", "🎉")

# 图片消息
await self.send_type("image", "/path/to/image.jpg")

# 音频消息
await self.send_type("audio", "/path/to/audio.mp3")

# 文件消息
await self.send_type("file", "/path/to/document.pdf")
```

## 🔍 消息查询

### 获取聊天类型

```python
# 获取当前聊天类型
chat_type = self.api.get_chat_type()

if chat_type == "group":
    print("当前是群聊")
elif chat_type == "private":
    print("当前是私聊")
```

### 获取最近消息

```python
# 获取最近的5条消息
recent_messages = self.api.get_recent_messages(count=5)

for message in recent_messages:
    print(f"用户: {message.user_nickname}")
    print(f"内容: {message.processed_plain_text}")
    print(f"时间: {message.timestamp}")
```

### 获取当前消息信息

```python
# 在Action或Command中获取当前处理的消息
current_message = self.message

# 消息基本信息
user_id = current_message.message_info.user_info.user_id
user_nickname = current_message.message_info.user_info.user_nickname
message_content = current_message.processed_plain_text
timestamp = current_message.timestamp

# 群聊信息（如果是群聊）
if current_message.message_info.group_info:
    group_id = current_message.message_info.group_info.group_id
    group_name = current_message.message_info.group_info.group_name
```

## 🌐 平台支持

### 支持的平台

| 平台 | 标识 | 说明 |
|-----|------|------|
| QQ | `qq` | QQ聊天平台 |
| 微信 | `wechat` | 微信聊天平台 |
| Discord | `discord` | Discord聊天平台 |

### 平台特定功能

```python
# 获取当前平台
current_platform = self.api.get_current_platform()

# 根据平台调整消息格式
if current_platform == "qq":
    # QQ平台特定处理
    await self.send_text("[QQ] 消息内容")
elif current_platform == "wechat":
    # 微信平台特定处理
    await self.send_text("【微信】消息内容")
```

## 🎨 消息格式化

### Markdown支持

```python
# 发送Markdown格式的消息（如果平台支持）
markdown_message = """
**粗体文本**
*斜体文本*
`代码块`
[链接](https://example.com)
"""

await self.send_text(markdown_message)
```

### 消息模板

```python
# 使用模板生成消息
def format_user_info(username: str, level: int, points: int) -> str:
    return f"""
👤 用户信息
━━━━━━━━━━━━━━━━━━
📛 用户名: {username}
⭐ 等级: Lv.{level}
💰 积分: {points:,}
━━━━━━━━━━━━━━━━━━
    """.strip()

# 使用模板
user_info = format_user_info("张三", 15, 12580)
await self.send_text(user_info)
```

### 表情和Unicode

```python
# 发送Unicode表情
await self.send_text("消息发送成功 ✅")

# 发送表情包
await self.send_type("emoji", "🎉")

# 组合文本和表情
await self.send_text("恭喜你完成任务！🎊🎉")
```

## 🔄 流式消息

### 获取聊天流信息

```python
# 获取当前聊天流
chat_stream = self.api.get_service("chat_stream")

if chat_stream:
    # 流基本信息
    stream_id = chat_stream.stream_id
    platform = chat_stream.platform
    
    # 群聊信息
    if chat_stream.group_info:
        group_id = chat_stream.group_info.group_id
        group_name = chat_stream.group_info.group_name
        print(f"当前群聊: {group_name} ({group_id})")
    
    # 用户信息
    user_id = chat_stream.user_info.user_id
    user_name = chat_stream.user_info.user_nickname
    print(f"当前用户: {user_name} ({user_id})")
```

## 🚨 错误处理

### 消息发送错误处理

```python
async def safe_send_message(self, content: str) -> bool:
    """安全发送消息，包含错误处理"""
    try:
        await self.send_text(content)
        return True
    except Exception as e:
        logger.error(f"消息发送失败: {e}")
        # 发送错误提示
        try:
            await self.send_text("❌ 消息发送失败，请稍后重试")
        except:
            pass  # 避免循环错误
        return False
```

### 目标消息发送错误处理

```python
async def send_to_group_safely(self, text: str, group_id: str) -> bool:
    """安全向群聊发送消息"""
    try:
        success = await self.api.send_text_to_group(
            text=text,
            group_id=group_id,
            platform="qq"
        )
        
        if not success:
            logger.warning(f"向群聊 {group_id} 发送消息失败")
            
        return success
        
    except Exception as e:
        logger.error(f"向群聊发送消息异常: {e}")
        return False
```

## 📊 最佳实践

### 1. 消息长度控制

```python
async def send_long_message(self, content: str, max_length: int = 500):
    """发送长消息，自动分段"""
    if len(content) <= max_length:
        await self.send_text(content)
    else:
        # 分段发送
        parts = [content[i:i+max_length] for i in range(0, len(content), max_length)]
        for i, part in enumerate(parts):
            prefix = f"[{i+1}/{len(parts)}] " if len(parts) > 1 else ""
            await self.send_text(f"{prefix}{part}")
            
            # 避免发送过快
            if i < len(parts) - 1:
                await asyncio.sleep(0.5)
```

### 2. 消息格式规范

```python
class MessageFormatter:
    """消息格式化工具类"""
    
    @staticmethod
    def success(message: str) -> str:
        return f"✅ {message}"
    
    @staticmethod
    def error(message: str) -> str:
        return f"❌ {message}"
    
    @staticmethod
    def warning(message: str) -> str:
        return f"⚠️ {message}"
    
    @staticmethod
    def info(message: str) -> str:
        return f"ℹ️ {message}"

# 使用示例
await self.send_text(MessageFormatter.success("操作成功完成"))
await self.send_text(MessageFormatter.error("操作失败，请重试"))
```

### 3. 异步消息处理

```python
async def batch_send_messages(self, messages: List[str]):
    """批量发送消息"""
    tasks = []
    
    for message in messages:
        task = self.send_text(message)
        tasks.append(task)
    
    # 并发发送，但控制并发数
    semaphore = asyncio.Semaphore(3)  # 最多3个并发
    
    async def send_with_limit(message):
        async with semaphore:
            await self.send_text(message)
    
    await asyncio.gather(*[send_with_limit(msg) for msg in messages])
```

### 4. 消息缓存

```python
class MessageCache:
    """消息缓存管理"""
    
    def __init__(self):
        self._cache = {}
        self._max_size = 100
    
    def get_cached_message(self, key: str) -> Optional[str]:
        return self._cache.get(key)
    
    def cache_message(self, key: str, message: str):
        if len(self._cache) >= self._max_size:
            # 删除最旧的缓存
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        
        self._cache[key] = message

# 使用缓存避免重复生成消息
cache = MessageCache()

async def send_user_info(self, user_id: str):
    cache_key = f"user_info_{user_id}"
    cached_message = cache.get_cached_message(cache_key)
    
    if cached_message:
        await self.send_text(cached_message)
    else:
        # 生成新消息
        message = await self._generate_user_info(user_id)
        cache.cache_message(cache_key, message)
        await self.send_text(message)
```

---

🎉 **现在你已经掌握了消息API的完整用法！继续学习其他API接口。** 