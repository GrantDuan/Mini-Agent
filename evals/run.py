"""
Run eval golden cases (Lesson 11) against the REAL Mini Agent.

Unlike the interactive CLI (prompt_toolkit, Esc listeners - not automatable),
this drives the same full Agent that the CLI assembles:

    config -> LLMClient -> tools (bash / files / calculator / notes / weather)
           -> system prompt -> Agent.run()

and asserts on the agent's observable behavior:
  - final reply text (structured output, decisions)
  - tool calls recorded in the transcript (tool accuracy)
  - cross-session memory via record_note / recall_notes (memory cycle)

Usage:
    python evals/run.py                     # Quick run (subset of each suite)
    python evals/run.py --full              # Full golden datasets
    python evals/run.py --suite tool        # Single suite (repeatable)
    python evals/run.py --list              # List available suites
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

# Allow running directly: python evals/run.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows console (GBK) can't print ✓/✗ - force UTF-8 output
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from mini_agent import LLMClient
from mini_agent.agent import Agent
from mini_agent.config import Config
from mini_agent.schema import LLMProvider
from mini_agent.tools.base import Tool
from mini_agent.tools.bash_tool import BashOutputTool, BashTool
from mini_agent.tools.calculator_tool import CalculatorTool
from mini_agent.tools.file_tools import EditTool, ReadTool, WriteTool
from mini_agent.tools.note_tool import RecallNoteTool, SessionNoteTool
from mini_agent.tools.weather_tool import WeatherTool

from evals.evals import EvalResult, EvalSuiteResult, print_eval_report
from evals.golden_datasets import (
    DECISION_GOLDEN,
    MEMORY_GOLDEN,
    STRUCTURED_OUTPUT_GOLDEN,
    TOOL_CALL_GOLDEN,
)

EVAL_WORKSPACE = Path(__file__).resolve().parent / "workspace"
MEMORY_FILE = EVAL_WORKSPACE / ".agent_memory.json"


# ============================================================
# Build the REAL agent (mirrors cli.run_agent's assembly)
# ============================================================

def build_tools(workspace: Path) -> list[Tool]:
    """Same tool set the interactive CLI loads for a workspace."""
    memory_file = str(workspace / ".agent_memory.json")
    return [
        BashTool(workspace_dir=str(workspace)),
        BashOutputTool(),
        ReadTool(workspace_dir=str(workspace)),
        WriteTool(workspace_dir=str(workspace)),
        EditTool(workspace_dir=str(workspace)),
        SessionNoteTool(memory_file=memory_file),
        RecallNoteTool(memory_file=memory_file),
        CalculatorTool(),
        WeatherTool(),
    ]


def build_agent(max_steps: int = 8) -> Agent:
    """Assemble a real Agent from the same config the CLI uses."""
    config_path = Config.get_default_config_path()
    if not config_path.exists():
        print("❌ Configuration file not found (mini_agent/config/config.yaml)")
        sys.exit(1)

    config = Config.from_yaml(config_path)

    provider = (
        LLMProvider.ANTHROPIC
        if config.llm.provider.lower() == "anthropic"
        else LLMProvider.OPENAI
    )
    llm_client = LLMClient(
        api_key=config.llm.api_key,
        provider=provider,
        api_base=config.llm.api_base,
        model=config.llm.model,
    )

    system_prompt_path = Config.find_config_file(config.agent.system_prompt_path)
    if system_prompt_path and system_prompt_path.exists():
        system_prompt = system_prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = "You are Mini-Agent, an intelligent assistant that can help users complete tasks."

    EVAL_WORKSPACE.mkdir(parents=True, exist_ok=True)

    return Agent(
        llm_client=llm_client,
        system_prompt=system_prompt,
        tools=build_tools(EVAL_WORKSPACE),
        max_steps=max_steps,
        workspace_dir=str(EVAL_WORKSPACE),
    )


# ============================================================
# Transcript helpers: what did the agent actually DO?
# ============================================================

def collect_tool_calls(agent: Agent) -> list[dict]:
    """All tool calls the agent made during its run, in order.

    [{'tool': name, 'arguments': {...}}, ...]
    """
    calls = []
    for msg in agent.messages:
        if msg.role == "assistant" and msg.tool_calls:
            for tc in msg.tool_calls:
                calls.append({"tool": tc.function.name, "arguments": tc.function.arguments})
    return calls


def extract_json(text: str) -> dict | None:
    """Extract the first JSON object from a model reply."""
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


async def run_task(task: str, max_steps: int = 8) -> tuple[str, Agent]:
    """Fresh agent per case - golden cases must not leak into each other."""
    agent = build_agent(max_steps=max_steps)
    agent.add_user_message(task)
    reply = await agent.run()
    return reply, agent


# ============================================================
# Eval suites (each returns an EvalSuiteResult from evals.py)
# ============================================================

async def eval_structured_output(cases: list[dict]) -> EvalSuiteResult:
    """Run the full agent and check its final reply is valid JSON matching the schema."""
    suite = EvalSuiteResult(name="Structured Output")
    for case in cases:
        task = (
            f"{case['input']}\n\n"
            "Respond with ONLY a JSON object matching this schema "
            "(no markdown, no explanation):\n"
            f"{case['schema']}"
        )
        reply, _ = await run_task(task, max_steps=3)
        result = extract_json(reply)

        if result is None:
            suite.add_result(EvalResult(
                passed=False, input=case["input"],
                expected="Valid JSON", actual=reply[:200],
                error="Failed to parse JSON",
            ))
            continue

        missing = [f for f in case.get("must_have_fields", []) if f not in result]
        if missing:
            suite.add_result(EvalResult(
                passed=False, input=case["input"],
                expected=f"Fields: {case.get('must_have_fields', [])}",
                actual=f"Missing: {missing}",
                error="Schema contract violated",
            ))
            continue

        suite.add_result(EvalResult(passed=True, input=case["input"], actual=result))
    return suite


async def eval_tool_calls(cases: list[dict]) -> EvalSuiteResult:
    """Run the full agent and check WHICH tools it called with WHAT arguments."""
    suite = EvalSuiteResult(name="Tool Calls")
    for case in cases:
        _, agent = await run_task(case["input"])
        calls = collect_tool_calls(agent)

        if not calls:
            suite.add_result(EvalResult(
                passed=False, input=case["input"],
                expected=case["expected_tool"], actual=None,
                error="Agent made no tool calls",
            ))
            continue

        # Does any call match the expected tool? (agent may retry/break down
        # the problem, so scan all calls, not just the first)
        matching = [c for c in calls if c["tool"] == case["expected_tool"]]
        if not matching:
            suite.add_result(EvalResult(
                passed=False, input=case["input"],
                expected=case["expected_tool"],
                actual=[c["tool"] for c in calls],
                error="Expected tool never called",
            ))
            continue

        # Check required arguments on one matching call
        expected_args = case.get("expected_args", {})
        ok_call = next(
            (c for c in matching
             if all(c["arguments"].get(k) == v for k, v in expected_args.items())),
            None,
        )
        if ok_call is None:
            suite.add_result(EvalResult(
                passed=False, input=case["input"],
                expected=expected_args,
                actual=[c["arguments"] for c in matching],
                error="Tool called but with wrong arguments",
            ))
            continue

        suite.add_result(EvalResult(
            passed=True, input=case["input"],
            expected=case["expected_tool"], actual=ok_call,
        ))
    return suite


async def eval_decisions(cases: list[dict]) -> EvalSuiteResult:
    """Run the full agent as a router and check it picks the expected action."""
    suite = EvalSuiteResult(name="Decisions")
    for case in cases:
        choices = case["choices"]
        choice_list = ", ".join(choices)
        task = (
            f"{case['input']}\n\n"
            f"This request must be routed to exactly one of: {choice_list}.\n"
            "Reply with ONLY the name of the best matching action, nothing else."
        )
        reply, _ = await run_task(task, max_steps=2)

        matched = next((c for c in choices if c in reply), None)
        if matched is None:
            suite.add_result(EvalResult(
                passed=False, input=case["input"],
                expected=case["expected"], actual=reply[:200],
                error="Reply matched no valid choice",
            ))
        elif matched != case["expected"]:
            suite.add_result(EvalResult(
                passed=False, input=case["input"],
                expected=case["expected"], actual=matched,
                error="Wrong routing decision",
            ))
        else:
            suite.add_result(EvalResult(
                passed=True, input=case["input"],
                expected=case["expected"], actual=matched,
            ))
    return suite


async def eval_memory_cycle(cases: list[dict]) -> EvalSuiteResult:
    """Store with one agent instance, recall with a FRESH instance.

    This tests real cross-session persistence (record_note -> file ->
    recall_notes), not just in-context memory.
    """
    suite = EvalSuiteResult(name="Memory Cycle")
    for case in cases:
        # Clean slate per case
        if MEMORY_FILE.exists():
            MEMORY_FILE.unlink()

        _, store_agent = await run_task(
            f"{case['store_input']}\n\n"
            "Record this information with the record_note tool before replying.",
        )
        recorded = any(c["tool"] == "record_note" for c in collect_tool_calls(store_agent))

        reply, query_agent = await run_task(
            f"{case['query_input']}\n\n"
            "If you need information about the user, use the recall_notes tool.",
        )

        if not recorded:
            suite.add_result(EvalResult(
                passed=False, input=f"{case['store_input']} → {case['query_input']}",
                expected="record_note called", actual=None,
                error="Agent never stored the fact",
            ))
            continue

        expected_sub = case.get("expected_in_response", "")
        if expected_sub.lower() in reply.lower():
            suite.add_result(EvalResult(
                passed=True,
                input=f"{case['store_input']} → {case['query_input']}",
                expected=expected_sub, actual=reply[:200],
            ))
        else:
            suite.add_result(EvalResult(
                passed=False,
                input=f"{case['store_input']} → {case['query_input']}",
                expected=expected_sub, actual=reply[:200],
                error="Expected content not in reply",
            ))
    # Clean up after the suite
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()
    return suite


# ============================================================
# Runner
# ============================================================

SUITES = {
    "structured": eval_structured_output,
    "tool": eval_tool_calls,
    "decision": eval_decisions,
    "memory": eval_memory_cycle,
}


async def run_evals(suite_names: list[str], full: bool) -> int:
    """Run requested suites against the real agent. Returns failed count."""
    limit = None if full else 2

    results = []
    for name in suite_names:
        cases = SUITE_CASES[name]
        subset = cases if limit is None else cases[:limit]
        print(f"\n▶ Suite '{name}': {len(subset)} case(s)...")
        results.append(await SUITES[name](subset))

    print_eval_report(results)

    failed = sum(suite.failed for suite in results)
    return failed


SUITE_CASES = {
    "structured": STRUCTURED_OUTPUT_GOLDEN,
    "tool": TOOL_CALL_GOLDEN,
    "decision": DECISION_GOLDEN,
    "memory": MEMORY_GOLDEN,
}


def main():
    parser = argparse.ArgumentParser(description="Run eval golden cases (real agent)")
    parser.add_argument(
        "--suite", action="append", choices=sorted(SUITES.keys()),
        help="Run only this suite (repeatable, default: all)",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Run the complete golden datasets (default: quick subset)",
    )
    parser.add_argument("--list", action="store_true", help="List available suites")
    args = parser.parse_args()

    if args.list:
        print("Available suites:")
        for name, cases in SUITE_CASES.items():
            print(f"  {name}: {len(cases)} cases")
        return

    suite_names = args.suite or list(SUITES.keys())
    failed = asyncio.run(run_evals(suite_names, full=args.full))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
