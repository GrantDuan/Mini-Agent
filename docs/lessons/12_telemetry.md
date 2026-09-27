# Lesson 12 - Telemetry (Runtime Observability)

## What Question Are We Answering?

**"What is my agent actually doing at runtime?"**

Evals tell you if the agent works before deployment. Telemetry tells you what's happening during deployment. Without telemetry, debugging is guesswork.

## What You Will Build

A telemetry system that:
- Logs every LLM call with inputs and outputs
- Tracks tool call success/failure rates
- Measures latency and retry counts
- Enables post-hoc debugging with traces

## New Concepts Introduced

### 1. Structured Logging

**Structured logging** means JSON logs, not print statements. Every log entry has a consistent schema: timestamp, event type, data, error.

```json
{"event_type": "llm_call", "timestamp": "2024-01-15T10:30:00", "duration_ms": 1523, "success": true}
```

This is searchable, parseable, and machine-readable.

### 2. Spans and Traces

A **span** is one operation - a single LLM call, one tool execution, one memory access.

A **trace** is a full agent interaction - multiple spans linked together by a trace ID.

When something fails, you find the trace and see exactly what happened step by step.

### 3. Metrics

**Metrics** are aggregated numbers:
- `llm_success_rate` - How often does JSON parse correctly?
- `avg_latency_ms` - How long do LLM calls take?
- `tool_failure_rate` - How often do tool calls fail?

Metrics tell you the health of your agent at a glance.

## What We Are NOT Doing (Yet)

- No distributed tracing (single machine only)
- No production dashboards (file-based logging)
- No alerting (manual inspection)
- No OpenTelemetry (keeping it simple)

## The Code

Look at `agent/telemetry.py`:

```python
import json
import time
from datetime import datetime
from uuid import uuid4
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Span:
    """A single operation in a trace."""
    span_id: str
    trace_id: str
    event_type: str
    timestamp: str
    duration_ms: Optional[float] = None
    data: Optional[dict] = None
    error: Optional[str] = None


@dataclass
class Metrics:
    """Aggregated metrics for the agent."""
    llm_calls: int = 0
    llm_failures: int = 0
    llm_retries: int = 0
    tool_calls: int = 0
    tool_failures: int = 0
    total_latency_ms: float = 0.0
    
    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.llm_calls if self.llm_calls > 0 else 0.0
    
    @property
    def llm_success_rate(self) -> float:
        return 1 - (self.llm_failures / self.llm_calls) if self.llm_calls > 0 else 0.0


class Telemetry:
    """Simple telemetry for agent observability."""
    
    def __init__(self, log_file: str = "agent_telemetry.jsonl"):
        self.log_file = log_file
        self.current_trace_id = None
        self.metrics = Metrics()
    
    def start_trace(self) -> str:
        """Start a new trace (one full agent interaction)."""
        self.current_trace_id = str(uuid4())[:8]
        return self.current_trace_id
    
    def log_llm_call(self, prompt_length: int, response_length: int, 
                     duration_ms: float, success: bool = True, error: str = None):
        """Log an LLM call."""
        span = Span(
            span_id=str(uuid4())[:8],
            trace_id=self.current_trace_id or "no-trace",
            event_type="llm_call",
            timestamp=datetime.now().isoformat(),
            duration_ms=round(duration_ms, 2),
            data={"prompt_length": prompt_length, "response_length": response_length},
            error=error
        )
        
        # Write to log file
        with open(self.log_file, "a") as f:
            f.write(json.dumps(asdict(span)) + "\n")
        
        # Update metrics
        self.metrics.llm_calls += 1
        self.metrics.total_latency_ms += duration_ms
        if not success:
            self.metrics.llm_failures += 1
```

Notice:
- **Dataclasses** - Clean, typed structures
- **JSONL format** - One JSON object per line, easy to parse
- **Metrics accumulation** - Track aggregates as we go
- **Trace linking** - All spans share a trace ID

## How to Run

Look at `complete_example.py`, see `lesson_12_telemetry()` method:

```python
from agent.agent import Agent
from agent.telemetry import Telemetry

agent = Agent("models/llama-3-8b-instruct.gguf")
telemetry = Telemetry()

# Start a trace
trace_id = telemetry.start_trace()
print(f"Trace ID: {trace_id}")

# Simulate some operations (in real usage, these come from instrumented agent)
import time

start = time.time()
result = agent.generate_structured("What is Python?", '{"answer": string}')
duration = (time.time() - start) * 1000

telemetry.log_llm_call(
    prompt_length=100,
    response_length=len(str(result)),
    duration_ms=duration,
    success=result is not None
)

# Check metrics
telemetry.print_summary()
```

Example output:

```
========================================
TELEMETRY SUMMARY
========================================
LLM Calls:      3
  Success Rate: 100.00%
  Avg Latency:  1245ms
  Retries:      0
Tool Calls:     2
  Success Rate: 100.00%
Memory Ops:     1
========================================
```

## Viewing the Log File

The telemetry logs to `agent_telemetry.jsonl`:

```jsonl
{"span_id": "a1b2c3d4", "trace_id": "x9y8z7w6", "event_type": "llm_call", "timestamp": "2024-01-15T10:30:00.123456", "duration_ms": 1523.45, "data": {"prompt_length": 256, "response_length": 89, "success": true}}
{"span_id": "e5f6g7h8", "trace_id": "x9y8z7w6", "event_type": "tool_call", "timestamp": "2024-01-15T10:30:02.456789", "duration_ms": 5.23, "data": {"tool": "calculator", "arguments": {"a": 42, "b": 7, "operation": "multiply"}}}
```

To debug a specific interaction, filter by trace_id:
```bash
grep "x9y8z7w6" agent_telemetry.jsonl
```

## What to Log

| Event | Data to Capture | Why |
|-------|-----------------|-----|
| LLM call | prompt_length, response_length, duration_ms, success | Track latency, identify slow/failing calls |
| Tool request | tool_name, arguments | Debug wrong tool selection |
| Tool execution | tool_name, result, error | Debug tool failures |
| Memory operation | operation, data | Track what's being stored/retrieved |
| Decision | choices, selected | Debug routing issues |

## Compare to Lesson 11

**Lesson 11 (Evals):**
- Run before deployment
- Known inputs, expected outputs
- Binary pass/fail
- Catches regressions

**Lesson 12 (Telemetry):**
- Run during deployment
- Unknown inputs, observed outputs
- Continuous monitoring
- Enables debugging

They're complementary. Evals prevent bad code from shipping. Telemetry helps you understand what shipped code is doing.

## Key Insights

### Telemetry is Just Structured Logging

No magic. You're writing JSON to a file. The power is in:
- Consistent schema
- Trace IDs linking related events
- Aggregated metrics

### Traces Are Your Debugging Superpower

When a user reports "the agent gave a weird answer", you:
1. Get the trace ID
2. Find all spans for that trace
3. See exactly what happened

Without traces, you're guessing.

### Metrics Tell You System Health

Glance at metrics to know if something's wrong:
- Success rate dropping? Check for prompt issues
- Latency increasing? Check model/hardware
- Retries increasing? Check JSON parsing

### Start Simple, Add More Later

This implementation logs to a file. That's enough to start. Later you might add:
- Database storage
- Real-time dashboards
- Alerting on thresholds

But start with a file.

## Common Issues

**"The log file is too big"**
- Rotate logs (new file per day/hour)
- Only log failures in production
- Truncate long data fields

**"I can't find the trace I need"**
- Add trace IDs to user-facing errors
- Log trace IDs in your application logs
- Consider adding user IDs to traces

**"Telemetry is slowing down my agent"**
- Log asynchronously (buffer, then write)
- Reduce data captured per span
- Sample instead of logging everything

## Exercises

1. Add telemetry to the agent loop and trace a full multi-step interaction
2. Calculate JSON parse success rate across 20 structured output calls
3. Compare latency between different prompt lengths
4. Find a failing span in the logs and debug what went wrong

## What's Next?

Congratulations! You've completed the core curriculum.

You now have an agent with:
- Structured outputs (Lesson 03)
- Decision making (Lesson 04)
- Tool calling (Lesson 05)
- Agent loop (Lesson 06)
- Memory (Lesson 07)
- Planning (Lesson 08)
- Atomic actions (Lesson 09)
- Dependency graphs (Lesson 10)
- Regression testing (Lesson 11)
- Runtime observability (Lesson 12)

This is a complete, observable, testable agent built from first principles.

---

**Key Takeaway:** Telemetry = structured logging + traces + metrics. It turns "something's wrong" into "here's exactly what happened."
