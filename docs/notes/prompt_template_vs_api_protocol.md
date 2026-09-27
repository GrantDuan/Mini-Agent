# Prompt 模板 vs API 协议

## 核心概念

### API 协议（网络通信层）
定义了**如何与 LLM 服务通信**的标准规范。

### Prompt 模板（模型输入层）
定义了**模型实际接收的文本格式**，包含特殊 token 和对话结构。

## 一、层次关系

```
┌─────────────────────────────────────────┐
│        你的代码（Mini-Agent）            │
│        messages = [...]                  │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│         LLMClient（选择协议）            │
│    provider = OPENAI / ANTHROPIC        │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│      API 协议层（HTTP + JSON）          │
│  • 构造请求：POST /v1/chat/completions  │
│  • JSON 序列化                          │
│  • 发送到远程服务器                      │
└─────────────────┬───────────────────────┘
                  │ HTTP Request
                  ▼
┌─────────────────────────────────────────┐
│      远程服务器（如 MiniMax/DashScope） │
│  • 解析 API 协议                        │
│  • 提取 messages                        │
│  • **应用 Prompt 模板**                 │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│         实际的 LLM 模型                 │
│  接收已格式化的文本：                    │
│  <|im_start|>user\nHello<|im_end|>...  │
└─────────────────────────────────────────┘
```

## 二、API 协议详解

### 定义内容

| 层面 | 内容 |
|------|------|
| **端点路径** | `/v1/chat/completions` vs `/v1/messages` |
| **请求结构** | JSON 字段名、嵌套方式 |
| **响应结构** | 返回数据的格式 |
| **流式传输** | Server-Sent Events (SSE) 格式 |
| **工具调用** | Tool call 的 JSON 格式 |

### OpenAI 协议示例

```json
POST /v1/chat/completions
{
  "model": "qwen-max",
  "messages": [
    {"role": "system", "content": "You are helpful"},
    {"role": "user", "content": "Explain AI agent"}
  ],
  "temperature": 0.7
}
```

### Anthropic 协议示例

```json
POST /v1/messages
{
  "model": "qwen-max",
  "system": "You are helpful",
  "messages": [
    {"role": "user", "content": "Explain AI agent"}
  ],
  "max_tokens": 1024
}
```

### 协议特点

- ✅ **标准化高**：OpenAI 和 Anthropic 是行业事实标准
- ✅ **可互换**：同一个模型可以支持多种协议
- ✅ **跨模型兼容**：不同模型可以使用相同协议

## 三、Prompt 模板详解

### 定义内容

| 层面 | 内容 |
|------|------|
| **特殊 Token** | `<|im_start|>`, `<|begin_of_text|>` 等 |
| **对话结构** | 如何组织 user/assistant 轮次 |
| **停止标记** | `<|im_end|>`, `<|eot_id|>` 等 |
| **工具调用格式** | XML 标签 vs 特殊 token |

### Qwen（ChatML 格式）

```text
<|im_start|>system
You are a helpful assistant.<|im_end|>
<|im_start|>user
Explain what an AI agent is?<|im_end|>
<|im_start|>assistant
An AI agent is...<|im_end|>
```

**特点：**
- 无全局 BOS token
- Stop token: `["<|im_end|>"]`
- 工具调用：`<tool_call>` / `<tool_response>` XML 标签

### Llama 3（Llama3 格式）

```text
<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are a helpful assistant.<|eot_id|><|start_header_id|>user<|end_header_id|>

Explain what an AI agent is?<|eot_id|><|start_header_id|>assistant<|end_header_id|>

An AI agent is...<|eot_id|>
```

**特点：**
- `<|begin_of_text|>` 整个对话开头只出现一次
- Stop token: `["<|eot_id|>", "<|end_of_text|>"]`
- 工具调用：`<|eom_id|>` 特殊 token 标记

### 模板特点

- ❌ **标准化低**：每个模型训练时决定，各不相同
- ❌ **不可互换**：必须匹配模型
- ❌ **硬编码风险**：用错模板会导致输出崩坏

## 四、实际转换流程

### 场景：调用 Qwen 模型

```python
# 1. 你的代码
llm = LLMClient(
    api_key="sk-xxx",
    provider=LLMProvider.OPENAI,  # ← API 协议
    api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model="qwen-max"  # ← Prompt 模板由这个决定
)

messages = [
    Message(role="user", content="What is AI?")
]

response = await llm.generate(messages)
```

```python
# 2. OpenAI Client 发送（API 协议层）
POST /compatible-mode/v1/chat/completions
{
  "model": "qwen-max",
  "messages": [
    {"role": "user", "content": "What is AI?"}
  ]
}
```

```python
# 3. DashScope 服务器处理
# a. 解析 API 协议（OpenAI 格式）
# b. 识别 model="qwen-max"
# c. 查找对应的 Prompt 模板：ChatML
# d. 转换

input_text = """<|im_start|>user
What is AI?<|im_end|>
<|im_start|>assistant
"""

# e. 送入 Qwen 模型
# f. 检测 stop token: <|im_end|>
```

## 五、为什么容易混淆？

### 相同点

- 都处理对话消息
- 都涉及 user/assistant 角色
- 都需要处理工具调用

### 不同点

| 维度 | API 协议 | Prompt 模板 |
|------|---------|------------|
| **定义者** | OpenAI、Anthropic | 模型训练团队 |
| **作用域** | 网络通信 | 模型输入 |
| **格式** | JSON | 纯文本 + 特殊 token |
| **可见性** | 开发者可见 | 通常对开发者隐藏 |
| **标准化** | 高 | 低 |

## 六、工具调用的双层处理

### API 协议层（标准化）

**OpenAI 协议：**
```json
{
  "tools": [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "parameters": {"type": "object", "properties": {...}}
    }
  }],
  "tool_calls": [{
    "id": "call_123",
    "type": "function",
    "function": {
      "name": "get_weather",
      "arguments": "{\"city\":\"Beijing\"}"
    }
  }]
}
```

### Prompt 模板层（模型相关）

**Qwen 内部格式（XML）：**
```xml
<|im_start|>assistant
<tool_call>
{"name": "get_weather", "arguments": {"city": "Beijing"}}
</tool_call><|im_end|>
<|im_start|>tool
{"temperature": 20}<|im_end|>
```

**Llama3 内部格式（特殊 token）：**
```text
<|start_header_id|>assistant<|end_header_id|>

{"name": "get_weather", "arguments": {"city": "Beijing"}}<|eom_id|>
<|start_header_id|>ipython<|end_header_id|>

{"temperature": 20}<|eot_id|>
```

## 七、常见的坑

### 坑 1：本地部署时硬编码模板

```python
# ❌ 错误：用 Llama 模板调用 Qwen 模型
def format_prompt_llama3(messages):
    prompt = "<|begin_of_text|>"
    for msg in messages:
        prompt += f"<|start_header_id|>{msg.role}<|end_header_id|>\n\n"
        prompt += f"{msg.content}<|eot_id|>"
    return prompt

# 如果把这个送给 Qwen 模型...
qwen_model.generate(format_prompt_llama3(messages))
# 结果：Qwen 不认识这些 token，输出崩坏
```

### 坑 2：混淆协议和模板

```python
# ❌ 错误理解
"我用 OpenAI 协议，所以只能调用 OpenAI 模型？"

# ✅ 正确理解
"OpenAI 协议是通信格式，任何支持这个协议的模型都能调用
包括 Qwen、Llama、DeepSeek 等"
```

### 坑 3：忘记云服务自动处理模板

```python
# ❌ 不必要的担心
"我需要自己处理 Qwen 的 ChatML 格式吗？"

# ✅ 云服务已处理
# 当你使用 DashScope、MiniMax 等云服务时
# 服务器会根据 model 参数自动应用正确的模板
# 你只需要关心 API 协议即可
```

## 八、Mini-Agent 的设计优势

### 只关心 API 协议

```python
# mini_agent/llm/openai_client.py
async def generate(self, messages, tools):
    # 只处理 OpenAI 协议的 JSON 构造
    payload = {
        "model": self.model,  # ← 模板由服务器根据这个决定
        "messages": [msg.to_dict() for msg in messages],
    }
    
    # 发送给服务器
    response = await self.client.post("/v1/chat/completions", json=payload)
    
    # 只解析 OpenAI 协议的返回
    return self._parse_response(response)
```

### Prompt 模板交给服务器

- ✅ **云服务负责**：DashScope、MiniMax 等自动处理
- ✅ **模型匹配**：服务器保证模板与模型匹配
- ✅ **无需维护**：新模型出现时无需修改客户端代码

### 统一抽象

```python
# 统一的输入
messages = [Message(role="user", content="...")]

# 统一的输出
class LLMResponse:
    content: str
    thinking: str | None
    tool_calls: list[ToolCall] | None
```

## 九、何时需要关心 Prompt 模板？

### 需要关心的场景

1. **本地部署开源模型**（如用 Ollama 运行 Llama）
   - 需要自己构造 Prompt
   - 需要设置正确的 stop tokens

2. **微调模型**
   - 训练数据需要使用正确的模板格式
   - 保持与基座模型一致

3. **调试模型行为**
   - 理解模型实际看到的输入
   - 排查输出异常

### 不需要关心的场景

1. **使用云服务 API**（MiniMax、DashScope、OpenAI、Anthropic）
   - 服务器自动处理
   - 只需选择正确的 API 协议

2. **使用 Mini-Agent 等封装库**
   - 库已处理协议层
   - 专注业务逻辑即可

## 十、总结

### 类比

```
API 协议 = 信封格式（怎么寄信）
  - 收信人地址怎么写
  - 邮票贴哪里
  - 信封大小规格

Prompt 模板 = 信纸格式（收信人怎么读）
  - 称呼怎么写
  - 正文怎么排版
  - 落款怎么签
```

### 关系

```
你用 OpenAI 协议（信封）可以寄给 Qwen（收信人）
但 Qwen 内部用 ChatML 格式（信纸）来读内容
服务器会帮你把信封里的内容转换成正确的信纸格式
```

### 实践建议

| 角色 | 关注点 |
|------|-------|
| **应用开发者** | 只需关心 API 协议 |
| **模型训练者** | 需要设计和实现 Prompt 模板 |
| **服务提供商** | 负责协议到模板的转换 |
| **本地部署者** | 两者都需要关心 |

### Mini-Agent 的策略

- ✅ **协议层抽象**：支持 OpenAI 和 Anthropic 两种协议
- ✅ **模板层托管**：交给云服务自动处理
- ✅ **统一接口**：屏蔽底层差异
- ✅ **易于扩展**：新协议只需加新 Client，新模型无需改动

这就是为什么 Mini-Agent 用两个 Client 就能支持众多模型的原因！
