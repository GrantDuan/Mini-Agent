"""Test cases for MemoryLogger (memory-specific JSON-lines log)."""

import json
import tempfile
from pathlib import Path

from mini_agent.memory_logger import MemoryLogger


def read_events(log_file: Path) -> list[dict]:
    with open(log_file, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_full_run_event_flow():
    """run_started -> turn_signal -> tool_call/result -> run_summary, all valid JSON lines."""
    with tempfile.TemporaryDirectory() as tmp:
        logger = MemoryLogger(log_dir=Path(tmp))
        logger.start_new_run(
            memory_tools=["create_entities", "read_graph"],
            policy_injected=True,
            system_prompt="You are Mini-Agent with memory policy",
            memory_judge=False,
        )
        assert logger.get_log_file_path() is not None
        assert logger.get_log_file_path().name.startswith("memory_run_")

        logger.log_turn_signal(
            turn_index=0,
            user_excerpt="记住我在做 Mini-Agent" + "x" * 200,  # truncated to 100
            memory_tools=["create_entities", "read_graph"],
            policy_injected=True,
            memory_tools_called=["read_graph"],
            tools_called=["read_graph", "bash"],
        )
        logger.begin_tool_call(1, "create_entities", {"entities": [{"name": "User"}]})
        logger.end_tool_call(success=True, content="Created 1 entity")
        logger.log_summary()

        events = read_events(logger.get_log_file_path())
        types = [e["type"] for e in events]
        assert types == ["run_started", "turn_signal", "memory_tool_call", "memory_tool_result", "run_summary"]

        # Every event carries a timestamp
        assert all("ts" in e for e in events)

        started = events[0]
        assert started["policy_injected"] is True
        assert started["memory_judge"] is False
        assert started["system_prompt_len"] == len("You are Mini-Agent with memory policy")
        assert len(started["system_prompt_hash"]) == 16

        signal = events[1]
        assert len(signal["user_excerpt"]) == 100
        assert signal["tools_called"] == ["read_graph", "bash"]
        assert signal["memory_tools_called"] == ["read_graph"]

        result = events[3]
        assert result["success"] is True
        assert result["content_summary"] == "Created 1 entity"
        assert result["latency_ms"] >= 0

        summary = events[4]
        assert summary["total_turns"] == 1
        assert summary["memory_tool_calls"] == 1
        assert summary["memory_tool_errors"] == 0
        assert summary["counts_by_tool"] == {"create_entities": 1}


def test_error_counting_and_dangling_call_finalize():
    """Failed calls are counted; a run ending mid-call is finalized with an error."""
    with tempfile.TemporaryDirectory() as tmp:
        logger = MemoryLogger(log_dir=Path(tmp))
        logger.start_new_run(
            memory_tools=["search_nodes"],
            policy_injected=False,
            system_prompt="p",
        )
        logger.begin_tool_call(0, "search_nodes", {"query": "评测"})
        logger.end_tool_call(success=False, error="MCP server unavailable")
        logger.begin_tool_call(1, "read_graph", {})
        logger.log_summary()  # dangling call finalized by summary

        events = read_events(logger.get_log_file_path())
        results = [e for e in events if e["type"] == "memory_tool_result"]
        assert len(results) == 2
        assert results[0]["success"] is False and results[0]["error"]
        assert results[1]["success"] is False  # finalized dangling call
        assert "run ended" in results[1]["error"]

        summary = events[-1]
        assert summary["memory_tool_calls"] == 2
        assert summary["memory_tool_errors"] == 2


def test_noop_before_start():
    """Logging before start_new_run writes nothing and raises no error."""
    with tempfile.TemporaryDirectory() as tmp:
        logger = MemoryLogger(log_dir=Path(tmp))
        logger.log_turn_signal(0, "u", [], False, [], [])
        logger.begin_tool_call(0, "read_graph", {})
        logger.end_tool_call(True, "c")
        logger.log_summary()
        assert logger.get_log_file_path() is None
