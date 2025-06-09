# 消息发送API使用说明

## 概述

新的消息发送API允许插件直接向指定的平台和ID发送消息，无需依赖当前聊天上下文。API会自动从数据库中匹配chat_stream并构建相应的发送消息对象。

## 可用方法

### 1. `send_message_to_target()`

最通用的消息发送方法，支持各种类型的消息。

```python
async def send_message_to_target(
    self,
    message_type: str,        # 消息类型：text, image, emoji等
    content: str,             # 消息内容
    platform: str,            # 目标平台：qq等
    target_id: str,           # 目标ID（群ID或用户ID）
    is_group: bool = True,    # 是否为群聊
    display_message: str = "", # 显示消息（可选）
) -> bool:
```

**示例用法：**
```python
# 发送文本消息到群聊
success = await self.send_message_to_target(
    message_type="text",
    content="Hello, 这是一条测试消息！",
    platform="qq",
    target_id="123456789",
    is_group=True
)

# 发送图片到私聊
success = await self.send_message_to_target(
    message_type="image", 
    content="https://example.com/image.jpg",
    platform="qq",
    target_id="987654321",
    is_group=False
)

# 发送表情包
success = await self.send_message_to_target(
    message_type="emoji",
    content="😄",
    platform="qq",
    target_id="123456789", 
    is_group=True
)
```

### 2. `send_text_to_group()`

便捷方法，专门用于向群聊发送文本消息。

```python
async def send_text_to_group(
    self,
    text: str,                # 文本内容
    group_id: str,            # 群聊ID
    platform: str = "qq"      # 平台，默认为qq
) -> bool:
```

**示例用法：**
```python
success = await self.send_text_to_group(
    text="群聊测试消息", 
    group_id="123456789"
)
```

### 3. `send_text_to_user()`

便捷方法，专门用于向用户发送私聊文本消息。

```python
async def send_text_to_user(
    self,
    text: str,                # 文本内容  
    user_id: str,             # 用户ID
    platform: str = "qq"      # 平台，默认为qq
) -> bool:
```

**示例用法：**
```python
success = await self.send_text_to_user(
    text="私聊测试消息",
    user_id="987654321"
)
```

## 支持的消息类型

- `"text"` - 文本消息
- `"image"` - 图片消息（需要提供图片URL或路径）
- `"emoji"` - 表情消息
- `"voice"` - 语音消息
- `"video"` - 视频消息
- 其他类型根据平台支持情况

## 注意事项

1. **前提条件**：目标群聊或用户必须已经在数据库中存在对应的chat_stream记录
2. **权限要求**：机器人必须在目标群聊中有发言权限
3. **错误处理**：所有方法都会返回bool值表示发送成功与否，同时会在日志中记录详细错误信息
4. **异步调用**：所有方法都是异步的，需要使用`await`调用

## 完整示例插件

参考 `example_send_message_plugin.py` 文件，该文件展示了如何在插件中使用新的消息发送API。

## 配置文件支持

可以通过TOML配置文件管理目标ID、默认平台等设置。参考 `example_config.toml` 文件。

## 错误排查

如果消息发送失败，请检查：

1. 目标ID是否正确
2. chat_stream是否已加载到ChatManager中
3. 机器人是否有相应权限
4. 网络连接是否正常
5. 查看日志中的详细错误信息 