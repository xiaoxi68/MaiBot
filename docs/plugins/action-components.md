# ⚡ Action组件详解

## 📖 什么是Action

Action是给麦麦在回复之外提供额外功能的智能组件，**由麦麦的决策系统自主选择是否使用**，具有随机性和拟人化的调用特点。Action不是直接响应用户命令，而是让麦麦根据聊天情境智能地选择合适的动作，使其行为更加自然和真实。

### 🎯 Action的特点

- 🧠 **智能激活**：麦麦根据多种条件智能判断是否使用
- 🎲 **随机性**：增加行为的不可预测性，更接近真人交流
- 🤖 **拟人化**：让麦麦的回应更自然、更有个性
- 🔄 **情境感知**：基于聊天上下文做出合适的反应

## 🎯 两层决策机制

Action采用**两层决策机制**来优化性能和决策质量：

### 第一层：激活控制（Activation Control）

**激活决定麦麦是否"知道"这个Action的存在**，即这个Action是否进入决策候选池。**不被激活的Action麦麦永远不会选择**。

> 🎯 **设计目的**：在加载许多插件的时候降低LLM决策压力，避免让麦麦在过多的选项中纠结。

#### 激活类型说明

| 激活类型 | 说明 | 使用场景 |
|---------|-----|---------|
| `NEVER` | 从不激活，Action对麦麦不可见 | 临时禁用某个Action |
| `ALWAYS` | 永远激活，Action总是在麦麦的候选池中 | 核心功能，如回复、表情 |
| `LLM_JUDGE` | 通过LLM智能判断当前情境是否需要激活此Action | 需要智能判断的复杂场景 |
| `RANDOM` | 基于随机概率决定是否激活 | 增加行为随机性的功能 |
| `KEYWORD` | 当检测到特定关键词时激活 | 明确触发条件的功能 |

#### 聊天模式控制

| 模式 | 说明 |
|-----|-----|
| `ChatMode.FOCUS` | 仅在专注聊天模式下可激活 |
| `ChatMode.NORMAL` | 仅在普通聊天模式下可激活 |
| `ChatMode.ALL` | 所有模式下都可激活 |

### 第二层：使用决策（Usage Decision）

**在Action被激活后，使用条件决定麦麦什么时候会"选择"使用这个Action**。

这一层由以下因素综合决定：
- `action_require`：使用场景描述，帮助LLM判断何时选择
- `action_parameters`：所需参数，影响Action的可执行性
- 当前聊天上下文和麦麦的决策逻辑

### 🎬 决策流程示例

假设有一个"发送表情"Action：

```python
class EmojiAction(BaseAction):
    # 第一层：激活控制
    focus_activation_type = ActionActivationType.RANDOM  # 专注模式下随机激活
    normal_activation_type = ActionActivationType.KEYWORD  # 普通模式下关键词激活
    activation_keywords = ["表情", "emoji", "😊"]
    
    # 第二层：使用决策
    action_require = [
        "表达情绪时可以选择使用",
        "增加聊天趣味性",
        "不要连续发送多个表情"
    ]
```

**决策流程**：
1. **第一层激活判断**：
   - 普通模式：只有当用户消息包含"表情"、"emoji"或"😊"时，麦麦才"知道"可以使用这个Action
   - 专注模式：随机激活，有概率让麦麦"看到"这个Action

2. **第二层使用决策**：
   - 即使Action被激活，麦麦还会根据`action_require`中的条件判断是否真正选择使用
   - 例如：如果刚刚已经发过表情，根据"不要连续发送多个表情"的要求，麦麦可能不会选择这个Action

## 📋 Action必须项清单

每个Action类都**必须**包含以下属性：

### 1. 激活控制必须项

```python
# 专注模式下的激活类型
focus_activation_type = ActionActivationType.LLM_JUDGE

# 普通模式下的激活类型
normal_activation_type = ActionActivationType.KEYWORD

# 启用的聊天模式
mode_enable = ChatMode.ALL

# 是否允许与其他Action并行执行
parallel_action = False
```

### 2. 基本信息必须项

```python
# Action的唯一标识名称
action_name = "my_action"

# Action的功能描述
action_description = "描述这个Action的具体功能和用途"
```

### 3. 功能定义必须项

```python
# Action参数定义 - 告诉LLM执行时需要什么参数
action_parameters = {
    "param1": "参数1的说明",
    "param2": "参数2的说明"
}

# Action使用场景描述 - 帮助LLM判断何时"选择"使用
action_require = [
    "使用场景描述1",
    "使用场景描述2"
]

# 关联的消息类型 - 说明Action能处理什么类型的内容
associated_types = ["text", "emoji", "image"]
```

## 🔧 激活类型详解

### KEYWORD激活

当检测到特定关键词时激活Action：

```python
class GreetingAction(BaseAction):
    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD
    
    # 关键词配置
    activation_keywords = ["你好", "hello", "hi", "嗨"]
    keyword_case_sensitive = False  # 不区分大小写
```

### LLM_JUDGE激活

通过LLM智能判断是否激活：

```python
class HelpAction(BaseAction):
    focus_activation_type = ActionActivationType.LLM_JUDGE
    normal_activation_type = ActionActivationType.LLM_JUDGE
    
    # LLM判断提示词
    llm_judge_prompt = """
    判定是否需要使用帮助动作的条件：
    1. 用户表达了困惑或需要帮助
    2. 用户提出了问题但没有得到满意答案
    3. 对话中出现了技术术语或复杂概念
    
    请回答"是"或"否"。
    """
```

### RANDOM激活

基于随机概率激活：

```python
class SurpriseAction(BaseAction):
    focus_activation_type = ActionActivationType.RANDOM
    normal_activation_type = ActionActivationType.RANDOM
    
    # 随机激活概率
    random_activation_probability = 0.1  # 10%概率激活
```

### ALWAYS/NEVER激活

```python
class CoreAction(BaseAction):
    focus_activation_type = ActionActivationType.ALWAYS  # 总是激活
    normal_activation_type = ActionActivationType.NEVER  # 在普通模式下禁用
```

## 🎨 完整Action示例

### 智能问候Action

```python
from src.plugin_system import BaseAction, ActionActivationType, ChatMode

class SmartGreetingAction(BaseAction):
    """智能问候Action - 展示关键词激活的完整示例"""

    # ===== 激活控制必须项 =====
    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD
    mode_enable = ChatMode.ALL
    parallel_action = False

    # ===== 基本信息必须项 =====
    action_name = "smart_greeting"
    action_description = "智能问候系统，基于关键词触发，支持个性化问候消息"

    # 关键词配置
    activation_keywords = ["你好", "hello", "hi", "嗨", "问候", "早上好", "晚上好"]
    keyword_case_sensitive = False

    # ===== 功能定义必须项 =====
    action_parameters = {
        "username": "要问候的用户名（可选）",
        "greeting_style": "问候风格：casual(随意)、formal(正式)、friendly(友好)"
    }

    action_require = [
        "用户发送包含问候词汇的消息时使用",
        "检测到新用户加入时使用", 
        "响应友好交流需求时使用",
        "避免在短时间内重复问候同一用户"
    ]

    associated_types = ["text", "emoji"]

    async def execute(self) -> Tuple[bool, str]:
        """执行智能问候"""
        # 获取参数
        username = self.action_data.get("username", "")
        greeting_style = self.action_data.get("greeting_style", "casual")

        # 根据风格生成问候消息
        if greeting_style == "formal":
            message = f"您好{username}！很荣幸为您服务！"
            emoji = "🙏"
        elif greeting_style == "friendly":
            message = f"你好{username}！欢迎来到这里，希望我们能成为好朋友！"
            emoji = "😊"
        else:  # casual
            message = f"嗨{username}！很开心见到你～"
            emoji = "👋"

        # 发送消息
        await self.send_text(message)
        await self.send_type("emoji", emoji)

        return True, f"向{username or '用户'}发送了{greeting_style}风格的问候"
```

### 智能禁言Action

以下是一个真实的群管理禁言Action示例，展示了LLM判断、参数验证、配置管理等高级功能：

```python
from typing import Optional
import random
from src.plugin_system.base.base_action import BaseAction
from src.plugin_system.base.component_types import ActionActivationType, ChatMode

class MuteAction(BaseAction):
    """智能禁言Action - 基于LLM智能判断是否需要禁言"""

    # ===== 激活控制必须项 =====
    focus_activation_type = ActionActivationType.LLM_JUDGE  # Focus模式使用LLM判定
    normal_activation_type = ActionActivationType.KEYWORD   # Normal模式使用关键词
    mode_enable = ChatMode.ALL
    parallel_action = False

    # ===== 基本信息必须项 =====
    action_name = "mute"
    action_description = "智能禁言系统，基于LLM判断是否需要禁言"

    # ===== 激活配置 =====
    # 关键词设置（用于Normal模式）
    activation_keywords = ["禁言", "mute", "ban", "silence"]
    keyword_case_sensitive = False

    # LLM判定提示词（用于Focus模式）
    llm_judge_prompt = """
判定是否需要使用禁言动作的严格条件：

使用禁言的情况：
1. 用户发送明显违规内容（色情、暴力、政治敏感等）
2. 恶意刷屏或垃圾信息轰炸
3. 用户主动明确要求被禁言（"禁言我"等）
4. 严重违反群规的行为
5. 恶意攻击他人或群组管理

绝对不要使用的情况：
1. 正常聊天和交流
2. 情绪化表达但无恶意
3. 开玩笑或调侃，除非过分
4. 单纯的意见分歧或争论
"""

    # ===== 功能定义必须项 =====
    action_parameters = {
        "target": "禁言对象，必填，输入你要禁言的对象的名字，请仔细思考不要弄错禁言对象",
        "duration": "禁言时长，必填，输入你要禁言的时长（秒），单位为秒，必须为数字",
        "reason": "禁言理由，可选",
    }

    action_require = [
        "当有人违反了公序良俗的内容",
        "当有人刷屏时使用",
        "当有人发了擦边，或者色情内容时使用",
        "当有人要求禁言自己时使用",
        "如果某人已经被禁言了，就不要再次禁言了，除非你想追加时间！！",
    ]

    associated_types = ["text", "command"]

    async def execute(self) -> Tuple[bool, Optional[str]]:
        """执行智能禁言判定"""
        # 获取参数
        target = self.action_data.get("target")
        duration = self.action_data.get("duration")
        reason = self.action_data.get("reason", "违反群规")

        # 参数验证
        if not target:
            await self.send_text("没有指定禁言对象呢~")
            return False, "禁言目标不能为空"

        if not duration:
            await self.send_text("没有指定禁言时长呢~")
            return False, "禁言时长不能为空"

        # 获取时长限制配置
        min_duration = self.api.get_config("mute.min_duration", 60)
        max_duration = self.api.get_config("mute.max_duration", 2592000)

        # 验证时长格式并转换
        try:
            duration_int = int(duration)
            if duration_int <= 0:
                await self.send_text("禁言时长必须是正数哦~")
                return False, "禁言时长必须大于0"

            # 限制禁言时长范围
            if duration_int < min_duration:
                duration_int = min_duration
            elif duration_int > max_duration:
                duration_int = max_duration

        except (ValueError, TypeError):
            await self.send_text("禁言时长必须是数字哦~")
            return False, f"禁言时长格式无效: {duration}"

        # 获取用户ID
        try:
            platform, user_id = await self.api.get_user_id_by_person_name(target)
        except Exception as e:
            await self.send_text("查找用户信息时出现问题~")
            return False, f"查找用户ID时出错: {e}"

        if not user_id:
            await self.send_text(f"找不到 {target} 这个人呢~")
            return False, f"未找到用户 {target} 的ID"

        # 格式化时长显示
        time_str = self._format_duration(duration_int)

        # 获取模板化消息
        message = self._get_template_message(target, time_str, reason)
        await self.send_message_by_expressor(message)

        # 发送群聊禁言命令
        success = await self.send_command(
            command_name="GROUP_BAN",
            args={"qq_id": str(user_id), "duration": str(duration_int)},
            display_message=f"禁言了 {target} {time_str}",
        )

        if success:
            return True, f"成功禁言 {target}，时长 {time_str}"
        else:
            await self.send_text("执行禁言动作失败")
            return False, "发送禁言命令失败"

    def _get_template_message(self, target: str, duration_str: str, reason: str) -> str:
        """获取模板化的禁言消息"""
        templates = self.api.get_config(
            "mute.templates",
            [
                "好的，禁言 {target} {duration}，理由：{reason}",
                "收到，对 {target} 执行禁言 {duration}，因为{reason}",
                "明白了，禁言 {target} {duration}，原因是{reason}",
                "哇哈哈哈哈哈，已禁言 {target} {duration}，理由：{reason}",
            ],
        )
        template = random.choice(templates)
        return template.format(target=target, duration=duration_str, reason=reason)

    def _format_duration(self, seconds: int) -> str:
        """将秒数格式化为可读的时间字符串"""
        if seconds < 60:
            return f"{seconds}秒"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            if remaining_seconds > 0:
                return f"{minutes}分{remaining_seconds}秒"
            else:
                return f"{minutes}分钟"
        else:
            hours = seconds // 3600
            remaining_minutes = (seconds % 3600) // 60
            if remaining_minutes > 0:
                return f"{hours}小时{remaining_minutes}分钟"
            else:
                return f"{hours}小时"
```

**关键特性说明**：

1. **🎯 双模式激活**：Focus模式使用LLM_JUDGE更谨慎，Normal模式使用KEYWORD快速响应
2. **🧠 严格的LLM判定**：详细提示词指导LLM何时应该/不应该使用禁言，避免误判
3. **✅ 完善的参数验证**：验证必需参数、数值转换、用户ID查找等多重验证
4. **⚙️ 配置驱动**：时长限制、消息模板等都可通过配置文件自定义
5. **😊 友好的用户反馈**：错误提示清晰、随机化消息模板、时长格式化显示
6. **🛡️ 安全措施**：严格权限控制、防误操作验证、完整错误处理

### 智能助手Action

```python
class IntelligentHelpAction(BaseAction):
    """智能助手Action - 展示LLM判断激活的完整示例"""

    # ===== 激活控制必须项 =====
    focus_activation_type = ActionActivationType.LLM_JUDGE
    normal_activation_type = ActionActivationType.RANDOM
    mode_enable = ChatMode.ALL
    parallel_action = True

    # ===== 基本信息必须项 =====
    action_name = "intelligent_help"
    action_description = "智能助手，主动提供帮助和建议"

    # LLM判断提示词
    llm_judge_prompt = """
    判定是否需要提供智能帮助的条件：
    1. 用户表达了困惑或需要帮助
    2. 对话中出现了技术问题
    3. 用户寻求解决方案或建议
    4. 适合提供额外信息的场合
    
    不要使用的情况：
    1. 用户明确表示不需要帮助
    2. 对话进行得很顺利
    3. 刚刚已经提供过帮助
    
    请回答"是"或"否"。
    """

    # 随机激活概率
    random_activation_probability = 0.15

    # ===== 功能定义必须项 =====
    action_parameters = {
        "help_type": "帮助类型：explanation(解释)、suggestion(建议)、guidance(指导)",
        "topic": "帮助主题或用户关心的问题",
        "urgency": "紧急程度：low(低)、medium(中)、high(高)"
    }

    action_require = [
        "用户表达困惑或寻求帮助时使用",
        "检测到用户遇到技术问题时使用",
        "对话中出现知识盲点时主动提供帮助",
        "避免过度频繁地提供帮助，要恰到好处"
    ]

    associated_types = ["text", "emoji"]

    async def execute(self) -> Tuple[bool, str]:
        """执行智能帮助"""
        # 获取参数
        help_type = self.action_data.get("help_type", "suggestion")
        topic = self.action_data.get("topic", "")
        urgency = self.action_data.get("urgency", "medium")

        # 根据帮助类型和紧急程度生成消息
        if help_type == "explanation":
            message = f"关于{topic}，让我来为你解释一下..."
        elif help_type == "guidance":
            message = f"在{topic}方面，我可以为你提供一些指导..."
        else:  # suggestion
            message = f"针对{topic}，我建议你可以尝试以下方法..."

        # 根据紧急程度调整表情
        if urgency == "high":
            emoji = "🚨"
        elif urgency == "low":
            emoji = "💡"
        else:
            emoji = "🤔"

        # 发送帮助消息
        await self.send_text(message)
        await self.send_type("emoji", emoji)

        return True, f"提供了{help_type}类型的帮助，主题：{topic}"
```

## 📊 性能优化建议

### 1. 合理使用激活类型

- **ALWAYS**: 仅用于核心功能
- **LLM_JUDGE**: 适度使用，避免过多LLM调用
- **KEYWORD**: 优选，性能最好
- **RANDOM**: 控制概率，避免过于频繁

### 2. 优化execute方法

```python
async def execute(self) -> Tuple[bool, str]:
    try:
        # 快速参数验证
        if not self._validate_parameters():
            return False, "参数验证失败"
        
        # 核心逻辑
        result = await self._core_logic()
        
        # 成功返回
        return True, "执行成功"
        
    except Exception as e:
        logger.error(f"{self.log_prefix} 执行失败: {e}")
        return False, f"执行失败: {str(e)}"
```

### 3. 合理设置并行执行

```python
# 轻量级Action可以并行
parallel_action = True  # 如：发送表情、记录日志

# 重要Action应该独占
parallel_action = False  # 如：回复消息、状态切换
```

## 🐛 调试技巧

### 1. 日志记录

```python
from src.common.logger import get_logger

logger = get_logger("my_action")

async def execute(self) -> Tuple[bool, str]:
    logger.info(f"{self.log_prefix} 开始执行: {self.reasoning}")
    logger.debug(f"{self.log_prefix} 参数: {self.action_data}")
    
    # 执行逻辑...
    
    logger.info(f"{self.log_prefix} 执行完成")
```

### 2. 激活状态检查

```python
# 在execute方法中检查激活原因
def _debug_activation(self):
    logger.debug(f"激活类型: Focus={self.focus_activation_type}, Normal={self.normal_activation_type}")
    logger.debug(f"当前模式: {self.api.get_chat_mode()}")
    logger.debug(f"激活原因: {self.reasoning}")
```

### 3. 参数验证

```python
def _validate_parameters(self) -> bool:
    required_params = ["param1", "param2"]
    for param in required_params:
        if param not in self.action_data:
            logger.warning(f"{self.log_prefix} 缺少必需参数: {param}")
            return False
    return True
```

## 🎯 最佳实践

### 1. 清晰的Action命名

- 使用描述性的类名：`SmartGreetingAction` 而不是 `Action1`
- action_name要简洁明确：`"smart_greeting"` 而不是 `"action_1"`

### 2. 完整的文档字符串

```python
class MyAction(BaseAction):
    """
    我的Action - 一句话描述功能
    
    详细描述Action的用途、激活条件、执行逻辑等。
    
    激活条件：
    - Focus模式：关键词激活
    - Normal模式：LLM判断激活
    
    执行逻辑：
    1. 验证参数
    2. 生成响应
    3. 发送消息
    """
```

### 3. 错误处理

```python
async def execute(self) -> Tuple[bool, str]:
    try:
        # 主要逻辑
        pass
    except ValueError as e:
        await self.send_text("参数错误，请检查输入")
        return False, f"参数错误: {e}"
    except Exception as e:
        await self.send_text("操作失败，请稍后重试")
        return False, f"执行失败: {e}"
```

### 4. 配置驱动

```python
# 从配置文件读取设置
enable_feature = self.api.get_config("my_action.enable_feature", True)
max_retries = self.api.get_config("my_action.max_retries", 3)
```

---

🎉 **现在你已经掌握了Action组件开发的完整知识！继续学习 [Command组件详解](command-components.md) 来了解命令开发。** 