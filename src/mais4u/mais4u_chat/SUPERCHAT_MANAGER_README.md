# SuperChat管理器使用说明

## 概述

SuperChat管理器是用于管理和跟踪超级弹幕消息的核心组件。它能够根据SuperChat的金额自动设置不同的存活时间，并提供多种格式的字符串构建功能。

## 主要功能

### 1. 自动记录SuperChat
当收到SuperChat消息时，管理器会自动记录以下信息：
- 用户ID和昵称
- 平台信息
- 聊天ID
- SuperChat金额和消息内容
- 时间戳和过期时间
- 群组名称（如果适用）

### 2. 基于金额的存活时间

SuperChat的存活时间根据金额阶梯设置：

| 金额范围 | 存活时间 |
|---------|---------|
| ≥500元  | 4小时   |
| 200-499元 | 2小时 |
| 100-199元 | 1小时 |
| 50-99元 | 30分钟 |
| 20-49元 | 15分钟 |
| 10-19元 | 10分钟 |
| <10元   | 5分钟  |

### 3. 自动清理
管理器每30秒自动检查并清理过期的SuperChat记录，保持内存使用的高效性。

## 使用方法

### 基本用法

```python
from src.mais4u.mais4u_chat.super_chat_manager import get_super_chat_manager

# 获取全局管理器实例
super_chat_manager = get_super_chat_manager()

# 添加SuperChat（通常在消息处理时自动调用）
await super_chat_manager.add_superchat(message)

# 获取指定聊天的SuperChat显示字符串
display_string = super_chat_manager.build_superchat_display_string(chat_id, max_count=10)

# 获取摘要信息
summary = super_chat_manager.build_superchat_summary_string(chat_id)

# 获取统计信息
stats = super_chat_manager.get_superchat_statistics(chat_id)
```

### 结合S4UChat使用

```python
from src.mais4u.mais4u_chat.s4u_chat import get_s4u_chat_manager

# 获取S4UChat实例
s4u_manager = get_s4u_chat_manager()
s4u_chat = s4u_manager.get_or_create_chat(chat_stream)

# 便捷方法获取SuperChat信息
display_string = s4u_chat.get_superchat_display_string(max_count=10)
summary = s4u_chat.get_superchat_summary_string()
stats = s4u_chat.get_superchat_statistics()
```

## API 参考

### SuperChatManager类

#### 主要方法

- `add_superchat(message: MessageRecvS4U)`: 添加SuperChat记录
- `get_superchats_by_chat(chat_id: str)`: 获取指定聊天的有效SuperChat列表
- `build_superchat_display_string(chat_id: str, max_count: int = 10)`: 构建显示字符串
- `build_superchat_summary_string(chat_id: str)`: 构建摘要字符串
- `get_superchat_statistics(chat_id: str)`: 获取统计信息

#### 输出格式示例

**显示字符串格式：**
```
📢 当前有效超级弹幕：
1. 【100元】用户名: 消息内容 (剩余25分30秒)
2. 【50元】用户名: 消息内容 (剩余10分15秒)
... 还有3条SuperChat
```

**摘要字符串格式：**
```
当前有5条超级弹幕，总金额350元，最高单笔100元
```

**统计信息格式：**
```python
{
    "count": 5,
    "total_amount": 350.0,
    "average_amount": 70.0,
    "highest_amount": 100.0,
    "lowest_amount": 20.0
}
```

### S4UChat扩展方法

- `get_superchat_display_string(max_count: int = 10)`: 获取当前聊天的SuperChat显示字符串
- `get_superchat_summary_string()`: 获取当前聊天的SuperChat摘要字符串
- `get_superchat_statistics()`: 获取当前聊天的SuperChat统计信息

## 集成说明

SuperChat管理器已经集成到S4U聊天系统中：

1. **自动处理**: 当S4UChat收到SuperChat消息时，会自动调用管理器记录
2. **内存管理**: 管理器会自动清理过期的SuperChat，无需手动管理
3. **全局单例**: 使用全局单例模式，确保所有聊天共享同一个管理器实例

## 注意事项

1. SuperChat管理器是全局单例，在应用程序整个生命周期中保持运行
2. 过期时间基于消息金额自动计算，无需手动设置
3. 管理器会自动处理异常情况，如无效的价格格式等
4. 清理任务在后台异步运行，不会阻塞主要功能

## 示例文件

参考 `superchat_example.py` 文件查看完整的使用示例。 