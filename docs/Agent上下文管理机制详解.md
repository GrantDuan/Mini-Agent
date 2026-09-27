# Agent 上下文管理机制详解

> 基于 Mini-Agent 的实际实现，深入理解 Agent 如何管理对话历史和上下文。

---

## 📚 目录

1. [概述](#概述)
2. [五层上下文管理机制](#五层上下文管理机制)
3. [消息累积](#1️⃣-消息累积基础层)
4. [消息顺序和配对](#2️⃣-消息顺序和配对协议层)
5. [Token 计数和监控](#3️⃣-token-计数和监控资源层)
6. [自动总结压缩](#4️⃣-自动总结压缩优化层)
7. [总结生成机制](#5️⃣-总结生成机制元认知层)
8. [完整流程图](#完整的上下文管理流程)
9. [为什么需要复杂的管理](#为什么需要这么复杂的管理)

---

## 概述

### 什么是上下文管理？

**上下文（Context）** = Agent 与 LLM 交互的完整历史记录

```python
context = {
    "系统提示": "You are Mini-Agent...",
    "用户消息": ["创建算法艺术", "添加更多颜色"],
    "助手响应": ["好的，让我加载技能...", "已添加配色方案..."],
    "工具调用": [get_skill(), read_file(), write_file()],
    "工具结果": ["技能内容...", "模板内容...", "写入成功"]
}
```

### 为什么重要？

- ✅ LLM 是**无状态**的，每次调用都需要完整的历史
- ✅ 上下文决定了 LLM 的"记忆"和决策依据
- ✅ 管理不当会导致 Token 超限、成本飙升、性能下降

---

## 五层上下文管理机制

| 层级 | 功能 | 目的 |
|------|------|------|
| **1. 消息累积** | 把所有交互记录到列表 | 保存完整历史 |
| **2. 消息顺序和配对** | 维护严格的消息顺序和关联 | 符合 API 协议 |
| **3. Token 监控** | 实时估算和跟踪 Token 使用 | 防止超限 |
| **4. 自动总结压缩** | 超限时智能压缩历史 | 节省 Token 和成本 |
| **5. 总结生成** | 用 LLM 总结 LLM 的历史 | 保留核心信息 |

---

## 1️⃣ 消息累积（基础层）

### 核心概念

所有交互都追加到一个消息列表中：

```python
class Agent:
    def __init__(self):
        self.messages = []  # 消息历史列表

    def add_message(self, role, content):
        self.messages.append({
            "role": role,        # system / user / assistant / tool
            "content": content   # 消息内容
        })
```

### 消息的四种角色

```python
# 1. System（系统提示）
{"role": "system", "content": "You are Mini-Agent..."}

# 2. User（用户输入）
{"role": "user", "content": "创建一个算法艺术作品"}

# 3. Assistant（LLM 响应）
{
    "role": "assistant",
    "content": "好的，让我加载相关技能...",
    "tool_calls": [...]  # 可能包含工具调用
}

# 4. Tool（工具执行结果）
{
    "role": "tool",
    "content": "技能内容已加载...",
    "tool_call_id": "call_abc123",  # 关联到具体的 tool_call
    "name": "get_skill"
}
```

### 消息累积示例

```python
# 初始状态
messages = [
    {"role": "system", "content": "You are Mini-Agent..."}
]

# 用户发起任务
messages.append({"role": "user", "content": "创建算法艺术"})

# LLM 响应
messages.append({
    "role": "assistant",
    "content": "让我加载技能",
    "tool_calls": [{"id": "call_1", "function": {"name": "get_skill", ...}}]
})

# 工具结果
messages.append({
    "role": "tool",
    "content": "技能内容...",
    "tool_call_id": "call_1"
})

# ... 不断累积
```

---

## 2️⃣ 消息顺序和配对（协议层）

### 严格的顺序要求

LLM API 要求消息必须遵循特定顺序：

```
✅ 正确的顺序：
system
→ user
→ assistant (with tool_calls)
→ tool (关联 tool_call_id)
→ tool (关联 tool_call_id)
→ assistant (next response)
→ ...

❌ 错误的顺序：
assistant → assistant          # 缺少中间的 tool
tool → assistant               # tool 没有对应的 tool_call
user → tool                    # tool 必须跟在 assistant 后
```

### tool_call_id 配对机制

**问题**：一个 Step 可能有多个 tool_calls，LLM 怎么知道哪个结果对应哪个请求？

**答案**：通过 `tool_call_id` 关联

#### 实现代码

```python
# mini_agent/agent.py:398-404
# Step 1: 先添加 assistant 消息（包含 tool_calls）
assistant_msg = Message(
    role="assistant",
    content=response.content,
    thinking=response.thinking,
    tool_calls=response.tool_calls,  # ← 包含工具调用请求
)
self.messages.append(assistant_msg)

# Step 2: 然后添加每个工具的结果
for tool_call in response.tool_calls:
    result = await tool.execute(**tool_call.function.arguments)

    # mini_agent/agent.py:495-501
    tool_msg = Message(
        role="tool",
        content=result.content,
        tool_call_id=tool_call.id,  # ← 关联到具体的 tool_call
        name=function_name,
    )
    self.messages.append(tool_msg)
```

#### 配对示例

```python
# LLM 发出多个工具调用
{
  "role": "assistant",
  "tool_calls": [
    {
      "id": "call_abc123",
      "function": {"name": "read_file", "arguments": {"path": "a.txt"}}
    },
    {
      "id": "call_def456",
      "function": {"name": "read_file", "arguments": {"path": "b.txt"}}
    }
  ]
}

# Agent 返回对应的结果
{
  "role": "tool",
  "tool_call_id": "call_abc123",  # ← 对应第一个请求
  "name": "read_file",
  "content": "Content of a.txt"
}

{
  "role": "tool",
  "tool_call_id": "call_def456",  # ← 对应第二个请求
  "name": "read_file",
  "content": "Content of b.txt"
}
```

### 为什么顺序很重要？

1. **API 协议要求**：OpenAI/Anthropic API 会验证消息顺序
2. **LLM 理解依赖**：顺序错误会导致 LLM 无法理解上下文
3. **工具结果匹配**：tool_call_id 必须对应之前的 tool_call

---

## 3️⃣ Token 计数和监控（资源层）

### 为什么需要监控 Token？

- **API 限制**：Claude 200K tokens，GPT-4 128K tokens
- **成本控制**：Token 使用量直接影响费用
- **性能优化**：Token 越多，LLM 处理越慢

### 双重检查机制

```python
# mini_agent/agent.py:198-201
estimated_tokens = self._estimate_tokens()  # 本地估算

# 检查两个来源的 token 数量
should_summarize = (
    estimated_tokens > self.token_limit or       # 本地估算超限
    self.api_total_tokens > self.token_limit     # API 报告超限
)
```

### 两种计数方式对比

| 方式 | 来源 | 计算时机 | 优点 | 缺点 |
|------|------|---------|------|------|
| **本地估算** | tiktoken `cl100k_base` 逐条实际编码 | 每次调用前 | 实时、无延迟；接近真实分词 | 按消息 +4 估算固定开销，与真实模板有偏差 |
| **API 报告** | LLM 返回的 `usage.total_tokens` | 调用后 | 绝对精确 | 延迟一轮 |

### Token 估算实现

本地估算**不是**简单的"字符数/4"，而是真的调 tiktoken 编码一遍：

```python
# mini_agent/agent.py:123-158
def _estimate_tokens(self) -> int:
    """Accurately calculate token count for message history using tiktoken"""
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
    except Exception:
        # tiktoken 不可用时才降级
        return self._estimate_tokens_fallback()

    total_tokens = 0
    for msg in self.messages:
        if isinstance(msg.content, str):
            total_tokens += len(encoding.encode(msg.content))
        elif isinstance(msg.content, list):          # 多模态 / block 形式
            for block in msg.content:
                if isinstance(block, dict):
                    total_tokens += len(encoding.encode(str(block)))

        if msg.thinking:                              # 思考内容也计入
            total_tokens += len(encoding.encode(msg.thinking))
        if msg.tool_calls:
            total_tokens += len(encoding.encode(str(msg.tool_calls)))

        total_tokens += 4                             # 每条消息的元数据开销

    return total_tokens
```

降级路径才是"字符数估算"，且系数是 **2.5** 不是 4：

```python
# mini_agent/agent.py:160-178
def _estimate_tokens_fallback(self) -> int:
    """Fallback token estimation method (when tiktoken is unavailable)"""
    total_chars = 0
    # ... 累加 content / thinking / tool_calls 的字符数
    # Rough estimation: average 2.5 characters = 1 token
    return int(total_chars / 2.5)
```

> ⚠️ 注意 `encoding.encode()` 是在**整个消息历史**上逐条跑的。历史越长，
> 这一步越贵——它本身也是上下文管理的一个隐性成本。

### API Token 更新

```python
# mini_agent/agent.py:386-387
if response.usage:
    self.api_total_tokens = response.usage.total_tokens
```

### 监控输出示例

```
📊 Token usage - Local estimate: 85234, API reported: 87456, Limit: 100000
🔄 Triggering message history summarization...
```

---

## 4️⃣ 自动总结压缩（优化层）

### 问题：消息越来越长

```
Step 1:  system + user + 5 messages   →   1K tokens
Step 5:  system + user + 20 messages  →  10K tokens
Step 10: system + user + 50 messages  →  30K tokens ⚠️
Step 15: system + user + 80 messages  →  50K tokens ❌ 接近上限
Step 20: system + user + 120 messages →  80K tokens ❌ 严重超限
```

### 解决方案：智能总结

当 Token 超限时，自动压缩历史消息：

```python
# mini_agent/agent.py:353
await self._summarize_messages()  # 每个 Step 开始前检查
```

### 总结策略

```python
# mini_agent/agent.py:183-188
"""
Strategy (Agent mode):
- 保留所有 user 消息（这些是用户意图，不能丢失）
- 总结每两个 user 之间的 agent 执行过程
- 结构: system → user1 → summary1 → user2 → summary2 → user3
"""
```

### 总结前后对比

#### 原始消息（50K tokens）

```python
[
    {"role": "system", "content": "You are Mini-Agent..."},
    {"role": "user", "content": "创建算法艺术"},

    # 20 条详细的执行过程
    {"role": "assistant", "content": "加载技能..."},
    {"role": "tool", "content": "技能内容 2800 行..."},
    {"role": "assistant", "content": "读取模板..."},
    {"role": "tool", "content": "模板内容 600 行..."},
    {"role": "tool", "content": "模板内容 223 行..."},
    {"role": "assistant", "content": "创建哲学文档..."},
    {"role": "tool", "content": "写入成功"},
    # ... 更多消息
]
```

#### 总结后（15K tokens）

```python
[
    {"role": "system", "content": "You are Mini-Agent..."},
    {"role": "user", "content": "创建算法艺术"},

    # 压缩为一条总结（注意：以 user 角色注入）
    {"role": "user", "content": """[Assistant Execution Summary]

Round 1 execution process:
- Loaded algorithmic-art skill with templates and guidelines
- Read viewer.html template (600 lines) and generator template (223 lines)
- Created algorithmic philosophy document "ink-tide-philosophy.md"
- Generated interactive HTML artwork "ink-tide.html" with p5.js
- Opened artwork in browser successfully

Key results:
- Philosophy: "墨汐 · Ink Tide" generative art movement
- Implementation: Flow field with dual-octave noise, ink particles
- Parameters: 7 sliders for customization
- All files created successfully
    """}
]
```

### 压缩效果

```
原始: 50K tokens (20 条详细消息)
  ↓ 总结压缩
压缩: 15K tokens (1 条总结)

节省: 70% tokens
效果: 保留核心信息，去除冗余细节
```

### 关键实现细节

```python
# mini_agent/agent.py:250-255
# 用总结后的新列表替换原列表
self.messages = new_messages

# 跳过下一次 token 检查，避免连续触发总结
# （api_total_tokens 要等下一次 LLM 调用才会更新）
self._skip_next_token_check = True
```

**为什么需要 `_skip_next_token_check`？**
总结刚完成时，`api_total_tokens` 还是旧的（超限的）数值。
如果不跳过检查，会立刻再次触发总结 → 死循环。
等下一次真实 LLM 调用返回新的 usage 后再恢复检查。

---

## 5️⃣ 总结生成机制（元认知层）

### 核心思想：用 LLM 总结 LLM

Agent 使用 LLM 来总结之前的 LLM 执行历史！🤯

### 总结生成流程

```python
# mini_agent/agent.py:262-319
async def _create_summary(self, messages: list[Message], round_num: int) -> str:
    """为一轮执行创建总结"""

    # Step 1: 构建执行过程描述
    summary_content = f"Round {round_num} execution process:\n\n"

    for msg in messages:
        if msg.role == "assistant":
            content_text = msg.content if isinstance(msg.content, str) else str(msg.content)
            summary_content += f"Assistant: {content_text}\n"
            if msg.tool_calls:
                tool_names = [tc.function.name for tc in msg.tool_calls]
                summary_content += f"  → Called tools: {', '.join(tool_names)}\n"

        elif msg.role == "tool":
            # ⚠️ 这里没有截断！工具返回的完整内容原样进 prompt
            result_preview = msg.content if isinstance(msg.content, str) else str(msg.content)
            summary_content += f"  ← Tool returned: {result_preview}...\n"

    # Step 2: 构建总结提示词（注意：还额外带了一条 system 消息）
    summary_prompt = f"""Please provide a concise summary of the following Agent execution process:

{summary_content}

Requirements:
1. Focus on what tasks were completed and which tools were called
2. Keep key execution results and important findings
3. Be concise and clear, within 1000 words
4. Use English
5. Do not include "user" related content, only summarize the Agent's execution process"""

    # Step 3: 调用 LLM 生成总结
    response = await self.llm.generate(
        messages=[
            Message(role="system",
                    content="You are an assistant skilled at summarizing Agent execution processes."),
            Message(role="user", content=summary_prompt),
        ]
    )
    summary_text = response.content

    return summary_text
    # 异常时降级：return summary_content（原始拼接文本，不经 LLM）
```

### 总结示例

#### 输入（执行过程）

```
Round 1 execution process:

Assistant: 我来帮您创建一个算法艺术作品。首先让我加载相关技能获取专业指导。
  → Called tools: get_skill
  ← Tool returned: # Skill: algorithmic-art ... (2800 行技能内容)...
Assistant: 技能已加载。按照流程，我先读取模板文件作为起点：
  → Called tools: read_file, read_file
  ← Tool returned: <!DOCTYPE html> ... (600 行 HTML 模板)...
  ← Tool returned: /** P5.JS GENERATIVE ART ... (223 行 JS 模板)...
Assistant: 两个文件已创建完成。让我在浏览器中打开作品供您预览：
  → Called tools: bash
  ← Tool returned: (no output)
```

#### 输出（LLM 生成的总结）

```
The agent loaded the algorithmic-art skill (p5.js generative art guide),
read two template files (viewer.html and generator_template.js) from the
skill directory, created an algorithmic philosophy document and an
interactive HTML artwork based on the templates, then opened the artwork
in the browser. All operations succeeded.
```

> 🚨 **这个例子本身就是"没有截断"的证据。**
>
> 上面那 2800 行技能内容 + 600 行 HTML + 223 行 JS，是**原封不动**拼进
> 总结 prompt 的（源码里没有 `[:200]`）。也就是说：
>
> - **总结这一步本来是省 token 的**，却先把全部原始工具输出当成输入——
>   "压缩"动作本身吃掉了一次完整的历史
> - 输入 3600+ 行，输出 60 词。压缩比很高，但那 3600 行的输入账是实打实付了
> - 若输出已是极限，这一步**可能直接超上下文窗口**而失败
>
> 这属于 #10 的"**工具上下文预算**"问题：压缩前应先做分级/预截断，
> 而不是把工具输出无条件全量注入。

### 总结的注入方式

```python
# 总结以 user 角色注入（不能是 assistant，否则破坏配对规则）
summary_message = Message(
    role="user",
    content=f"[Assistant Execution Summary]\n\n{summary_text}",
)
new_messages.append(summary_message)
```

**为什么用 user 角色？**
- 顺序规则要求 assistant+tool_calls 后必须跟 tool
- 直接删除 assistant/tool 消息不会破坏协议
- user 消息天然可以独立存在
- LLM 会把总结当作"任务背景说明"来理解

---

## 完整的上下文管理流程

```
┌─────────────────────────────────────────────────────────┐
│                    Agent 运行循环                         │
└─────────────────────────────────────────────────────────┘

for step in range(max_steps):

    ┌─────────────────────────────────────────────┐
    │ ① Token 检查（每个 Step 开始前）              │
    │    estimated_tokens > limit ?                │
    │    api_total_tokens > limit ?                │
    │         ↓ 超限                               │
    │    _summarize_messages()                     │
    │    · 保留 system + 所有 user 消息            │
    │    · 每轮执行过程 → LLM 生成总结             │
    │    · 替换 messages 列表                      │
    │    · 设置 _skip_next_token_check = True      │
    └─────────────────────────────────────────────┘
                      ↓
    ┌─────────────────────────────────────────────┐
    │ ② 调用 LLM（发送完整 messages 历史）         │
    │    response = llm.generate(messages, tools)  │
    │    api_total_tokens = response.usage         │
    └─────────────────────────────────────────────┘
                      ↓
    ┌─────────────────────────────────────────────┐
    │ ③ 没有 tool_calls？ → 任务完成，返回 content │
    └─────────────────────────────────────────────┘
                      ↓ 有 tool_calls
    ┌─────────────────────────────────────────────┐
    │ ④ 追加 assistant 消息（含 tool_calls）       │
    │ ⑤ 逐个执行工具，追加 tool 消息               │
    │    （tool_call_id 严格配对）                 │
    └─────────────────────────────────────────────┘
                      ↓
                  回到 ①
```

---

## 为什么需要这么复杂的管理？

### 问题 1：Token 限制

```
Claude: 200K tokens
GPT-4:  128K tokens
MiniMax: 各系列不同

如果不压缩，长任务的 20 步就可能超限 ❌
超限后 API 直接报错，任务失败
```

### 问题 2：成本

```
每次 LLM 调用都要传所有历史（消息按输入计费）

Step 1:   1K tokens 输入
Step 10: 30K tokens 输入
Step 20: 50K tokens 输入  ← 单次调用贵 50 倍！

累计输入 = 1+2+3+...+20 ≈ 210K tokens（不压缩时）
压缩后每步保持 ~15K，累计 ≈ 300K → 90K（省 70%）
```

### 问题 3：性能

```
历史越长 → LLM 处理越慢（attention 计算量与长度相关）
50K tokens 可能需要 10-20 秒处理
压缩到 15K 后显著提速
```

### 问题 4：噪声干扰

```
大量中间过程消息（工具原始输出）会稀释关键信息
LLM 可能被无关细节干扰，降低决策质量
总结 = 信息浓缩 = 更好的决策依据
```

---

## 🎓 最终总结

**上下文管理 ≠ 简单的"把消息加入列表"**

它是一个包含 **5 层机制** 的完整系统：

| 层 | 机制 | 关键代码 |
|---|------|---------|
| 1 | **累积**：保存完整历史 | `self.messages.append(msg)` |
| 2 | **配对**：tool_call_id 关联请求与结果 | `Message(role="tool", tool_call_id=...)` |
| 3 | **监控**：本地估算 + API 报告双重检查 | `_estimate_tokens()` + `api_total_tokens` |
| 4 | **压缩**：超限时自动总结历史 | `_summarize_messages()` |
| 5 | **元认知**：用 LLM 总结 LLM 的执行历史 | `_create_summary()` |

### 一句话记忆

> **上下文管理就是在"完整记忆"和"有限窗口"之间做平衡：
> 平时全量累积，超限时用 LLM 把过程浓缩成摘要，永远保住用户的原始意图。**
