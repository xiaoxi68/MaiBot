# HearflowAPI 使用说明

## 概述

HearflowAPI 是一个新增的插件API模块，提供了与心流和子心流相关的操作接口。通过这个API，插件开发者可以方便地获取和操作sub_hearflow实例。

## 主要功能

### 1. 获取子心流实例

#### `get_sub_hearflow_by_chat_id(chat_id: str) -> Optional[SubHeartflow]`
根据chat_id获取指定的sub_hearflow实例（仅获取已存在的）。

**参数：**
- `chat_id`: 聊天ID，与sub_hearflow的subheartflow_id相同

**返回值：**
- `SubHeartflow`: sub_hearflow实例，如果不存在则返回None

**示例：**
```python
# 获取当前聊天的子心流实例
current_subflow = await self.get_sub_hearflow_by_chat_id(self.observation.chat_id)
if current_subflow:
    print(f"找到子心流: {current_subflow.chat_id}")
else:
    print("子心流不存在")
```

#### `get_or_create_sub_hearflow_by_chat_id(chat_id: str) -> Optional[SubHeartflow]`
根据chat_id获取或创建sub_hearflow实例。

**参数：**
- `chat_id`: 聊天ID

**返回值：**
- `SubHeartflow`: sub_hearflow实例，创建失败时返回None

**示例：**
```python
# 获取或创建子心流实例
subflow = await self.get_or_create_sub_hearflow_by_chat_id("some_chat_id")
if subflow:
    print("成功获取或创建子心流")
```

### 2. 获取子心流列表

#### `get_all_sub_hearflow_ids() -> List[str]`
获取所有活跃子心流的ID列表。

**返回值：**
- `List[str]`: 所有活跃子心流的ID列表

#### `get_all_sub_hearflows() -> List[SubHeartflow]`
获取所有活跃的子心流实例。

**返回值：**
- `List[SubHeartflow]`: 所有活跃的子心流实例列表

**示例：**
```python
# 获取所有活跃的子心流ID
all_chat_ids = self.get_all_sub_hearflow_ids()
print(f"共有 {len(all_chat_ids)} 个活跃的子心流")

# 获取所有活跃的子心流实例
all_subflows = self.get_all_sub_hearflows()
for subflow in all_subflows:
    print(f"子心流 {subflow.chat_id} 状态: {subflow.chat_state.chat_status.value}")
```

### 3. 心流状态操作

#### `get_sub_hearflow_chat_state(chat_id: str) -> Optional[ChatState]`
获取指定子心流的聊天状态。

**参数：**
- `chat_id`: 聊天ID

**返回值：**
- `ChatState`: 聊天状态，如果子心流不存在则返回None

#### `set_sub_hearflow_chat_state(chat_id: str, target_state: ChatState) -> bool`
设置指定子心流的聊天状态。

**参数：**
- `chat_id`: 聊天ID
- `target_state`: 目标状态

**返回值：**
- `bool`: 是否设置成功

**示例：**
```python
from src.chat.heart_flow.sub_heartflow import ChatState

# 获取当前状态
current_state = await self.get_sub_hearflow_chat_state(self.observation.chat_id)
print(f"当前状态: {current_state.value}")

# 设置状态
success = await self.set_sub_hearflow_chat_state(self.observation.chat_id, ChatState.FOCUS)
if success:
    print("状态设置成功")
```

### 4. Replyer和Expressor操作

#### `get_sub_hearflow_replyer_and_expressor(chat_id: str) -> Tuple[Optional[Any], Optional[Any]]`
根据chat_id获取指定子心流的replyer和expressor实例。

**参数：**
- `chat_id`: 聊天ID

**返回值：**
- `Tuple[Optional[Any], Optional[Any]]`: (replyer实例, expressor实例)，如果子心流不存在或未处于FOCUSED状态，返回(None, None)

#### `get_sub_hearflow_replyer(chat_id: str) -> Optional[Any]`
根据chat_id获取指定子心流的replyer实例。

**参数：**
- `chat_id`: 聊天ID

**返回值：**
- `Optional[Any]`: replyer实例，如果不存在则返回None

#### `get_sub_hearflow_expressor(chat_id: str) -> Optional[Any]`
根据chat_id获取指定子心流的expressor实例。

**参数：**
- `chat_id`: 聊天ID

**返回值：**
- `Optional[Any]`: expressor实例，如果不存在则返回None

**示例：**
```python
# 获取replyer和expressor
replyer, expressor = await self.get_sub_hearflow_replyer_and_expressor(self.observation.chat_id)
if replyer and expressor:
    print(f"获取到replyer: {type(replyer).__name__}")
    print(f"获取到expressor: {type(expressor).__name__}")
    
    # 检查属性
    print(f"Replyer聊天ID: {replyer.chat_id}")
    print(f"Expressor聊天ID: {expressor.chat_id}")
    print(f"是否群聊: {replyer.is_group_chat}")

# 单独获取replyer
replyer = await self.get_sub_hearflow_replyer(self.observation.chat_id)
if replyer:
    print("获取到replyer实例")

# 单独获取expressor  
expressor = await self.get_sub_hearflow_expressor(self.observation.chat_id)
if expressor:
    print("获取到expressor实例")
```

## 可用的聊天状态

```python
from src.chat.heart_flow.sub_heartflow import ChatState

ChatState.FOCUS    # 专注模式
ChatState.NORMAL   # 普通模式  
ChatState.ABSENT   # 离开模式
```

## 完整插件示例

```python
from typing import Tuple
from src.plugin_system.base.base_action import BaseAction as PluginAction, register_action
from src.chat.heart_flow.sub_heartflow import ChatState

@register_action
class MyHearflowPlugin(PluginAction):
    """我的心流插件"""
    
    activation_keywords = ["心流信息"]
    
    async def process(self) -> Tuple[bool, str]:
        try:
            # 获取当前聊天的chat_id
            current_chat_id = self.observation.chat_id
            
            # 获取子心流实例
            subflow = await self.get_sub_hearflow_by_chat_id(current_chat_id)
            if not subflow:
                return False, "未找到子心流实例"
            
            # 获取状态信息
            current_state = await self.get_sub_hearflow_chat_state(current_chat_id)
            
            # 构建回复
            response = f"心流信息：\n"
            response += f"聊天ID: {current_chat_id}\n"
            response += f"当前状态: {current_state.value}\n"
            response += f"是否群聊: {subflow.is_group_chat}\n"
            
            return True, response
            
        except Exception as e:
            return False, f"处理出错: {str(e)}"
```

## 注意事项

1. **线程安全**: API内部已处理锁机制，确保线程安全。

2. **错误处理**: 所有API方法都包含异常处理，失败时会记录日志并返回安全的默认值。

3. **性能考虑**: `get_sub_hearflow_by_chat_id` 只获取已存在的实例，性能更好；`get_or_create_sub_hearflow_by_chat_id` 会在需要时创建新实例。

4. **状态管理**: 修改心流状态时请谨慎，确保不会影响系统的正常运行。

5. **日志记录**: 所有操作都会记录适当的日志，便于调试和监控。

6. **Replyer和Expressor可用性**: 
   - 这些实例仅在子心流处于**FOCUSED状态**时可用
   - 如果子心流处于NORMAL或ABSENT状态，将返回None
   - 需要确保HeartFC实例存在且正常运行

7. **使用Replyer和Expressor时的注意事项**:
   - 直接调用这些实例的方法需要谨慎，可能影响系统正常运行
   - 建议主要用于监控、信息获取和状态检查
   - 不建议在插件中直接调用回复生成方法，这可能与系统的正常流程冲突

## 相关类型和模块

- `SubHeartflow`: 子心流实例类
- `ChatState`: 聊天状态枚举
- `DefaultReplyer`: 默认回复器类
- `DefaultExpressor`: 默认表达器类
- `HeartFChatting`: 专注聊天主类
- `src.chat.heart_flow.heartflow`: 主心流模块
- `src.chat.heart_flow.subheartflow_manager`: 子心流管理器
- `src.chat.focus_chat.replyer.default_replyer`: 回复器模块
- `src.chat.focus_chat.expressors.default_expressor`: 表达器模块 