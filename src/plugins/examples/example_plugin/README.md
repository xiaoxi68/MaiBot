# 综合示例插件

## 概述

这是一个展示新插件系统完整功能的综合示例插件，整合了所有旧示例插件的功能，并使用新的架构重写。

## 功能特性

### 🎯 Action组件

#### SmartGreetingAction - 智能问候
- **触发方式**: 关键词触发 (你好、hello、hi、嗨等)
- **支持模式**: 所有聊天模式
- **功能**: 智能问候，支持LLM个性化生成
- **配置**: 可自定义问候模板、启用表情、LLM生成

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
enable_greeting = true  # 启用智能问候
enable_help = true      # 启用帮助系统
enable_send = true      # 启用消息发送
# ... 其他组件开关
```

### 功能配置
```toml
[greeting]
template = "你好，{username}！"  # 问候模板
enable_emoji = true              # 启用表情
enable_llm = false              # 启用LLM生成

[send]
max_message_length = 500        # 最大消息长度

[echo]
max_length = 200               # 回声最大长度
enable_formatting = true       # 启用格式化
```

## 🚀 使用示例

### 智能问候
```
用户: 你好
机器人: 你好，朋友！欢迎使用MaiBot综合插件系统！😊
```

### 帮助查询
```
用户: /help
机器人: [显示完整命令帮助列表]

用户: /help send
机器人: [显示send命令的详细帮助]
```

### 消息发送
```
用户: /send group 123456 大家好！
机器人: ✅ 消息已成功发送到 群聊 123456
```

### 日志监控（不拦截）
```
用户: /log info 这是一条测试消息
[日志记录但消息继续处理，可能触发智能问候等其他功能]
```

## 📁 文件结构

```
src/plugins/built_in/example_comprehensive/
├── plugin.py           # 主插件文件
├── config.toml         # 配置文件
└── README.md          # 说明文档
```

## 🔄 架构升级

此插件展示了从旧插件系统到新插件系统的完整升级：

### 旧系统特征
- 使用 `@register_command` 装饰器
- 继承旧的 `BaseCommand`
- 硬编码的消息处理逻辑
- 有限的配置支持

### 新系统特征
- 使用统一的组件注册机制
- 新的 `BaseAction` 和 `BaseCommand` 基类
- **拦截控制功能** - 灵活的消息处理流程
- 强大的配置驱动架构
- 统一的API接口
- 完整的错误处理和日志

## 💡 开发指南

此插件可作为开发新插件的完整参考：

1. **Action开发**: 参考 `SmartGreetingAction`
2. **Command开发**: 参考各种Command实现
3. **拦截控制**: 根据需要设置 `intercept_message`
4. **配置使用**: 通过 `self.api.get_config()` 读取配置
5. **错误处理**: 完整的异常捕获和用户反馈
6. **日志记录**: 结构化的日志输出

## 🎉 总结

这个综合示例插件完美展示了新插件系统的强大功能，特别是**拦截控制机制**，让开发者可以精确控制消息处理流程，实现更灵活的插件交互模式。 