# OpenAI vs Anthropic 协议详细对比

## 概述

虽然 OpenAI 和 Anthropic 都是通过 HTTP + JSON 进行通信，但两者的协议设计存在显著差异。本文档详细对比这两种协议的区别。

## 一、API 端点（Endpoint）

```python
# OpenAI 协议
POST /v1/chat/completions

# Anthropic 协议  
POST /v1/messages
```

## 二、System Prompt 处理

### OpenAI：作为消息数组的一部分

```python
# openai_client.py:128-129
if msg.role == "system":
    api_messages.append({"role": "system", "content": msg.content})
```

**请求示例：**
```json
{
  "model": "gpt-4",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant"},
    {"role": "user", "content": "Hello"}
  ]
}
```

**特点：**
- ✅ System prompt 在 `messages` 数组内
- ✅ 可以有多个 system 消息
- ✅ 可以插入在任何位置（通常在开头）

### Anthropic：独立的参数

```python
# anthropic_client.py:127-129
if msg.role == "system":
    system_message = msg.content
    continue  # 不加入 messages 数组
```

**请求示例：**
```json
{
  "model": "claude-3",
  "system": "You are a helpful assistant",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "max_tokens": 16384
}
```

**特点：**
- ✅ System prompt 是顶层独立参数
- ⚠️ 只能有一个 system（字符串）
- ✅ 与 messages 分离，语义更清晰

## 三、必需参数差异

### OpenAI

```json
{
  "model": "gpt-4",        // 必需
  "messages": [...]        // 必需
  // 其他都是可选
}
```

### Anthropic

```json
{
  "model": "claude-3",     // 必需
  "messages": [...],       // 必需
  "max_tokens": 16384      // 必需！
  // Anthropic 必须指定 max_tokens
}
```

**关键区别：**
- ⚠️ Anthropic 必须指定 `max_tokens`
- OpenAI 有默认值，可以不指定

## 四、Tool（工具）定义格式

### OpenAI：嵌套的 function 结构

```python
# openai_client.py:98-105
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "Get current weather",
    "parameters": {           // ← 字段名是 "parameters"
      "type": "object",
      "properties": {
        "city": {"type": "string", "description": "City name"}
      },
      "required": ["city"]
    }
  }
}
```

**特点：**
- 外层有 `type: "function"` 包裹
- 参数定义在 `function.parameters`
- 嵌套层级更深

### Anthropic：扁平的结构

```python
# anthropic_client.py:87-95
{
  "name": "get_weather",
  "description": "Get current weather",
  "input_schema": {          // ← 字段名是 "input_schema"
    "type": "object",
    "properties": {
      "city": {"type": "string", "description": "City name"}
    },
    "required": ["city"]
  }
}
```

**特点：**
- 没有外层 `type` 包裹
- 参数定义在顶层 `input_schema`
- 结构更扁平

### 转换函数对比

**OpenAI Client：**
```python
def _convert_tools(self, tools):
    result = []
    for tool in tools:
        result.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema
            }
        })
    return result
```

**Anthropic Client：**
```python
def _convert_tools(self, tools):
    result = []
    for tool in tools:
        result.append({
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema
        })
    return result
```

## 五、Tool Call（工具调用）格式

### OpenAI：在 assistant 消息中

```python
# openai_client.py:146-158
{
  "role": "assistant",
  "content": null,  // 可以为空
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "get_weather",
        "arguments": "{\"city\":\"Beijing\"}"  // JSON 字符串
      }
    }
  ]
}
```

**特点：**
- ✅ `arguments` 是 JSON 字符串（需要序列化）
- ✅ 有 `type: "function"` 字段
- ✅ `content` 可以为 `null`

### Anthropic：作为 content 块

```python
# anthropic_client.py:149-156
{
  "role": "assistant",
  "content": [
    {
      "type": "tool_use",
      "id": "toolu_abc123",
      "name": "get_weather",
      "input": {"city": "Beijing"}  // 直接是对象
    }
  ]
}
```

**特点：**
- ✅ `input` 是 JSON 对象（无需序列化）
- ✅ 作为 `content` 数组的一个块
- ✅ 可以和 text、thinking 块混合

## 六、Tool Result（工具结果）返回

### OpenAI：使用专门的 `tool` 角色

```python
# openai_client.py:171-178
{
  "role": "tool",           // ← 专门的角色
  "tool_call_id": "call_abc123",
  "content": "Temperature is 20°C, sunny"
}
```

**特点：**
- ✅ 有专门的 `tool` 角色
- ✅ 结构简单
- ✅ 通过 `tool_call_id` 关联

### Anthropic：使用 `user` 角色 + `tool_result` 块

```python
# anthropic_client.py:165-176
{
  "role": "user",           // ← 用 user 角色！
  "content": [
    {
      "type": "tool_result",
      "tool_use_id": "toolu_abc123",
      "content": "Temperature is 20°C, sunny"
    }
  ]
}
```

**特点：**
- ⚠️ 使用 `user` 角色，不是专门的 tool 角色
- ✅ 作为 content 块，可以包含多个结果
- ✅ 通过 `tool_use_id` 关联

### 为什么 Anthropic 用 user 角色？

**设计理念：**
- Tool 的结果被视为"来自外部世界的信息"
- 这些信息本质上是"提供给 AI 的输入"
- 因此归类为 `user` 角色更合理

## 七、Thinking（思考过程）处理

### OpenAI：使用 `reasoning_details`

```python
# openai_client.py:165-166
if msg.thinking:
    assistant_msg["reasoning_details"] = [{"text": msg.thinking}]
```

**请求格式：**
```json
{
  "role": "assistant",
  "content": "The answer is 42",
  "reasoning_details": [
    {"text": "Let me think step by step...\n1. First..."}
  ]
}
```

**响应格式：**
```python
# openai_client.py:219-224
if hasattr(message, "reasoning_details") and message.reasoning_details:
    for detail in message.reasoning_details:
        if hasattr(detail, "text"):
            thinking_content += detail.text
```

**特点：**
- ✅ `reasoning_details` 是数组
- ✅ 需要通过 `extra_body: {"reasoning_split": True}` 启用
- ✅ 与 `content` 平级

### Anthropic：使用 `thinking` 内容块

```python
# anthropic_client.py:139-140
if msg.thinking:
    content_blocks.append({"type": "thinking", "thinking": msg.thinking})
```

**请求格式：**
```json
{
  "role": "assistant",
  "content": [
    {"type": "thinking", "thinking": "Let me think step by step..."},
    {"type": "text", "text": "The answer is 42"}
  ]
}
```

**响应格式：**
```python
# anthropic_client.py:219-220
elif block.type == "thinking":
    thinking_content += block.thinking
```

**特点：**
- ✅ `thinking` 是 content 数组中的一个块
- ✅ 可以和 text、tool_use 块混合
- ✅ 顺序可控（thinking 通常在前）

## 八、消息内容结构

### OpenAI：灵活的字符串或数组

```python
# 简单消息
{
  "role": "assistant",
  "content": "This is a simple response"  // 字符串
}

# 带工具调用
{
  "role": "assistant",
  "content": null,  // 可以为空
  "tool_calls": [...]
}

# 多模态（图片等）
{
  "role": "user",
  "content": [  // 数组
    {"type": "text", "text": "What's in this image?"},
    {"type": "image_url", "image_url": {"url": "..."}}
  ]
}
```

### Anthropic：统一的内容块数组

```python
# 简单消息
{
  "role": "assistant",
  "content": "This is a simple response"  // 可以是字符串
}

# 或者
{
  "role": "assistant",
  "content": [  // 推荐用数组
    {"type": "text", "text": "This is a simple response"}
  ]
}

# 复杂消息（thinking + text + tool）
{
  "role": "assistant",
  "content": [
    {"type": "thinking", "thinking": "Let me analyze..."},
    {"type": "text", "text": "Based on my analysis..."},
    {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
  ]
}
```

**Anthropic 的内容块类型：**
- `text` - 文本内容
- `thinking` - 思考过程
- `tool_use` - 工具调用
- `tool_result` - 工具结果
- `image` - 图片（vision 模型）

## 九、Token 使用统计

### OpenAI：简单的三个字段

```python
# openai_client.py:247-251
usage = TokenUsage(
    prompt_tokens=response.usage.prompt_tokens,
    completion_tokens=response.usage.completion_tokens,
    total_tokens=response.usage.total_tokens
)
```

**响应示例：**
```json
{
  "usage": {
    "prompt_tokens": 56,
    "completion_tokens": 31,
    "total_tokens": 87
  }
}
```

### Anthropic：包含缓存统计

```python
# anthropic_client.py:238-247
input_tokens = response.usage.input_tokens
cache_read_tokens = response.usage.cache_read_input_tokens or 0
cache_creation_tokens = response.usage.cache_creation_input_tokens or 0
total_input_tokens = input_tokens + cache_read_tokens + cache_creation_tokens

usage = TokenUsage(
    prompt_tokens=total_input_tokens,
    completion_tokens=output_tokens,
    total_tokens=total_input_tokens + output_tokens
)
```

**响应示例：**
```json
{
  "usage": {
    "input_tokens": 56,
    "output_tokens": 31,
    "cache_read_input_tokens": 120,      // 从缓存读取
    "cache_creation_input_tokens": 200   // 写入缓存
  }
}
```

**Anthropic 的缓存机制：**
- ✅ 支持 Prompt Caching（提示词缓存）
- ✅ 显式区分缓存读取和创建的 token 数
- ✅ 缓存读取的 token 计费更便宜

## 十、完整请求示例对比

### 场景：带工具调用的多轮对话

#### OpenAI 协议

```json
POST /v1/chat/completions
{
  "model": "gpt-4",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful weather assistant"
    },
    {
      "role": "user",
      "content": "What's the weather in Beijing?"
    },
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\"city\":\"Beijing\"}"
        }
      }]
    },
    {
      "role": "tool",
      "tool_call_id": "call_abc123",
      "content": "20°C, sunny, humidity 45%"
    },
    {
      "role": "assistant",
      "content": "The weather in Beijing is sunny with a temperature of 20°C.",
      "reasoning_details": [{
        "text": "The user asked about weather, I called the tool and got the data."
      }]
    }
  ],
  "tools": [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Get current weather for a city",
      "parameters": {
        "type": "object",
        "properties": {
          "city": {
            "type": "string",
            "description": "City name"
          }
        },
        "required": ["city"]
      }
    }
  }],
  "extra_body": {
    "reasoning_split": true
  }
}
```

#### Anthropic 协议

```json
POST /v1/messages
{
  "model": "claude-3",
  "system": "You are a helpful weather assistant",
  "max_tokens": 16384,
  "messages": [
    {
      "role": "user",
      "content": "What's the weather in Beijing?"
    },
    {
      "role": "assistant",
      "content": [{
        "type": "tool_use",
        "id": "toolu_abc123",
        "name": "get_weather",
        "input": {"city": "Beijing"}
      }]
    },
    {
      "role": "user",
      "content": [{
        "type": "tool_result",
        "tool_use_id": "toolu_abc123",
        "content": "20°C, sunny, humidity 45%"
      }]
    },
    {
      "role": "assistant",
      "content": [
        {
          "type": "thinking",
          "thinking": "The user asked about weather, I called the tool and got the data."
        },
        {
          "type": "text",
          "text": "The weather in Beijing is sunny with a temperature of 20°C."
        }
      ]
    }
  ],
  "tools": [{
    "name": "get_weather",
    "description": "Get current weather for a city",
    "input_schema": {
      "type": "object",
      "properties": {
        "city": {
          "type": "string",
          "description": "City name"
        }
      },
      "required": ["city"]
    }
  }]
}
```

## 十一、核心差异总结表

| 特性 | OpenAI 协议 | Anthropic 协议 |
|-----|------------|----------------|
| **端点路径** | `/v1/chat/completions` | `/v1/messages` |
| **System Prompt** | 在 `messages` 数组内 | 独立的 `system` 参数 |
| **必需参数** | `model`, `messages` | `model`, `messages`, `max_tokens` |
| **Tool 定义** | `{type: "function", function: {...}}` | `{name, description, input_schema}` |
| **Tool 参数字段** | `parameters` | `input_schema` |
| **Tool 调用** | `tool_calls` 数组（arguments 是字符串） | `content` 块（input 是对象） |
| **Tool 结果** | `role: "tool"` | `role: "user"` + `tool_result` 块 |
| **Thinking** | `reasoning_details` 数组 | `thinking` 内容块 |
| **内容结构** | 字符串或数组（灵活） | 推荐统一用内容块数组 |
| **缓存统计** | 无 | 有（`cache_read/creation_tokens`） |
| **多模态** | `image_url` 类型 | `image` 块 |

## 十二、Mini-Agent 的统一抽象

尽管协议差异很大，Mini-Agent 通过以下方式统一了接口：

### 统一的输入

```python
# 不管用哪个协议，输入都是这样
messages = [
    Message(role="system", content="You are helpful"),
    Message(role="user", content="Hello"),
    Message(
        role="assistant",
        content="Hi there!",
        thinking="User greeted me, I should respond warmly",
        tool_calls=[...]
    ),
    Message(role="tool", tool_call_id="...", content="...")
]
```

### 统一的输出

```python
@dataclass
class LLMResponse:
    content: str                      # 统一的文本内容
    thinking: str | None              # 统一的思考过程
    tool_calls: list[ToolCall] | None # 统一的工具调用列表
    finish_reason: str
    usage: TokenUsage | None          # 统一的 token 统计
```

### 自动转换

```python
# OpenAI Client 自动转换
def _convert_messages(self, messages):
    # 把内部 Message 转换成 OpenAI 格式
    ...

# Anthropic Client 自动转换  
def _convert_messages(self, messages):
    # 把内部 Message 转换成 Anthropic 格式
    ...
```

## 十三、选择建议

### 何时选择 OpenAI 协议？

- ✅ 使用 OpenAI 官方模型（GPT-4 等）
- ✅ 使用 OpenAI 兼容的第三方服务（大多数国内模型）
- ✅ 生态工具支持更广泛

### 何时选择 Anthropic 协议？

- ✅ 使用 Claude 官方模型
- ✅ 需要利用 Prompt Caching 节省成本
- ✅ 喜欢更结构化的内容块设计
- ✅ 明确区分 thinking 和 text

### Mini-Agent 的策略

```python
# 同时支持两种协议，根据场景选择
llm = LLMClient(
    api_key="...",
    provider=LLMProvider.OPENAI,  # 或 ANTHROPIC
    api_base="...",
    model="..."
)
```

**优势：**
- ✅ 一套代码，两种协议
- ✅ 可以随时切换
- ✅ 充分利用各协议的特性
- ✅ 为未来的协议扩展留下空间

## 十四、未来趋势

### 协议标准化

- 行业正在向 OpenAI 协议靠拢
- 大多数新模型都优先支持 OpenAI 兼容接口
- Anthropic 协议主要用于 Claude 官方 API

### Mini-Agent 的应对

```python
# 灵活的架构，易于扩展
class LLMClient:
    def __init__(self, provider: LLMProvider):
        if provider == LLMProvider.OPENAI:
            self._client = OpenAIClient(...)
        elif provider == LLMProvider.ANTHROPIC:
            self._client = AnthropicClient(...)
        # 未来可以轻松添加新协议
        # elif provider == LLMProvider.GOOGLE:
        #     self._client = GoogleClient(...)
```

这种设计确保了 Mini-Agent 能够：
- 🎯 适应当前的双协议格局
- 🚀 快速支持新出现的协议
- 💪 为用户提供统一的编程体验
