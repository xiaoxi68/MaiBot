# 综合示例插件

## 概述

这是一个展示新插件系统完整功能的综合示例插件，整合了所有旧示例插件的功能，并使用新的架构重写。

## 功能特性

### 🎯 Action组件

#### SmartGreetingAction - 智能问候
- **激活类型**: 
  - Focus模式: KEYWORD (关键词激活)
  - Normal模式: KEYWORD (关键词激活)
- **触发关键词**: 你好、hello、hi、嗨、问候、早上好、晚上好
- **支持模式**: 所有聊天模式
- **并行执行**: 否
- **功能**: 智能问候，支持多种风格和LLM个性化生成
- **参数**: username(用户名), greeting_style(问候风格)
- **配置**: 可自定义问候模板、启用表情、LLM生成

#### HelpfulAction - 智能助手
- **激活类型**: 
  - Focus模式: LLM_JUDGE (LLM智能判断)
  - Normal模式: RANDOM (随机激活，概率15%)
- **支持模式**: 所有聊天模式
- **并行执行**: 是
- **功能**: 主动提供帮助和建议，展示LLM判断激活机制
- **参数**: help_type(帮助类型), topic(主题), complexity(复杂度)
- **特点**: 
  - 通过LLM智能判断是否需要提供帮助
  - 展示两层决策机制的实际应用
  - 支持多种帮助类型（解释、建议、指导、提示）

### 📝 Command组件

#### 1. ComprehensiveHelpCommand - 综合帮助系统
```
/help [命令名]
```
- **功能**: 显示所有命令帮助或特定命令详情
- **拦截**: ✅ 拦截消息处理
- **示例**: `/help`, `/help send`

#### 2. MessageSendCommand - 消息发送
```
/send <group|user> <ID> <消息内容>
```
- **功能**: 向指定群聊或私聊发送消息
- **拦截**: ✅ 拦截消息处理
- **示例**: `/send group 123456 大家好`

#### 3. SystemStatusCommand - 系统状态查询
```
/status [类型]
```
- **功能**: 查询系统、插件、内存等状态
- **拦截**: ✅ 拦截消息处理
- **示例**: `/status`, `/status 插件`

#### 4. EchoCommand - 回声命令
```
/echo <消息内容>
```
- **功能**: 重复用户输入的消息
- **拦截**: ✅ 拦截消息处理
- **示例**: `/echo Hello World`

#### 5. MessageInfoCommand - 消息信息查询
```
/info
```
- **功能**: 显示当前消息的详细信息
- **拦截**: ✅ 拦截消息处理
- **示例**: `/info`

#### 6. CustomPrefixCommand - 自定义前缀
```
/prefix <前缀> <内容>
```
- **功能**: 为消息添加自定义前缀
- **拦截**: ✅ 拦截消息处理
- **示例**: `/prefix [公告] 系统维护`

#### 7. LogMonitorCommand - 日志监控
```
/log [级别]
```
- **功能**: 记录消息到日志但不拦截后续处理
- **拦截**: ❌ 不拦截，继续处理消息
- **示例**: `/log`, `/log debug`

## 🔧 拦截控制演示

此插件完美演示了新插件系统的**拦截控制功能**：

### 拦截型命令 (intercept_message = True)
- `/help` - 显示帮助后停止处理
- `/send` - 发送消息后停止处理  
- `/status` - 查询状态后停止处理
- `/echo` - 回声后停止处理
- `/info` - 显示信息后停止处理
- `/prefix` - 添加前缀后停止处理

### 非拦截型命令 (intercept_message = False)
- `/log` - 记录日志但继续处理，可能触发其他功能

## ⚙️ 配置说明

插件支持通过 `config.toml` 进行详细配置：

### 组件控制
```toml
[components]
enable_greeting = true   # 启用智能问候Action
enable_helpful = true    # 启用智能助手Action
enable_help = true       # 启用帮助系统Command
enable_send = true       # 启用消息发送Command
enable_echo = true       # 启用回声Command
enable_info = true       # 启用消息信息Command
enable_dice = true       # 启用骰子Command
```

### Action配置
```toml
[greeting]
template = "你好，{username}！"  # 问候模板
enable_emoji = true              # 启用表情
enable_llm = false              # 启用LLM生成

[helpful]
enable_llm = false                    # 启用LLM生成帮助
enable_emoji = true                   # 启用鼓励表情
random_activation_probability = 0.15  # 随机激活概率
```

### Command配置
```toml
[send]
max_message_length = 500        # 最大消息长度

[echo]
max_length = 200               # 回声最大长度
enable_formatting = true       # 启用格式化

[help]
enable_llm = false             # 启用LLM生成帮助内容
enable_emoji = true            # 启用帮助表情
```

## 🚀 使用示例

### Action组件示例

#### 智能问候Action (关键词激活)
```
用户: 你好
机器人: 嗨！很开心见到你～ 😊

用户: 早上好
机器人: 早上好！今天也要元气满满哦！ ✨
```

#### 智能助手Action (LLM判断激活)
```
用户: 我不太懂怎么使用这个功能
机器人: 关于功能使用，我来为你解释一下：这是一个simple级别的概念...
这个概念其实很简单，让我用通俗的话来说明。 💡

用户: Python装饰器是什么？
机器人: 关于Python装饰器，我来为你解释一下：这是一个medium级别的概念...
装饰器是一种设计模式，用于在不修改原函数的情况下扩展功能。 🎯
```

### Command组件示例

#### 帮助查询
```
用户: /help
机器人: [显示完整命令帮助列表]

用户: /help send
机器人: [显示send命令的详细帮助]
```

#### 消息发送
```
用户: /send group 123456 大家好！
机器人: ✅ 消息已成功发送到 群聊 123456
```

#### 骰子命令
```
用户: !dice
机器人: 🎲 你投出了: 4

用户: !骰子 3
机器人: 🎲 你投出了3个骰子: 2, 5, 1 (总计: 8)
```

### 两层决策机制展示

#### 第一层：激活控制
```
# SmartGreetingAction - 关键词激活
用户消息包含"你好" → Action被激活 → 进入候选池

# HelpfulAction - LLM判断激活  
用户表达困惑 → LLM判断"是" → Action被激活 → 进入候选池
用户正常聊天 → LLM判断"否" → Action不激活 → 不进入候选池
```

#### 第二层：使用决策
```
# 即使Action被激活，LLM还会根据action_require判断是否真正使用
# 比如HelpfulAction的条件："避免过度频繁地提供帮助，要恰到好处"
# 如果刚刚已经提供了帮助，可能不会再次选择使用
```

## 📁 文件结构

```
plugins/example_plugin/     # 用户插件目录
├── plugin.py              # 主插件文件
├── config.toml            # 配置文件
└── README.md              # 说明文档
```

> 💡 **目录说明**：
> - `plugins/` - 用户自定义插件目录（推荐放置位置）
> - `src/plugins/builtin/` - 系统内置插件目录

## 🔄 架构升级

此插件展示了从旧插件系统到新插件系统的完整升级：

### 新系统特征
- 使用统一的组件注册机制
- 新的 `BaseAction` 和 `BaseCommand` 基类
- **拦截控制功能** - 灵活的消息处理流程
- 强大的配置驱动架构
- 统一的API接口
- 完整的错误处理和日志

## 💡 开发指南

此插件可作为开发新插件的完整参考：

### Action开发规范
1. **必须项检查清单**:
   - ✅ 激活控制必须项：`focus_activation_type`, `normal_activation_type`, `mode_enable`, `parallel_action`
   - ✅ 基本信息必须项：`action_name`, `action_description`
   - ✅ 功能定义必须项：`action_parameters`, `action_require`, `associated_types`

2. **激活类型选择**:
   - `KEYWORD`: 适合明确触发词的功能（如问候）
   - `LLM_JUDGE`: 适合需要智能判断的功能（如帮助）
   - `RANDOM`: 适合增加随机性的功能
   - `ALWAYS`: 适合总是考虑的功能
   - `NEVER`: 用于临时禁用

3. **两层决策设计**:
   - 第一层（激活控制）：控制Action是否进入候选池
   - 第二层（使用决策）：LLM根据场景智能选择

### Command开发规范
1. **拦截控制**: 根据需要设置 `intercept_message`
2. **正则表达式**: 使用命名组捕获参数
3. **错误处理**: 完整的异常捕获和用户反馈

### 通用开发规范
1. **配置使用**: 通过 `self.api.get_config()` 读取配置
2. **日志记录**: 结构化的日志输出
3. **API调用**: 使用新的统一API接口
4. **注册简化**: Action使用 `get_action_info()` 无参数调用

## 🎉 总结

这个综合示例插件完美展示了新插件系统的强大功能：

### 🚀 核心特性
- **两层决策机制**：优化LLM决策压力，提升性能
- **完整的Action规范**：所有必须项都在类中统一定义
- **灵活的激活控制**：支持多种激活类型和条件
- **精确的拦截控制**：Command可以精确控制消息处理流程

### 📚 学习价值
- **Action vs Command**: 清晰展示两种组件的不同设计理念
- **激活机制**: 实际演示关键词、LLM判断、随机等激活方式
- **配置驱动**: 展示如何通过配置文件控制插件行为
- **错误处理**: 完整的异常处理和用户反馈机制

这个插件是理解和掌握MaiBot插件系统的最佳起点！🌟 