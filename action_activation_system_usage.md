# MaiBot 动作激活系统使用指南

## 概述

MaiBot 的动作激活系统支持四种不同的激活类型，让机器人能够智能地根据上下文选择合适的动作。

**系统已集成三大优化策略：**
- 🚀 **并行判定**：多个LLM判定任务并行执行
- 💾 **智能缓存**：相同上下文的判定结果缓存复用
- 🔍 **分层判定**：快速过滤 + 精确判定的两层架构

## 激活类型详解

### 1. ALWAYS - 总是激活
**用途**：基础必需动作，始终可用
```python
action_activation_type = ActionActivationType.ALWAYS
```
**示例**：`reply_action`, `no_reply_action`

### 2. RANDOM - 随机激活
**用途**：增加不可预测性和趣味性
```python
action_activation_type = ActionActivationType.RANDOM
random_activation_probability = 0.2  # 20%概率激活
```
**示例**：`pic_action` (20%概率)

### 3. LLM_JUDGE - LLM智能判定
**用途**：需要上下文理解的复杂判定
```python
action_activation_type = ActionActivationType.LLM_JUDGE
llm_judge_prompt = """
判定条件：
1. 当前聊天涉及情感表达
2. 需要生动的情感回应
3. 场景适合虚拟主播动作

不适用场景：
1. 纯信息查询
2. 技术讨论
"""
```
**优化特性**：
- ⚡ **直接判定**：直接进行LLM判定，减少复杂度
- 🚀 **并行执行**：多个LLM判定同时进行
- 💾 **结果缓存**：相同上下文复用结果（30秒有效期）

### 4. KEYWORD - 关键词触发
**用途**：精确命令式触发
```python
action_activation_type = ActionActivationType.KEYWORD
activation_keywords = ["画", "画图", "生成图片", "draw"]
keyword_case_sensitive = False  # 不区分大小写
```
**示例**：`help_action`, `edge_search_action`, `pic_action`

## 性能优化详解

### 并行判定机制
```python
# 自动将多个LLM判定任务并行执行
async def _process_llm_judge_actions_parallel(self, llm_judge_actions, ...):
    tasks = [self._llm_judge_action(name, info, ...) for name, info in llm_judge_actions.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
```

**优势**：
- 多个LLM判定同时进行，显著减少总耗时
- 异常处理确保单个失败不影响整体
- 自动负载均衡

### 智能缓存系统
```python
# 基于上下文哈希的缓存机制
cache_key = f"{action_name}_{context_hash}"
if cache_key in self._llm_judge_cache:
    return cached_result  # 直接返回缓存结果
```

**特性**：
- 30秒缓存有效期
- MD5哈希确保上下文一致性
- 自动清理过期缓存
- 命中率优化：相同聊天上下文的重复判定

### 分层判定架构

#### 第一层：智能动态过滤
```python
def _pre_filter_llm_actions(self, llm_judge_actions, observed_messages_str, ...):
    # 动态收集所有KEYWORD类型actions的关键词
    all_keyword_actions = self.action_manager.get_registered_actions()
    collected_keywords = {}
    
    for action_name, action_info in all_keyword_actions.items():
        if action_info.get("activation_type") == "KEYWORD":
            keywords = action_info.get("activation_keywords", [])
            if keywords:
                collected_keywords[action_name] = [kw.lower() for kw in keywords]
    
    # 基于实际配置进行智能过滤
    for action_name, action_info in llm_judge_actions.items():
        # 策略1: 避免与KEYWORD类型重复
        # 策略2: 基于action描述进行语义相关性检查  
        # 策略3: 保留核心actions
```

**智能过滤策略**：
- **动态关键词收集**：从各个action的实际配置中收集关键词，无硬编码
- **重复避免机制**：如果存在对应的KEYWORD触发action，优先使用KEYWORD
- **语义相关性检查**：基于action描述和消息内容进行智能匹配
- **长度与复杂度匹配**：短消息自动排除复杂operations
- **核心action保护**：确保reply/no_reply等基础action始终可用

#### 第二层：LLM精确判定
通过第一层过滤后的动作才进入LLM判定，大幅减少：
- LLM调用次数
- 总处理时间
- API成本

## HFC流程级并行化优化 🆕

### 三阶段并行架构

除了动作激活系统内部的优化，整个HFC（HeartFocus Chat）流程也实现了并行化：

```python
# 在 heartFC_chat.py 中的优化
if global_config.focus_chat.parallel_processing:
    # 并行执行调整动作、回忆和处理器阶段
    with Timer("并行调整动作、回忆和处理", cycle_timers):
        async def modify_actions_task():
            await self.action_modifier.modify_actions(observations=self.observations)
            await self.action_observation.observe()
            self.observations.append(self.action_observation)
            return True
        
        # 创建三个并行任务
        action_modify_task = asyncio.create_task(modify_actions_task())
        memory_task = asyncio.create_task(self.memory_activator.activate_memory(self.observations))
        processor_task = asyncio.create_task(self._process_processors(self.observations, []))

        # 等待三个任务完成
        _, running_memorys, (all_plan_info, processor_time_costs) = await asyncio.gather(
            action_modify_task, memory_task, processor_task
        )
```

### 并行化阶段说明

**1. 调整动作阶段（Action Modifier）**
- 执行动作激活系统的智能判定
- 包含并行LLM判定和缓存
- 更新可用动作列表

**2. 回忆激活阶段（Memory Activator）**
- 根据当前观察激活相关记忆
- 检索历史对话和上下文信息
- 为规划器提供背景知识

**3. 信息处理器阶段（Processors）**
- 处理观察信息，提取关键特征
- 生成结构化的计划信息
- 为规划器提供决策依据

### 性能提升效果

**理论提升**：
- 原串行执行：500ms + 800ms + 1000ms = 2300ms
- 现并行执行：max(500ms, 800ms, 1000ms) = 1000ms
- **性能提升：2.3x**

**实际效果**：
- 显著减少每个HFC循环的总耗时
- 提高机器人响应速度
- 优化用户体验

### 配置控制

通过配置文件控制是否启用并行处理：
```yaml
focus_chat:
  parallel_processing: true  # 启用并行处理
```

**建议设置**：
- **生产环境**：启用（`true`）- 获得最佳性能
- **调试环境**：可选择禁用（`false`）- 便于问题定位

## 使用示例

### 定义新的动作类

```python
from src.chat.focus_chat.planners.actions.plugin_action import PluginAction, register_action, ActionActivationType

@register_action
class MyAction(PluginAction):
    action_name = "my_action"
    action_description = "我的自定义动作"
    
    # 选择合适的激活类型
    action_activation_type = ActionActivationType.LLM_JUDGE
    
    # LLM判定的自定义提示词
    llm_judge_prompt = """
    判定是否激活my_action的条件：
    1. 用户明确要求执行特定操作
    2. 当前场景适合此动作
    3. 没有其他更合适的动作
    
    不应激活的情况：
    1. 普通聊天对话
    2. 用户只是随便说说
    """
    
    async def process(self):
        # 动作执行逻辑
        pass
```

### 关键词触发动作
```python
@register_action  
class SearchAction(PluginAction):
    action_name = "search_action"
    action_activation_type = ActionActivationType.KEYWORD
    activation_keywords = ["搜索", "查找", "什么是", "search", "find"]
    keyword_case_sensitive = False
```

### 随机触发动作
```python
@register_action
class SurpriseAction(PluginAction):
    action_name = "surprise_action" 
    action_activation_type = ActionActivationType.RANDOM
    random_activation_probability = 0.1  # 10%概率
```

## 性能监控

### 实时性能指标
```python
# 自动记录的性能指标
logger.debug(f"激活判定：{before_count} -> {after_count} actions")
logger.debug(f"并行LLM判定完成，耗时: {duration:.2f}s")  
logger.debug(f"使用缓存结果 {action_name}: {'激活' if result else '未激活'}")
logger.debug(f"清理了 {count} 个过期缓存条目")
logger.debug(f"并行调整动作、回忆和处理完成，耗时: {duration:.2f}s")
```

### 性能优化建议
1. **合理配置缓存时间**：根据聊天活跃度调整 `_cache_expiry_time`
2. **优化过滤规则**：根据实际使用情况调整 `_quick_filter_keywords`
3. **监控并行效果**：关注 `asyncio.gather` 的执行时间
4. **缓存命中率**：监控缓存使用情况，优化策略
5. **启用流程并行化**：确保 `parallel_processing` 配置为 `true`

## 测试验证

运行动作激活优化测试：
```bash
python test_action_activation_optimized.py
```

运行HFC并行化测试：
```bash
python test_parallel_optimization.py
```

测试内容包括：
- ✅ 并行处理功能验证
- ✅ 缓存机制效果测试  
- ✅ 分层判定规则验证
- ✅ 性能对比分析
- ✅ HFC流程并行化效果
- ✅ 多循环平均性能测试

## 最佳实践

### 1. 激活类型选择
- **ALWAYS**：reply, no_reply 等基础动作
- **LLM_JUDGE**：需要智能判断的复杂动作 
- **KEYWORD**：明确的命令式动作
- **RANDOM**：增趣动作，低概率触发

### 2. LLM判定提示词编写
- 明确描述激活条件和排除条件
- 避免模糊的描述
- 考虑边界情况
- 保持简洁明了

### 3. 关键词设置
- 包含同义词和英文对应词
- 考虑用户的不同表达习惯
- 避免过于宽泛的关键词
- 根据实际使用调整

### 4. 性能优化
- 定期监控处理时间
- 根据使用模式调整缓存策略
- 优化激活判定逻辑
- 平衡准确性和性能
- **启用并行处理配置**

### 5. 并行化最佳实践
- 在生产环境启用 `parallel_processing`
- 监控并行阶段的执行时间
- 确保各阶段的独立性
- 避免共享状态导致的竞争条件

## 总结

优化后的动作激活系统通过**四层优化策略**，实现了全方位的性能提升：

### 第一层：动作激活内部优化
- **并行判定**：多个LLM判定任务并行执行
- **智能缓存**：相同上下文的判定结果缓存复用
- **分层判定**：快速过滤 + 精确判定的两层架构

### 第二层：HFC流程级并行化
- **三阶段并行**：调整动作、回忆、处理器同时执行
- **性能提升**：2.3x 理论加速比
- **配置控制**：可根据环境灵活开启/关闭

### 综合效果
- **响应速度**：显著提升机器人反应速度
- **成本优化**：减少不必要的LLM调用
- **智能决策**：四种激活类型覆盖所有场景
- **用户体验**：更快速、更智能的交互

**总性能提升预估：3-5x**
- 动作激活系统内部优化：1.5-2x
- HFC流程并行化：2.3x
- 缓存和过滤优化：额外20-30%提升

这使得MaiBot能够更快速、更智能地响应用户需求，提供卓越的交互体验。

## 如何为Action添加激活类型

### 对于普通Action

```python
from src.chat.focus_chat.planners.actions.base_action import BaseAction, register_action, ActionActivationType

@register_action
class YourAction(BaseAction):
    action_name = "your_action"
    action_description = "你的动作描述"
    
    # 设置激活类型 - 关键词触发示例
    action_activation_type = ActionActivationType.KEYWORD
    activation_keywords = ["关键词1", "关键词2", "keyword"]
    keyword_case_sensitive = False
    
    # ... 其他代码
```

### 对于插件Action

```python
from src.chat.focus_chat.planners.actions.plugin_action import PluginAction, register_action, ActionActivationType

@register_action
class YourPluginAction(PluginAction):
    action_name = "your_plugin_action"
    action_description = "你的插件动作描述"
    
    # 设置激活类型 - 关键词触发示例
    action_activation_type = ActionActivationType.KEYWORD
    activation_keywords = ["触发词1", "trigger", "启动"]
    keyword_case_sensitive = False
    
    # ... 其他代码
```

## 现有Action的激活类型设置

### 基础动作 (ALWAYS)
- `reply` - 回复动作
- `no_reply` - 不回复动作

### LLM判定动作 (LLM_JUDGE)
- `vtb_action` - 虚拟主播表情
- `mute_action` - 禁言动作

### 关键词触发动作 (KEYWORD) 🆕
- `edge_search_action` - 网络搜索 (搜索、查找、什么是等)
- `pic_action` - 图片生成 (画、画图、生成图片等)
- `help_action` - 帮助功能 (帮助、help、求助等)

## 工作流程

1. **ActionModifier处理**: 在planner运行前，ActionModifier会遍历所有注册的动作
2. **类型判断**: 根据每个动作的激活类型决定是否激活
3. **激活决策**:
   - ALWAYS: 直接激活
   - RANDOM: 根据概率随机决定
   - LLM_JUDGE: 调用小模型判定
   - KEYWORD: 检测关键词匹配
4. **结果收集**: 收集所有激活的动作供planner使用

## 配置建议

### LLM判定提示词编写
- 明确指出激活条件和不激活条件
- 使用简单清晰的语言
- 避免过于复杂的逻辑判断

### 随机概率设置
- 核心功能: 不建议使用随机
- 娱乐功能: 0.1-0.3 (10%-30%)
- 辅助功能: 0.05-0.2 (5%-20%)

### 关键词设计
- 包含常用的同义词和变体
- 考虑中英文兼容
- 避免过于宽泛的词汇
- 测试关键词的覆盖率

### 性能考虑
- LLM判定会增加响应时间，适度使用
- 关键词检测性能最好，推荐优先使用
- 建议优先级：KEYWORD > ALWAYS > RANDOM > LLM_JUDGE

## 调试和测试

使用提供的测试脚本验证激活类型系统：

```bash
python test_action_activation.py
```

该脚本会显示：
- 所有注册动作的激活类型
- 模拟不同消息下的激活结果
- 帮助验证配置是否正确

## 注意事项

1. **向后兼容**: 未设置激活类型的动作默认为ALWAYS
2. **错误处理**: LLM判定失败时默认不激活该动作
3. **日志记录**: 系统会记录激活决策过程，便于调试
4. **性能影响**: LLM判定会略微增加响应时间

## 未来扩展

系统设计支持未来添加更多激活类型，如：
- 基于时间的激活
- 基于用户权限的激活
- 基于群组设置的激活 