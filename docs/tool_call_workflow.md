# Mini Agent 工具调用流程详解

本文档详细讲解 Mini Agent 是如何分析 LLM response、提取 tool call、执行工具并获取结果的完整流程。

## 📋 目录

1. [整体架构](#整体架构)
2. [核心数据结构](#核心数据结构)
3. [完整流程详解](#完整流程详解)
4. [代码实现分析](#代码实现分析)
5. [执行示例](#执行示例)

---

## 整体架构

Mini Agent 的工具调用流程涉及以下核心组件：

```
┌─────────────────────────────────────────────────────────────┐
│                         Agent                                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   Messages   │───▶│  LLM Client  │───▶│    Tools     │  │
│  │   History    │    │   (Anthropic │    │   Registry   │  │
│  │              │◀───│   /OpenAI)   │    │              │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
   保存对话历史           解析响应结构            执行具体工具
```

---

## 核心数据结构

### 1. ToolCall - 工具调用结构

位置：`mini_agent/schema/schema.py:21-26`

```python
class ToolCall(BaseModel):
    """工具调用结构"""
    id: str                    # 工具调用唯一标识符
    type: str                  # "function"
    function: FunctionCall     # 函数调用详情
```

### 2. FunctionCall - 函数调用详情

位置：`mini_agent/schema/schema.py:14-18`

```python
class FunctionCall(BaseModel):
    """函数调用详情"""
    name: str                  # 工具名称（如 "write_file", "bash_execute"）
    arguments: dict[str, Any]  # 工具参数字典
```

### 3. LLMResponse - LLM 响应

位置：`mini_agent/schema/schema.py:48-56`

```python
class LLMResponse(BaseModel):
    """LLM 响应结构"""
    content: str                      # 文本响应内容
    thinking: str | None = None       # 思考过程（如果有）
    tool_calls: list[ToolCall] | None # 工具调用列表
    finish_reason: str                # 结束原因
    usage: TokenUsage | None          # Token 使用统计
```

### 4. ToolResult - 工具执行结果

位置：`mini_agent/tools/base.py:8-13`

```python
class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool              # 是否成功
    content: str = ""          # 返回内容
    error: str | None = None   # 错误信息（如果失败）
```

---

## 完整流程详解

### 阶段 1: 发送请求到 LLM

**位置**：`mini_agent/agent.py:366-383`

```python
# 1. 获取所有可用工具
tool_list = list(self.tools.values())

# 2. 记录请求日志
self.logger.log_request(messages=self.messages, tools=tool_list)

# 3. 调用 LLM 生成响应（带工具列表）
try:
    response = await self.llm.generate(
        messages=self.messages,  # 对话历史
        tools=tool_list           # 可用工具列表
    )
except Exception as e:
    # 处理异常...
```

### 阶段 2: LLM Client 处理请求

**位置**：`mini_agent/llm/anthropic_client.py:257-293`

#### 2.1 转换消息格式

```python
def _convert_messages(self, messages: list[Message]) 
    -> tuple[str | None, list[dict[str, Any]]]:
    """
    将内部消息格式转换为 Anthropic API 格式
    
    转换规则：
    - system 消息 → 独立的 system 参数
    - assistant 消息（带 thinking/tool_calls）→ content blocks
    - tool 消息 → user 消息 + tool_result content block
    """
    system_message = None
    api_messages = []
    
    for msg in messages:
        if msg.role == "system":
            system_message = msg.content
        elif msg.role == "assistant" and (msg.thinking or msg.tool_calls):
            # 构建复杂的 content blocks
            content_blocks = []
            
            # 添加 thinking block
            if msg.thinking:
                content_blocks.append({
                    "type": "thinking", 
                    "thinking": msg.thinking
                })
            
            # 添加文本内容
            if msg.content:
                content_blocks.append({
                    "type": "text", 
                    "text": msg.content
                })
            
            # 添加 tool_use blocks
            if msg.tool_calls:
                for tool_call in msg.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "input": tool_call.function.arguments,
                    })
            
            api_messages.append({
                "role": "assistant", 
                "content": content_blocks
            })
```

#### 2.2 转换工具格式

```python
def _convert_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
    """
    将 Tool 对象转换为 Anthropic 工具格式
    
    Anthropic 工具格式：
    {
        "name": "工具名称",
        "description": "工具描述",
        "input_schema": {
            "type": "object",
            "properties": {...},
            "required": [...]
        }
    }
    """
    result = []
    for tool in tools:
        if hasattr(tool, "to_schema"):
            result.append(tool.to_schema())
    return result
```

#### 2.3 发起 API 请求

```python
async def _make_api_request(
    self,
    system_message: str | None,
    api_messages: list[dict[str, Any]],
    tools: list[Any] | None = None,
) -> anthropic.types.Message:
    """执行 API 请求"""
    params = {
        "model": self.model,
        "max_tokens": 16384,
        "messages": api_messages,
    }
    
    if system_message:
        params["system"] = system_message
    
    if tools:
        params["tools"] = self._convert_tools(tools)
    
    # 使用 Anthropic SDK 发送请求
    response = await self.client.messages.create(**params)
    return response
```

### 阶段 3: 解析 LLM 响应

**位置**：`mini_agent/llm/anthropic_client.py:202-255`

这是**最关键**的部分 - 从 LLM 返回的原始响应中提取工具调用信息。

```python
def _parse_response(self, response: anthropic.types.Message) -> LLMResponse:
    """
    解析 Anthropic 响应，提取：
    1. 文本内容
    2. 思考过程
    3. 工具调用
    """
    text_content = ""
    thinking_content = ""
    tool_calls = []
    
    # 遍历响应中的所有 content blocks
    for block in response.content:
        if block.type == "text":
            # 提取文本内容
            text_content += block.text
            
        elif block.type == "thinking":
            # 提取思考过程
            thinking_content += block.thinking
            
        elif block.type == "tool_use":
            # 🔑 关键：提取工具调用信息
            tool_calls.append(
                ToolCall(
                    id=block.id,              # 工具调用 ID
                    type="function",          # 固定为 "function"
                    function=FunctionCall(
                        name=block.name,      # 工具名称
                        arguments=block.input # 工具参数（dict）
                    ),
                )
            )
    
    # 提取 token 使用统计
    usage = None
    if hasattr(response, "usage") and response.usage:
        input_tokens = response.usage.input_tokens or 0
        output_tokens = response.usage.output_tokens or 0
        usage = TokenUsage(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )
    
    # 返回统一的 LLMResponse 结构
    return LLMResponse(
        content=text_content,
        thinking=thinking_content if thinking_content else None,
        tool_calls=tool_calls if tool_calls else None,
        finish_reason=response.stop_reason or "stop",
        usage=usage,
    )
```

**Anthropic API 原始响应示例**：

```json
{
  "id": "msg_123",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "thinking",
      "thinking": "用户想要创建一个 Python 文件..."
    },
    {
      "type": "text",
      "text": "我将为您创建 hello.py 文件"
    },
    {
      "type": "tool_use",
      "id": "toolu_abc123",
      "name": "write_file",
      "input": {
        "file_path": "hello.py",
        "content": "def greet(name):\n    print(f'Hello, {name}!')\n\ngreet('Mini Agent')"
      }
    }
  ],
  "stop_reason": "tool_use",
  "usage": {
    "input_tokens": 1024,
    "output_tokens": 256
  }
}
```

**解析后的 LLMResponse**：

```python
LLMResponse(
    content="我将为您创建 hello.py 文件",
    thinking="用户想要创建一个 Python 文件...",
    tool_calls=[
        ToolCall(
            id="toolu_abc123",
            type="function",
            function=FunctionCall(
                name="write_file",
                arguments={
                    "file_path": "hello.py",
                    "content": "def greet(name):\n    print(f'Hello, {name}!')\n\ngreet('Mini Agent')"
                }
            )
        )
    ],
    finish_reason="tool_use",
    usage=TokenUsage(prompt_tokens=1024, completion_tokens=256, total_tokens=1280)
)
```

### 阶段 4: 处理响应并执行工具

**位置**：`mini_agent/agent.py:397-421`

```python
# 1. 更新 token 统计
if response.usage:
    self.api_total_tokens = response.usage.total_tokens

# 2. 记录响应日志
self.logger.log_response(
    content=response.content,
    thinking=response.thinking,
    tool_calls=response.tool_calls,
    finish_reason=response.finish_reason,
)

# 3. 将响应添加到对话历史
assistant_msg = Message(
    role="assistant",
    content=response.content,
    thinking=response.thinking,
    tool_calls=response.tool_calls,  # 包含工具调用信息
)
self.messages.append(assistant_msg)

# 4. 打印思考过程和响应内容
if response.thinking:
    print(f"🧠 Thinking: {response.thinking}")

if response.content:
    print(f"🤖 Assistant: {response.content}")

# 5. 检查是否需要执行工具
if not response.tool_calls:
    # 没有工具调用，任务完成
    return response.content
```

### 阶段 5: 执行工具调用

**位置**：`mini_agent/agent.py:430-502`

```python
# 遍历所有工具调用
for tool_call in response.tool_calls:
    tool_call_id = tool_call.id
    function_name = tool_call.function.name
    arguments = tool_call.function.arguments
    
    # 打印工具调用信息
    print(f"🔧 Tool Call: {function_name}")
    print(f"   Arguments: {json.dumps(arguments, indent=2)}")
    
    # 执行工具
    if function_name not in self.tools:
        # 工具不存在
        result = ToolResult(
            success=False,
            content="",
            error=f"Unknown tool: {function_name}",
        )
    else:
        try:
            # 🔑 关键：获取工具对象并执行
            tool = self.tools[function_name]
            result = await tool.execute(**arguments)
            
        except Exception as e:
            # 捕获执行异常，转换为 ToolResult
            import traceback
            error_detail = f"{type(e).__name__}: {str(e)}"
            error_trace = traceback.format_exc()
            result = ToolResult(
                success=False,
                content="",
                error=f"Tool execution failed: {error_detail}\n\nTraceback:\n{error_trace}",
            )
    
    # 记录工具执行结果
    self.logger.log_tool_result(
        tool_name=function_name,
        arguments=arguments,
        result_success=result.success,
        result_content=result.content if result.success else None,
        result_error=result.error if not result.success else None,
    )
    
    # 打印结果
    if result.success:
        print(f"✓ Result: {result.content[:300]}")
    else:
        print(f"✗ Error: {result.error}")
    
    # 🔑 关键：将工具结果添加到对话历史
    tool_msg = Message(
        role="tool",
        content=result.content if result.success else f"Error: {result.error}",
        tool_call_id=tool_call_id,  # 关联到原始工具调用
        name=function_name,
    )
    self.messages.append(tool_msg)
```

### 阶段 6: 循环继续

执行完所有工具后，对话历史更新为：

```
[
    Message(role="system", content="You are..."),
    Message(role="user", content="Create a Python file..."),
    Message(role="assistant", content="我将创建文件", tool_calls=[...]),
    Message(role="tool", content="File created successfully", tool_call_id="toolu_abc123", name="write_file"),
]
```

然后 Agent 继续下一步循环：
1. 再次调用 LLM，传入更新后的历史（包含工具执行结果）
2. LLM 基于工具结果决定下一步操作
3. 重复此过程，直到任务完成（没有工具调用）或达到最大步数

---

## 代码实现分析

### 1. 工具基类设计

**位置**：`mini_agent/tools/base.py:16-55`

```python
class Tool:
    """所有工具的基类"""
    
    @property
    def name(self) -> str:
        """工具名称（必须实现）"""
        raise NotImplementedError
    
    @property
    def description(self) -> str:
        """工具描述（必须实现）"""
        raise NotImplementedError
    
    @property
    def parameters(self) -> dict[str, Any]:
        """
        工具参数 schema（JSON Schema 格式）
        例如：
        {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "content": {
                    "type": "string",
                    "description": "文件内容"
                }
            },
            "required": ["file_path", "content"]
        }
        """
        raise NotImplementedError
    
    async def execute(self, *args, **kwargs) -> ToolResult:
        """执行工具（必须实现）"""
        raise NotImplementedError
    
    def to_schema(self) -> dict[str, Any]:
        """转换为 Anthropic 工具 schema"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }
    
    def to_openai_schema(self) -> dict[str, Any]:
        """转换为 OpenAI 工具 schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
```

### 2. 工具注册机制

**位置**：`mini_agent/agent.py:48-58`

```python
def __init__(
    self,
    llm_client: LLMClient,
    system_prompt: str,
    tools: list[Tool],
    max_steps: int = 50,
    workspace_dir: str = "./workspace",
    token_limit: int = 80000,
):
    self.llm = llm_client
    
    # 🔑 将工具列表转换为字典，方便快速查找
    self.tools = {tool.name: tool for tool in tools}
    # 结果：{"write_file": WriteTool实例, "read_file": ReadTool实例, ...}
```

### 3. 工具查找和执行

```python
# 快速查找工具
if function_name not in self.tools:
    result = ToolResult(success=False, error="Unknown tool")
else:
    tool = self.tools[function_name]  # O(1) 查找
    result = await tool.execute(**arguments)  # 解包参数执行
```

### 4. 异常处理策略

```python
try:
    tool = self.tools[function_name]
    result = await tool.execute(**arguments)
except Exception as e:
    # 捕获所有异常，转换为 ToolResult
    # 这样可以将错误信息返回给 LLM，让它决定如何处理
    result = ToolResult(
        success=False,
        content="",
        error=f"Tool execution failed: {str(e)}\n\n{traceback.format_exc()}",
    )
```

**为什么这样设计？**
- 不让异常中断整个 Agent 循环
- 将错误信息传递给 LLM，让它可以：
  - 修正参数重试
  - 选择其他工具
  - 向用户报告问题

---

## 执行示例

### 示例 1: 文件创建任务

**用户输入**：
```
Create a Python file named 'hello.py' with a greet function
```

**执行流程**：

#### Step 1: LLM 分析任务

**Request to LLM**:
```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant..."},
    {"role": "user", "content": "Create a Python file named 'hello.py' with a greet function"}
  ],
  "tools": [
    {
      "name": "write_file",
      "description": "Write content to a file",
      "input_schema": {
        "type": "object",
        "properties": {
          "file_path": {"type": "string"},
          "content": {"type": "string"}
        },
        "required": ["file_path", "content"]
      }
    }
  ]
}
```

**LLM Response**:
```json
{
  "content": [
    {
      "type": "text",
      "text": "I'll create the hello.py file with a greet function"
    },
    {
      "type": "tool_use",
      "id": "toolu_01A",
      "name": "write_file",
      "input": {
        "file_path": "hello.py",
        "content": "def greet(name):\n    print(f'Hello, {name}!')\n\ngreet('Mini Agent')"
      }
    }
  ]
}
```

#### Step 2: 解析并执行工具

```python
# 解析得到
tool_call = ToolCall(
    id="toolu_01A",
    type="function",
    function=FunctionCall(
        name="write_file",
        arguments={
            "file_path": "hello.py",
            "content": "def greet(name):\n    print(f'Hello, {name}!')\n\ngreet('Mini Agent')"
        }
    )
)

# 执行工具
tool = self.tools["write_file"]  # 获取 WriteTool 实例
result = await tool.execute(
    file_path="hello.py",
    content="def greet(name):\n    print(f'Hello, {name}!')\n\ngreet('Mini Agent')"
)

# 结果
result = ToolResult(
    success=True,
    content="File 'hello.py' created successfully with 3 lines",
    error=None
)
```

#### Step 3: 将结果返回给 LLM

```python
# 添加工具结果到对话历史
tool_msg = Message(
    role="tool",
    content="File 'hello.py' created successfully with 3 lines",
    tool_call_id="toolu_01A",
    name="write_file"
)
self.messages.append(tool_msg)
```

#### Step 4: LLM 确认完成

**Request to LLM** (第二轮):
```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "Create a Python file..."},
    {
      "role": "assistant",
      "content": [
        {"type": "text", "text": "I'll create the hello.py file..."},
        {"type": "tool_use", "id": "toolu_01A", "name": "write_file", "input": {...}}
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "type": "tool_result",
          "tool_use_id": "toolu_01A",
          "content": "File 'hello.py' created successfully with 3 lines"
        }
      ]
    }
  ],
  "tools": [...]
}
```

**LLM Response**:
```json
{
  "content": [
    {
      "type": "text",
      "text": "✅ I've successfully created the hello.py file with a greet function that prints 'Hello, {name}!' and calls it with 'Mini Agent'."
    }
  ],
  "stop_reason": "end_turn"
}
```

**没有 tool_calls，任务完成！**

---

### 示例 2: 多工具协作

**用户输入**：
```
Create a Python script, then run it
```

**执行流程**：

#### Step 1: 创建文件
```
LLM → tool_use: write_file
Tool → Result: "File created"
```

#### Step 2: 执行文件
```
LLM → tool_use: bash_execute
Tool → Result: "Hello, Mini Agent!"
```

#### Step 3: 报告结果
```
LLM → text: "Script created and executed successfully. Output: Hello, Mini Agent!"
```

**对话历史**：
```python
[
    Message(role="system", ...),
    Message(role="user", content="Create a Python script, then run it"),
    Message(role="assistant", tool_calls=[write_file]),
    Message(role="tool", content="File created", tool_call_id="toolu_01"),
    Message(role="assistant", tool_calls=[bash_execute]),
    Message(role="tool", content="Hello, Mini Agent!", tool_call_id="toolu_02"),
    Message(role="assistant", content="Script created and executed successfully..."),
]
```

---

## 关键设计决策

### 1. 为什么使用统一的 ToolResult？

```python
class ToolResult(BaseModel):
    success: bool
    content: str = ""
    error: str | None = None
```

**优势**：
- 所有工具返回统一格式，便于处理
- 明确区分成功/失败状态
- 错误信息可以传递给 LLM，让它决定如何恢复

### 2. 为什么将工具结果作为 Message 添加到历史？

```python
tool_msg = Message(
    role="tool",
    content=result.content,
    tool_call_id=tool_call_id,
    name=function_name,
)
self.messages.append(tool_msg)
```

**原因**：
- LLM 需要看到工具执行结果才能决定下一步
- 符合 Anthropic/OpenAI API 的对话模式
- 保持完整的上下文，支持多轮工具调用

### 3. 为什么使用 tool_call_id 关联？

```python
tool_call_id = tool_call.id  # "toolu_abc123"
```

**作用**：
- 一次可能有多个工具调用
- ID 确保结果与正确的调用关联
- API 要求每个 tool_result 必须引用一个 tool_use

### 4. 为什么不直接返回字符串？

```python
# ❌ 不好
async def execute(self, **kwargs) -> str:
    return "File created"

# ✅ 好
async def execute(self, **kwargs) -> ToolResult:
    return ToolResult(success=True, content="File created")
```

**原因**：
- 需要区分成功/失败
- 需要携带错误信息
- 支持未来扩展（如返回图片、文件等）

---

## 总结

Mini Agent 的工具调用流程可以概括为：

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 准备阶段                                                  │
│    • 将 Tool 对象转换为 API schema                           │
│    • 构建包含工具列表的请求                                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. LLM 分析                                                  │
│    • LLM 分析任务和可用工具                                  │
│    • 决定调用哪些工具及参数                                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. 响应解析（核心）                                          │
│    • 遍历 response.content blocks                            │
│    • 提取 type="tool_use" 的 blocks                          │
│    • 构建 ToolCall 对象（id, name, arguments）               │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. 工具执行                                                  │
│    • 根据 function_name 查找工具对象                         │
│    • 调用 tool.execute(**arguments)                          │
│    • 捕获异常并转换为 ToolResult                             │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. 结果回馈                                                  │
│    • 将 ToolResult 包装为 Message(role="tool")               │
│    • 添加到对话历史                                          │
│    • 继续下一轮循环                                          │
└─────────────────────────────────────────────────────────────┘
```

**核心要点**：

1. **统一抽象**：通过 `ToolCall`、`FunctionCall`、`ToolResult` 等数据类提供清晰的类型定义
2. **协议转换**：`AnthropicClient._parse_response()` 是关键，将 API 响应转换为统一格式
3. **循环执行**：工具结果作为消息添加到历史，LLM 可以基于结果继续决策
4. **错误处理**：异常转换为 ToolResult，不中断流程，让 LLM 有机会恢复
5. **扩展性**：通过继承 `Tool` 基类可以轻松添加新工具

这个设计让 Agent 能够：
- 支持多种 LLM 提供商（Anthropic、OpenAI）
- 灵活添加新工具
- 处理复杂的多步骤任务
- 从错误中恢复

