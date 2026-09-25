"""Test DispatchAgentTool（离线，用 FakeLLMClient，不打真 API）。"""

from pathlib import Path

from mini_agent.multi_agent.dispatch_tool import DispatchAgentTool
from mini_agent.multi_agent.plugin_loader import (
    AgentDefinition,
    SubagentDirectory,
    discover_plugins,
)
from mini_agent.schema import LLMResponse


class FakeLLMClient:
    """假 LLM：直接返回固定文本，记录每次收到的 messages 和 tools。"""

    def __init__(self) -> None:
        self.stream_callback = None
        self.stream_end_callback = None
        self.seen_messages: list[list] = []
        self.seen_tools: list[list] = []

    async def generate(self, messages=None, tools=None, **kwargs):
        self.seen_messages.append(list(messages or []))
        self.seen_tools.append(list(tools or []))
        return LLMResponse(content="FINAL REPORT", finish_reason="end_turn", tool_calls=None)


def make_directory(tmp_path: Path) -> SubagentDirectory:
    directory = SubagentDirectory()
    directory.definitions["expert"] = AgentDefinition(
        name="expert",
        description="An expert",
        tools=["Read"],
        system_prompt="You are an expert.",
        plugin_name="p",
        agent_path=tmp_path / "agents" / "expert.md",
    )
    return directory


async def test_dispatch_returns_final_report(tmp_path):
    directory = make_directory(tmp_path)
    tool = DispatchAgentTool(
        directory, FakeLLMClient(), base_tools=[], workspace_dir=str(tmp_path)
    )
    result = await tool.execute(agent="expert", task="Do the thing")
    assert result.success is True
    assert result.content == "FINAL REPORT"


async def test_dispatch_unknown_agent_lists_available(tmp_path):
    directory = make_directory(tmp_path)
    tool = DispatchAgentTool(
        directory, FakeLLMClient(), base_tools=[], workspace_dir=str(tmp_path)
    )
    result = await tool.execute(agent="nope", task="x")
    assert result.success is False
    assert "expert" in result.error


async def test_dispatch_empty_task_rejected(tmp_path):
    directory = make_directory(tmp_path)
    tool = DispatchAgentTool(
        directory, FakeLLMClient(), base_tools=[], workspace_dir=str(tmp_path)
    )
    result = await tool.execute(agent="expert", task="   ")
    assert result.success is False


async def test_dispatch_fresh_context_each_time(tmp_path):
    """每次委派都是全新上下文：发给 LLM 的消息只含本次 task。"""
    directory = make_directory(tmp_path)
    fake = FakeLLMClient()
    tool = DispatchAgentTool(directory, fake, base_tools=[], workspace_dir=str(tmp_path))
    await tool.execute(agent="expert", task="First task")
    await tool.execute(agent="expert", task="Second task")
    assert len(fake.seen_messages) == 2
    for call_messages in fake.seen_messages:
        # 每次都只有 system + 本次 task，无历史残留（fresh context）
        assert [m.role for m in call_messages] == ["system", "user"]


async def test_dispatch_includes_plugin_skill_tools(tmp_path):
    """subagent 的工具表里应包含其插件 skill 的 get_skill。"""
    plugin_dir = tmp_path / "p"
    (plugin_dir / "agents").mkdir(parents=True)
    (plugin_dir / "agents" / "expert.md").write_text(
        "---\nname: expert\ndescription: An expert\n---\n\nBody.\n", encoding="utf-8"
    )
    (plugin_dir / "skills" / "my-skill").mkdir(parents=True)
    (plugin_dir / "skills" / "my-skill" / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: A skill\n---\n\nDo it.\n", encoding="utf-8"
    )
    directory = discover_plugins(tmp_path)
    fake = FakeLLMClient()
    tool = DispatchAgentTool(directory, fake, base_tools=[], workspace_dir=str(tmp_path))
    result = await tool.execute(agent="expert", task="Go")
    assert result.success is True
    assert any(t.name == "get_skill" for t in fake.seen_tools[0])
