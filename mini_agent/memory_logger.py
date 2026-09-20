"""Memory usage logger

Records memory-tool-specific events to a dedicated JSON-lines log file so
memory behavior can be analyzed separately from the general agent log:

- run_started: which memory tools are available, whether the policy was injected
- memory_tool_call / memory_tool_result: per-call context, arguments, result, latency
- turn_signal: per-step visibility signals (was memory reachable? was it used?)
- run_summary: aggregate counts for the run

The "forgot to use memory" problem is not directly observable (absence leaves no
log), so turn_signal records the signals a human — or a future offline LLM judge
(see AgentConfig.memory_judge, reserved) — needs to audit afterwards.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any


class MemoryLogger:
    """Dedicated logger for memory tool usage, one JSON event per line.

    Writes to ~/.mini-agent/log/memory_run_YYYYMMDD_HHMMSS.log, mirroring the
    AgentLogger directory but in a compact machine-readable format.
    """

    def __init__(self, log_dir: Path | None = None):
        """Initialize logger.

        Args:
            log_dir: Optional override for the log directory (used by tests).
        """
        self.log_dir = log_dir or (Path.home() / ".mini-agent" / "log")
        self.log_file: Path | None = None
        self._current_call: dict[str, Any] | None = None

        # Aggregate counters for run_summary
        self._memory_tool_calls = 0
        self._memory_tool_errors = 0
        self._counts_by_tool: dict[str, int] = {}
        self._total_turns = 0

    def start_new_run(
        self,
        memory_tools: list[str],
        policy_injected: bool,
        system_prompt: str,
        memory_judge: bool = False,
    ):
        """Start a new run, create the log file and record run metadata.

        Args:
            memory_tools: Memory tool names available in this run.
            policy_injected: Whether the memory policy was injected into the system prompt.
            system_prompt: The full system prompt (hashed, not stored in plaintext).
            memory_judge: Reserved flag for the future offline LLM judge (no-op now).
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"memory_run_{timestamp}.log"

        self._memory_tool_calls = 0
        self._memory_tool_errors = 0
        self._counts_by_tool = {}
        self._total_turns = 0
        self._current_call = None

        self._write(
            {
                "type": "run_started",
                "memory_tools": memory_tools,
                "policy_injected": policy_injected,
                "memory_judge": memory_judge,
                "system_prompt_hash": hashlib.sha256(system_prompt.encode()).hexdigest()[:16],
                "system_prompt_len": len(system_prompt),
            }
        )

    def log_turn_signal(
        self,
        turn_index: int,
        user_excerpt: str,
        memory_tools: list[str],
        policy_injected: bool,
        memory_tools_called: list[str],
        tools_called: list[str],
    ):
        """Record per-step signals for later "should memory have been used?" audits.

        Args:
            turn_index: Zero-based step index of the agent loop.
            user_excerpt: Truncated excerpt of the last user message (<= 100 chars).
            memory_tools: Memory tools available this turn.
            policy_injected: Whether the memory policy is in the system prompt.
            memory_tools_called: Memory tool names invoked this turn.
            tools_called: All tool names invoked this turn.
        """
        self._total_turns = max(self._total_turns, turn_index + 1)
        self._write(
            {
                "type": "turn_signal",
                "turn_index": turn_index,
                "user_excerpt": user_excerpt[:100],
                "memory_tools_available": memory_tools,
                "policy_injected": policy_injected,
                "memory_tools_called": memory_tools_called,
                "tools_called": tools_called,
            }
        )

    def begin_tool_call(self, turn_index: int, tool_name: str, arguments: dict[str, Any]):
        """Record the start of a memory tool call (must be followed by end_tool_call).

        Args:
            turn_index: Zero-based step index.
            tool_name: Memory tool name.
            arguments: Tool arguments.
        """
        self._current_call = {
            "turn_index": turn_index,
            "tool_name": tool_name,
            "arguments": arguments,
            "_start": perf_counter(),
        }
        self._memory_tool_calls += 1
        self._counts_by_tool[tool_name] = self._counts_by_tool.get(tool_name, 0) + 1
        self._write(
            {
                "type": "memory_tool_call",
                "turn_index": turn_index,
                "tool_name": tool_name,
                "arguments": arguments,
            }
        )

    def end_tool_call(self, success: bool, content: str | None = None, error: str | None = None):
        """Record the result of the memory tool call opened by begin_tool_call.

        Args:
            success: Whether execution succeeded.
            content: Result content (truncated to 300 chars in the log).
            error: Error message on failure.
        """
        if self._current_call is None:
            return
        call = self._current_call
        self._current_call = None

        latency_ms = round((perf_counter() - call["_start"]) * 1000, 1)
        if not success:
            self._memory_tool_errors += 1

        self._write(
            {
                "type": "memory_tool_result",
                "turn_index": call["turn_index"],
                "tool_name": call["tool_name"],
                "success": success,
                "content_summary": (content or "")[:300],
                "error": error,
                "latency_ms": latency_ms,
            }
        )

    def log_summary(self):
        """Record aggregate counts for the run (call in a finally block)."""
        # Finalize a dangling call (e.g. cancelled mid-execution)
        if self._current_call is not None:
            self.end_tool_call(success=False, error="run ended before tool result was recorded")

        self._write(
            {
                "type": "run_summary",
                "total_turns": self._total_turns,
                "memory_tool_calls": self._memory_tool_calls,
                "memory_tool_errors": self._memory_tool_errors,
                "counts_by_tool": self._counts_by_tool,
            }
        )

    def _write(self, event: dict[str, Any]):
        """Append one JSON event per line."""
        if self.log_file is None:
            return
        event = {"ts": datetime.now().isoformat(timespec="milliseconds"), **event}
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def get_log_file_path(self) -> Path | None:
        """Get the current log file path (None before start_new_run)."""
        return self.log_file
