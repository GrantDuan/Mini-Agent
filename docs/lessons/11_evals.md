# Lesson 11 - Evals (Regression Testing for Agents)

## What Question Are We Answering?

**"How do I know if my agent still works after I change something?"**

Once you have tools, memory, and structured outputs, changing a prompt becomes risky. A small wording change can break JSON parsing. An "improvement" can make tool calls less reliable. Without evals, quality degrades silently.

An eval suite is just a Python file that runs your agent and asserts things didn't break.

## What You Will Build

An evaluation system that:
- Tests prompt and JSON parsing reliability
- Validates tool call accuracy
- Checks memory storage and retrieval cycles
- Catches regressions before deployment

## New Concepts Introduced

### 1. Eval Suites

An **eval suite** is a collection of test cases that validate agent behavior. Each case has an input and an expected outcome. You run the suite after every prompt change.

This isn't magic - it's just running your agent with known inputs and checking the outputs.

### 2. Golden Datasets

A **golden dataset** is your source of truth - known-good examples that must always pass. If a golden case fails, the agent is broken (not the test).

Golden datasets are version controlled alongside your prompts. When you change a prompt, you run the golden dataset to verify nothing broke.

### 3. Hard vs Soft Assertions

**Hard assertions** must always pass:
- JSON must be valid
- Required fields must be present
- Tool names must match available tools

**Soft assertions** should usually pass:
- The answer is semantically correct
- The phrasing is appropriate
- The tool arguments are optimal

Start with hard assertions. Add soft ones later.

## Why This Fails in the Real World

A prompt change that improves phrasing can:
- Increase verbosity
- Push JSON out of context window
- Break parsing
- ...without changing correctness

This is why evals exist. They catch these silent failures.

## What We Are NOT Doing (Yet)

- No runtime monitoring ([Lesson 12](12_telemetry.md))
- No A/B testing
- No production observability
- No LLM-as-judge evals (too complex for now)

## The Code

Look at `agent/evals.py`:

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalResult:
    """Result of a single eval case."""
    passed: bool
    input: str
    expected: Any = None
    actual: Any = None
    error: str | None = None


@dataclass 
class EvalSuiteResult:
    """Result of running an eval suite."""
    name: str
    passed: int = 0
    failed: int = 0
    results: list[EvalResult] = field(default_factory=list)
    
    @property
    def pass_rate(self) -> float:
        return self.passed / (self.passed + self.failed) if (self.passed + self.failed) > 0 else 0.0
    
    def summary(self) -> str:
        status = "✓ PASSED" if self.failed == 0 else "✗ FAILED"
        return f"{self.name}: {status} ({self.passed}/{self.passed + self.failed})"


class AgentEval:
    """Regression testing for agent capabilities."""
    
    def __init__(self, agent):
        self.agent = agent
    
    def test_structured_output(self, cases: list[dict]) -> EvalSuiteResult:
        """Test that structured output parses correctly and matches schema."""
        suite = EvalSuiteResult(name="Structured Output")
        
        for case in cases:
            result = self.agent.generate_structured(case["input"], case["schema"])
            
            # Check 1: Did we get valid JSON?
            if result is None:
                suite.add_result(EvalResult(
                    passed=False,
                    input=case["input"],
                    error="Failed to parse JSON"
                ))
                continue
            
            # Check 2: Are required fields present?
            missing = [f for f in case.get("must_have_fields", []) if f not in result]
            if missing:
                suite.add_result(EvalResult(
                    passed=False,
                    input=case["input"],
                    error=f"Missing fields: {missing}"
                ))
                continue
            
            suite.add_result(EvalResult(passed=True, input=case["input"], actual=result))
        
        return suite
```

Notice:
- **Plain Python** - No testing framework needed
- **Structured results** - Each result captures input, expected, actual, error
- **Composable** - Run one suite or many
- **Actionable** - Failures tell you exactly what went wrong

## The Golden Dataset

Look at `evals/golden_datasets.py`:

```python
STRUCTURED_OUTPUT_GOLDEN = [
    {
        "input": "Explain quantum computing in one sentence",
        "schema": """{
  "topic": "the topic name as a string",
  "difficulty": "beginner" or "intermediate" or "advanced"
}

Example: {"topic": "machine learning", "difficulty": "intermediate"}""",
        "must_have_fields": ["topic", "difficulty"]
    },
]

TOOL_CALL_GOLDEN = [
    {
        "input": "What is 42 * 7?",
        "expected_tool": "calculator",
        "expected_args": {"operation": "multiply"}
    },
]

MEMORY_GOLDEN = [
    {
        "store_input": "My name is Alice",
        "query_input": "What's my name?",
        "expected_in_response": "Alice"
    },
]
```

Notice:
- **Multi-line schemas with examples** - Single-line schemas often confuse models
- **Version controlled** - These live in your repo
- **Cover edge cases** - Special characters, numbers, etc.
- **Specific assertions** - Not "it works" but "this field exists"

## How to Run

Look at `complete_example.py`, see `lesson_11_evals()` method:

```python
from agent.agent import Agent
from agent.evals import AgentEval, print_eval_report
from evals.golden_datasets import (
    STRUCTURED_OUTPUT_GOLDEN,
    TOOL_CALL_GOLDEN,
    MEMORY_GOLDEN
)

agent = Agent("models/llama-3-8b-instruct.gguf")
evaluator = AgentEval(agent)

# Run all evals
results = evaluator.run_all(
    structured_cases=STRUCTURED_OUTPUT_GOLDEN,
    tool_cases=TOOL_CALL_GOLDEN,
    memory_cases=MEMORY_GOLDEN
)

# Print report
print_eval_report(results)
```

Example output:

```
==================================================
EVAL REPORT
==================================================

Structured Output: ✓ PASSED (4/4)
Tool Calls: ✓ PASSED (5/5)
Memory Cycle: ✓ PASSED (3/3)

--------------------------------------------------
Overall: ✓ ALL PASSED (12/12)
==================================================
```

Or when something breaks:

```
==================================================
EVAL REPORT
==================================================

Structured Output: ✗ FAILED (3/4)
  ✗ Input: What does 'hello world' mean in progra...
    Expected: Fields: ['explanation']
    Actual: Missing: ['explanation']
    Error: Schema contract violated

--------------------------------------------------
Overall: ✗ 1 FAILED (11/12)
==================================================
```

## What to Test

| Component | What to Eval | Example Assertion |
| --------- | ------------ | ----------------- |
| Structured output | JSON validity + schema contract | `parse_json(output) is not None and matches schema` |
| Decisions | Correct routing | `decision in valid_choices` |
| Tool calls | Correct tool + args | `tool_call["tool"] == "calculator"` |
| Memory | Store/retrieve cycle | `agent.memory.get_all()` contains saved fact |

## Compare to Lesson 03

**Lesson 03 (Structured Output):**
- One-off validation during generation
- Retry if JSON fails
- No history

**Lesson 11 (Evals):**
- Systematic testing across many cases
- Track success rates over time
- Catch regressions before deployment

## Key Insights

### Evals Are Just Assertions

There's no magic here. You run the agent, check the output, report pass/fail. The power is in doing this systematically.

### Golden Datasets Are Your Contract

When someone asks "does the agent work?", you point to the golden dataset. 100% pass rate = it works. Anything less = specific failures to fix.

### Run Evals Before Every Change

The workflow:
1. Make prompt change
2. Run evals
3. If any fail, fix or revert
4. Commit

This is how you prevent quality degradation.

### Start Simple

You don't need 1000 test cases. Start with 5-10 golden cases per capability. Add more as you find edge cases in production.

## Common Issues

**"Evals are too slow"**
- Run a smaller subset for quick checks
- Run full suite before commits
- Consider caching model loads

**"Soft assertions are flaky"**
- Start with hard assertions only
- Add soft ones when you have enough data
- Consider using exact match before semantic match

**"I don't know what to test"**
- Start with the happy path
- Add cases that broke in production
- Cover edge cases (empty input, special chars, etc.)

## Exercises

1. Add a new golden case that currently fails, then fix the prompt
2. Break a prompt intentionally and verify evals catch the regression
3. Add an edge case (empty input, very long input, unicode)
4. Create golden dataset for planning (Lesson 08)

## What's Next?

In [Lesson 12](12_telemetry.md), we'll add **telemetry** - understanding what your agent is doing at runtime, not just in tests.

---

**Key Takeaway:** Evals = systematic testing. Golden datasets = your contract. Run them before every prompt change.
