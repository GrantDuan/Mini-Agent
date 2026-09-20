"""Test cases for memory policy injection and memory tool detection."""

import pytest

from mini_agent.memory import (
    MEMORY_POLICY_HEADING,
    MEMORY_POLICY_TEXT,
    MEMORY_TOOL_NAMES,
    find_memory_tools,
)


class FakeTool:
    """Minimal tool stub with just a name."""

    def __init__(self, name: str):
        self.name = name


def inject_policy(system_prompt: str, tools: list[FakeTool]) -> str:
    """Replicate the cli.py step-6.5 injection logic for testing."""
    memory_tools = find_memory_tools(t.name for t in tools)
    if memory_tools:
        if "{MEMORY_POLICY}" in system_prompt:
            return system_prompt.replace("{MEMORY_POLICY}", MEMORY_POLICY_TEXT)
        return system_prompt + "\n\n" + MEMORY_POLICY_TEXT
    return system_prompt.replace("{MEMORY_POLICY}", "")


def test_find_memory_tools():
    """Only the memory server tools are matched, by raw name."""
    tools = ["create_entities", "read_graph", "search", "bash", "search_nodes"]
    assert find_memory_tools(tools) == ["create_entities", "read_graph", "search_nodes"]
    assert find_memory_tools([]) == []
    # All 9 known tools are recognized
    assert find_memory_tools(MEMORY_TOOL_NAMES) == sorted(MEMORY_TOOL_NAMES)


def test_policy_injected_with_placeholder():
    """Placeholder is replaced when memory tools are available."""
    prompt = "Intro\n\n{MEMORY_POLICY}\n\nGuidelines"
    result = inject_policy(prompt, [FakeTool("create_entities"), FakeTool("bash")])
    assert MEMORY_POLICY_HEADING in result
    assert "{MEMORY_POLICY}" not in result
    assert "Guidelines" in result


def test_policy_appended_without_placeholder():
    """Fallback: policy is appended when the custom prompt lacks the placeholder."""
    prompt = "Custom prompt without placeholder"
    result = inject_policy(prompt, [FakeTool("read_graph")])
    assert result.startswith("Custom prompt without placeholder")
    assert MEMORY_POLICY_HEADING in result


def test_placeholder_removed_without_memory_tools():
    """Without memory tools the placeholder is cleaned out and no policy injected."""
    prompt = "Intro\n\n{MEMORY_POLICY}\n\nGuidelines"
    result = inject_policy(prompt, [FakeTool("bash"), FakeTool("search")])
    assert MEMORY_POLICY_HEADING not in result
    assert "{MEMORY_POLICY}" not in result


def test_turn_signal_intersection_pattern():
    """Regression: agent.py intersects tool sets with find_memory_tools' result.

    find_memory_tools returns a LIST — the agent must wrap it in set() before
    using the & operator (set & list raises TypeError; this exact bug shipped
    once and crashed the agent loop after the first tool step).
    """
    names = find_memory_tools(["create_entities", "bash"])
    assert isinstance(names, list)
    # The exact expression agent.py uses in _log_memory_turn_signal
    result = sorted({"read_graph", "create_entities"} & set(names))
    assert result == ["create_entities"]
