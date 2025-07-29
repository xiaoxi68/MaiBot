# MaiBot 模型配置指南

本文档详细说明 MaiBot 的模型配置系统，包括 `model_config.toml` 和 `bot_config.toml` 中模型相关的配置项。

## 目录

1. [配置文件概述](#配置文件概述)
2. [model_config.toml 详细配置](#model_configtoml-详细配置)
3. [bot_config.toml 模型任务配置](#bot_configtoml-模型任务配置)
4. [任务类型和能力系统](#任务类型和能力系统)
5. [多API Key支持](#多api-key支持)
6. [配置示例](#配置示例)
7. [最佳实践](#最佳实践)
8. [故障排除](#故障排除)

## 配置文件概述

MaiBot 的模型配置分为两个文件：

- **`model_config.toml`**: 定义可用的模型、API提供商和基础配置
- **`bot_config.toml`**: 定义具体任务使用哪些模型以及模型参数

### 配置关系

```
model_config.toml → 定义模型池
                 ↓
bot_config.toml → 从模型池中选择模型用于具体任务
```

## model_config.toml 详细配置

### 基础结构

```toml
[inner]
version = "0.2.1"  # 配置文件版本

[request_conf]      # 全局请求配置
[[api_providers]]   # API服务提供商配置（可配置多个）
[[models]]          # 模型配置（可配置多个）
[task_model_usage]  # 任务模型使用配置
```

### 1. 请求配置 [request_conf]

全局的API请求配置，影响所有模型调用：

```toml
[request_conf]
max_retry = 2                    # 最大重试次数
timeout = 10                     # API调用超时时长（秒）
retry_interval = 10              # 重试间隔（秒）
default_temperature = 0.7        # 默认温度值
default_max_tokens = 1024        # 默认最大输出token数
```

**参数说明：**
- `max_retry`: 单个API调用失败时的最大重试次数
- `timeout`: 单次API调用的超时时间，超过此时间请求将被取消
- `retry_interval`: API调用失败后的重试间隔时间
- `default_temperature`: 当bot_config.toml中未设置时的默认温度值
- `default_max_tokens`: 当bot_config.toml中未设置时的默认最大输出token数

### 2. API提供商配置 [[api_providers]]

配置各个API服务商的连接信息，支持多个提供商：

```toml
[[api_providers]]
name = "DeepSeek"                           # 提供商名称（自定义）
base_url = "https://api.deepseek.cn/v1"     # API基础URL
api_keys = [                                # 多个API Key（推荐）
    "sk-your-first-key-here",
    "sk-your-second-key-here",
    "sk-your-third-key-here"
]
# 或者使用单个key（向后兼容）
# key = "sk-your-single-key-here"
client_type = "openai"                      # 客户端类型
```

**参数说明：**
- `name`: 提供商的自定义名称，在models配置中引用
- `base_url`: API服务的基础URL
- `api_keys`: API密钥数组，支持多个key实现负载均衡和错误切换
- `key`: 单个API密钥（向后兼容，建议使用api_keys）
- `client_type`: 客户端类型，可选值：
  - `"openai"`: OpenAI兼容格式（默认）
  - `"gemini"`: Google Gemini专用格式

#### 多API Key优势

1. **错误自动切换**: 当某个key失败时自动切换
2. **负载均衡**: 在多个key之间循环使用
3. **提高可用性**: 避免单点故障

#### 错误处理机制

- **401/403认证错误**: 立即切换到下一个API Key
- **429频率限制**: 等待后重试，持续失败则切换Key
- **网络错误**: 短暂等待后重试，失败则切换Key
- **其他错误**: 按照正常重试机制处理

### 3. 模型配置 [[models]]

定义可用的模型及其属性：

```toml
[[models]]
model_identifier = "deepseek-chat"          # API服务商的模型标识符
name = "deepseek-v3"                        # 自定义模型名称（可选）
api_provider = "DeepSeek"                   # 对应的API提供商名称
task_type = "llm_normal"                    # 任务类型（推荐配置）
capabilities = ["text", "tool_calling"]    # 模型能力列表（推荐配置）
price_in = 2.0                              # 输入价格（元/兆token）
price_out = 8.0                             # 输出价格（元/兆token）
force_stream_mode = false                   # 是否强制流式输出
```

**必填参数：**
- `model_identifier`: API服务商提供的模型标识符
- `api_provider`: 对应在api_providers中配置的服务商名称

**可选参数：**
- `name`: 自定义模型名称，如果不指定则使用model_identifier
- `task_type`: 模型主要任务类型（详见任务类型说明）
- `capabilities`: 模型支持的能力列表（详见能力说明）
- `price_in/price_out`: 用于统计API调用成本
- `force_stream_mode`: 当模型不支持非流式输出时启用

### 4. 任务模型使用配置 [task_model_usage]

定义系统任务使用的默认模型：

```toml
[task_model_usage]
llm_reasoning = {model="deepseek-r1", temperature=0.8, max_tokens=1024, max_retry=0}
llm_normal = {model="deepseek-v3", max_tokens=1024, max_retry=0}
embedding = "bge-m3"
# 可选：模型调度列表
# schedule = ["deepseek-v3", "deepseek-r1"]
```

## bot_config.toml 模型任务配置

### 模型任务分类

MaiBot 将不同功能分配给不同的模型以优化性能：

#### 核心对话模型

```toml
[model.replyer_1]                           # 首要回复模型
model_name = "siliconflow-deepseek-v3"      # 对应model_config.toml中的模型名称
temperature = 0.2                           # 模型温度（0.0-2.0）
max_tokens = 800                            # 最大输出token数

[model.replyer_2]                           # 次要回复模型
model_name = "siliconflow-deepseek-r1"
temperature = 0.7
max_tokens = 800
```

#### 功能性模型

```toml
[model.utils]                               # 通用工具模型
model_name = "siliconflow-deepseek-v3"      # 用于表情包、取名、关系等模块
temperature = 0.2
max_tokens = 800

[model.utils_small]                         # 小型工具模型
model_name = "qwen3-8b"                     # 用于高频率调用的场景
temperature = 0.7
max_tokens = 800
enable_thinking = false                     # 是否启用思考模式

[model.planner]                             # 决策模型
model_name = "siliconflow-deepseek-v3"      # 负责决定麦麦该做什么
temperature = 0.3
max_tokens = 800

[model.emotion]                             # 情绪模型
model_name = "siliconflow-deepseek-v3"      # 负责情绪变化
temperature = 0.3
max_tokens = 800

[model.memory]                              # 记忆模型
model_name = "qwen3-30b"                    # 用于记忆构建和管理
temperature = 0.7
max_tokens = 800
enable_thinking = false
```

#### 专用模型

```toml
[model.vlm]                                 # 视觉理解模型
model_name = "qwen2.5-vl-72b"              # 图像识别和理解
max_tokens = 800

[model.voice]                               # 语音识别模型
model_name = "sensevoice-small"             # 语音转文字

[model.tool_use]                            # 工具调用模型
model_name = "qwen3-14b"                    # 需要支持工具调用的模型
temperature = 0.7
max_tokens = 800
enable_thinking = false

[model.embedding]                           # 嵌入模型
model_name = "bge-m3"                       # 用于文本向量化
```

#### LPMM知识库模型

```toml
[model.lpmm_entity_extract]                 # 实体提取模型
model_name = "siliconflow-deepseek-v3"
temperature = 0.2
max_tokens = 800

[model.lpmm_rdf_build]                      # RDF构建模型
model_name = "siliconflow-deepseek-v3"
temperature = 0.2
max_tokens = 800

[model.lpmm_qa]                             # 问答模型
model_name = "deepseek-r1-distill-qwen-32b"
temperature = 0.7
max_tokens = 800
enable_thinking = false
```

### 模型参数说明

- **`model_name`**: 必填，对应model_config.toml中配置的模型名称
- **`temperature`**: 模型温度，控制回答的随机性（0.0-2.0）
  - 0.0-0.3: 确定性强，适合事实性任务
  - 0.4-0.7: 平衡创造性和准确性
  - 0.8-2.0: 创造性强，适合创意任务
- **`max_tokens`**: 单次回复的最大token数
- **`enable_thinking`**: 是否启用思考模式（仅支持特定模型）
- **`thinking_budget`**: 思考模式的最大token数

## 任务类型和能力系统

### 任务类型 (task_type)

明确指定模型的主要用途：

- **`llm_normal`**: 普通语言模型，用于一般对话
- **`llm_reasoning`**: 推理语言模型，用于复杂思考
- **`vision`**: 视觉模型，用于图像理解
- **`embedding`**: 嵌入模型，用于文本向量化
- **`speech`**: 语音模型，用于语音识别

### 能力列表 (capabilities)

描述模型支持的具体能力：

- **`text`**: 文本理解和生成
- **`vision`**: 图像理解
- **`embedding`**: 文本向量化
- **`speech`**: 语音处理
- **`tool_calling`**: 工具调用
- **`reasoning`**: 推理思考

### 配置优先级

系统按以下优先级确定模型任务类型：

1. **`task_type`** (最高优先级) - 直接指定任务类型
2. **`capabilities`** (中等优先级) - 根据能力推断任务类型
3. **模型名称关键字** (最低优先级) - 基于模型名称的关键字匹配

### 示例配置

```toml
# 推荐配置方式 - 明确指定任务类型和能力
[[models]]
model_identifier = "deepseek-chat"
name = "deepseek-v3"
api_provider = "DeepSeek"
task_type = "llm_normal"                    # 明确指定为普通语言模型
capabilities = ["text", "tool_calling"]    # 支持文本和工具调用

# 视觉模型示例
[[models]]
model_identifier = "Qwen/Qwen2.5-VL-72B-Instruct"
name = "qwen2.5-vl-72b"
api_provider = "SiliconFlow"
task_type = "vision"                        # 视觉任务
capabilities = ["vision", "text"]          # 支持视觉和文本

# 嵌入模型示例
[[models]]
model_identifier = "BAAI/bge-m3"
name = "bge-m3"
api_provider = "SiliconFlow"
task_type = "embedding"                     # 嵌入任务
capabilities = ["text", "embedding"]       # 支持文本和向量化
```

## 配置示例

### 完整的多提供商配置

```toml
# API提供商配置
[[api_providers]]
name = "DeepSeek"
base_url = "https://api.deepseek.cn/v1"
api_keys = [
    "sk-deepseek-key-1",
    "sk-deepseek-key-2"
]
client_type = "openai"

[[api_providers]]
name = "SiliconFlow"
base_url = "https://api.siliconflow.cn/v1"
key = "sk-siliconflow-key"
client_type = "openai"

[[api_providers]]
name = "Google"
base_url = "https://api.google.com/v1"
api_keys = ["google-api-key-1", "google-api-key-2"]
client_type = "gemini"

# 模型配置示例
[[models]]
model_identifier = "deepseek-chat"
name = "deepseek-v3"
api_provider = "DeepSeek"
task_type = "llm_normal"
capabilities = ["text", "tool_calling"]
price_in = 2.0
price_out = 8.0

[[models]]
model_identifier = "deepseek-reasoner"
name = "deepseek-r1"
api_provider = "DeepSeek"
task_type = "llm_reasoning"
capabilities = ["text", "tool_calling", "reasoning"]
price_in = 4.0
price_out = 16.0

[[models]]
model_identifier = "Pro/deepseek-ai/DeepSeek-V3"
name = "siliconflow-deepseek-v3"
api_provider = "SiliconFlow"
task_type = "llm_normal"
capabilities = ["text", "tool_calling"]
price_in = 2.0
price_out = 8.0
```

### bot_config.toml 任务配置示例

```toml
# 核心对话模型
[model.replyer_1]
model_name = "deepseek-v3"
temperature = 0.2
max_tokens = 800

[model.replyer_2]
model_name = "deepseek-r1"
temperature = 0.7
max_tokens = 800

# 工具模型
[model.utils]
model_name = "siliconflow-deepseek-v3"
temperature = 0.2
max_tokens = 800

[model.utils_small]
model_name = "qwen3-8b"
temperature = 0.7
max_tokens = 800
enable_thinking = false

# 专用模型
[model.vlm]
model_name = "qwen2.5-vl-72b"
max_tokens = 800

[model.embedding]
model_name = "bge-m3"
```
