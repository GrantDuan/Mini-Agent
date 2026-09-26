"""Test DispatchAgentTool（离线，用 FakeLLMClient，不打真 API）。"""

from pathlib import Path

from mini_agent.multi_agent.dispatch_tool import DispatchAgentTool
from mini_agent.multi_agent.plugin_loader import (
    AgentDefinition,
    SubagentDirectory,
    discover_plugins,
)
from mini_agent.schema import LLMResponse

# ---- 新增：模块级 stub，供多个测试复用 ----
from mini_agent.tools.base import Tool, ToolResult


class NamedTool(Tool):
    """只有名字的工具 stub。"""

    def __init__(self, tool_name: str):
        self._name = tool_name

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return "stub"

    @property
    def parameters(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return ToolResult(success=True, content="")


def make_defn(tmp_path: Path, name: str = "a", tools: list | None = None) -> AgentDefinition:
    """构造测试用 AgentDefinition（tools=None 表示 frontmatter 没写 tools:）。"""
    return AgentDefinition(
        name=name,
        description="d",
        tools=tools if tools is not None else [],
        system_prompt="s",
        plugin_name="p",
        agent_path=tmp_path / "agents" / f"{name}.md",
    )


# ---- Task 1: resolve_tools ----
from mini_agent.multi_agent.dispatch_tool import MAX_SPAWN_DEPTH, resolve_tools


def test_resolve_tools_exact_and_wildcard(tmp_path):
    pool = [
        NamedTool("read_file"),
        NamedTool("write_file"),
        NamedTool("mcp__internal-gl__balances"),
        NamedTool("mcp__internal-gl__entries"),
    ]
    defn = make_defn(tmp_path, tools=["read_file", "mcp__internal-gl__*"])
    grants, resolved, unresolved = resolve_tools(defn, pool)
    assert grants is False
    assert [t.name for t in resolved] == [
        "read_file", "mcp__internal-gl__balances", "mcp__internal-gl__entries",
    ]
    assert unresolved == []


def test_resolve_tools_dispatch_flag_and_unresolved(tmp_path):
    pool = [NamedTool("bash")]
    defn = make_defn(tmp_path, tools=["dispatch_agent", "bash", "mcp__subledger__*"])
    grants, resolved, unresolved = resolve_tools(defn, pool)
    assert grants is True                      # dispatch_agent 是授予标记，不进 resolved
    assert [t.name for t in resolved] == ["bash"]
    assert unresolved == ["mcp__subledger__*"]  # 零命中的通配符原样进 unresolved


def test_resolve_tools_dedupes_overlap(tmp_path):
    pool = [NamedTool("mcp__x__a"), NamedTool("bash")]
    defn = make_defn(tmp_path, tools=["mcp__x__a", "mcp__x__*", "bash", "bash"])
    _, resolved, unresolved = resolve_tools(defn, pool)
    assert [t.name for t in resolved] == ["mcp__x__a", "bash"]  # 重叠条目去重
    assert unresolved == []


def test_resolve_tools_star_matches_everything(tmp_path):
    pool = [NamedTool("bash"), NamedTool("read_file")]
    defn = make_defn(tmp_path, tools=["*"])
    _, resolved, unresolved = resolve_tools(defn, pool)
    assert [t.name for t in resolved] == ["bash", "read_file"]
    assert unresolved == []


def test_resolve_tools_get_skill_not_in_pool(tmp_path):
    """skills 例外：get_skill 不在池里，写了只会进 unresolved 并被警告。"""
    defn = make_defn(tmp_path, tools=["get_skill"])
    _, resolved, unresolved = resolve_tools(defn, [NamedTool("bash")])
    assert resolved == []
    assert unresolved == ["get_skill"]


def test_max_spawn_depth_constant():
    assert MAX_SPAWN_DEPTH == 2


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


def test_build_subagent_base_tools_excludes_all_get_skill():
    """Review Focus #3：主 agent 的 get_skill 必须被过滤，否则与插件版在
    Agent.tools dict 里静默互相覆盖。基座工具不得含任何名为 get_skill 的工具
    （插件的 get_skill 由 skill_tools 单独提供）。"""
    from mini_agent.multi_agent.dispatch_tool import build_subagent_base_tools
    from mini_agent.tools.base import Tool, ToolResult

    class NamedTool(Tool):
        def __init__(self, tool_name: str):
            self._name = tool_name

        @property
        def name(self):
            return self._name

        @property
        def description(self):
            return "stub"

        @property
        def parameters(self):
            return {"type": "object", "properties": {}}

        async def execute(self, **kwargs):
            return ToolResult(success=True, content="")

    main_get_skill = NamedTool("get_skill")   # 主 agent 的 skill 工具
    bash = NamedTool("bash")
    read = NamedTool("read")
    tools = [main_get_skill, bash, read]
    base = build_subagent_base_tools(tools)
    assert base == [bash, read]               # 只去掉 get_skill，其余原序保留
    # 插件 skill 工具随后单独拼接，拼接后也不得与基座重名
    combined = base + [NamedTool("get_skill")]
    assert len({t.name for t in combined}) == len(combined)


# ---- Task 2: 构造时解析 + execute 拼装 ----


async def test_dispatch_default_tools_unchanged(tmp_path):
    """frontmatter 没写 tools: → 行为与 M1 完全一致：全部基座 + 本插件 get_skill。"""
    directory = SubagentDirectory()
    directory.definitions["expert"] = make_defn(tmp_path, name="expert", tools=None)
    fake = FakeLLMClient()
    tool = DispatchAgentTool(
        directory, fake,
        base_tools=[NamedTool("read_file"), NamedTool("bash")],
        workspace_dir=str(tmp_path),
    )
    await tool.execute(agent="expert", task="Go")
    # 此用例 skill_tools 为空（无插件 skills），get_skill 不存在
    names = {t.name for t in fake.seen_tools[0]}
    assert names == {"read_file", "bash"}


async def test_dispatch_honors_tools_field(tmp_path):
    """写了 tools: → 子 agent 只拿到解析结果 + 本插件 get_skill（bash 被滤掉）。"""
    directory = SubagentDirectory()
    directory.definitions["expert"] = make_defn(
        tmp_path, name="expert", tools=["read_file", "mcp__internal-gl__*"]
    )
    directory.skill_tools["expert"] = [NamedTool("get_skill")]
    fake = FakeLLMClient()
    tool = DispatchAgentTool(
        directory, fake,
        base_tools=[
            NamedTool("read_file"), NamedTool("bash"),
            NamedTool("mcp__internal-gl__balances"),
        ],
        workspace_dir=str(tmp_path),
    )
    await tool.execute(agent="expert", task="Go")
    names = {t.name for t in fake.seen_tools[0]}
    assert names == {"read_file", "mcp__internal-gl__balances", "get_skill"}


async def test_dispatch_unresolved_collected_and_empty_base(tmp_path):
    """全部解析失败 → 基座为空（get_skill 仍附带），unresolved 逐名收集供启动警告。"""
    directory = SubagentDirectory()
    directory.definitions["expert"] = make_defn(
        tmp_path, name="expert", tools=["write_file", "nope_tool"]
    )
    fake = FakeLLMClient()
    tool = DispatchAgentTool(
        directory, fake, base_tools=[NamedTool("bash")], workspace_dir=str(tmp_path)
    )
    assert tool.unresolved == {"expert": ["write_file", "nope_tool"]}
    await tool.execute(agent="expert", task="Go")
    assert [t.name for t in fake.seen_tools[0]] == []


async def test_resolve_directory_idempotent_for_child_instances(tmp_path):
    """子 dispatch 实例构造时跳过已缓存 agent：unresolved 不重复、缓存不被覆盖。"""
    directory = SubagentDirectory()
    directory.definitions["expert"] = make_defn(
        tmp_path, name="expert", tools=["write_file"]
    )
    first = DispatchAgentTool(
        directory, FakeLLMClient(), base_tools=[], workspace_dir=str(tmp_path)
    )
    assert first.unresolved == {"expert": ["write_file"]}
    second = DispatchAgentTool(
        directory, FakeLLMClient(), base_tools=[NamedTool("bash")],
        workspace_dir=str(tmp_path),
    )
    assert second.unresolved == {}                # 已缓存，不再解析
    assert directory.resolved_tools["expert"] == []  # 首次结果未被覆盖


# ---- Task 3: 串行链 ----
from mini_agent.schema import FunctionCall, LLMResponse, ToolCall


class ScriptedLLMClient(FakeLLMClient):
    """按脚本逐次返回响应（pop(0)），并沿用 seen_messages / seen_tools 记录。"""

    def __init__(self, responses: list[LLMResponse]) -> None:
        super().__init__()
        self.responses = list(responses)

    async def generate(self, messages=None, tools=None, **kwargs):
        self.seen_messages.append(list(messages or []))
        self.seen_tools.append(list(tools or []))
        return self.responses.pop(0)


def dispatch_call(agent: str, task: str) -> LLMResponse:
    """构造一次 dispatch_agent 工具调用响应。"""
    return LLMResponse(
        content="",
        finish_reason="tool_use",
        tool_calls=[ToolCall(
            id="call1",
            type="function",
            function=FunctionCall(name="dispatch_agent",
                                  arguments={"agent": agent, "task": task}),
        )],
    )


async def test_l1_gets_dispatch_when_granted(tmp_path):
    """tools: 含 dispatch_agent 且子层级 1 < 2 → L1 挂 dispatch 工具。"""
    directory = SubagentDirectory()
    directory.definitions["orchestrator"] = make_defn(
        tmp_path, name="orchestrator", tools=["dispatch_agent", "bash"]
    )
    fake = FakeLLMClient()
    tool = DispatchAgentTool(
        directory, fake, base_tools=[NamedTool("bash")], workspace_dir=str(tmp_path)
    )
    await tool.execute(agent="orchestrator", task="Go")
    assert any(t.name == "dispatch_agent" for t in fake.seen_tools[0])


async def test_default_definition_cannot_spawn(tmp_path):
    """Review Focus #1：tools: 缺省 ≠ 自动可 spawn（显式授予才有效）。"""
    directory = SubagentDirectory()
    directory.definitions["plain"] = make_defn(tmp_path, name="plain", tools=None)
    fake = FakeLLMClient()
    tool = DispatchAgentTool(
        directory, fake, base_tools=[NamedTool("bash")], workspace_dir=str(tmp_path)
    )
    await tool.execute(agent="plain", task="Go")
    assert not any(t.name == "dispatch_agent" for t in fake.seen_tools[0])


async def test_serial_chain_three_levels(tmp_path):
    """集成：主(0) → orchestrator(1) → worker(2)。worker 即使 tools: 授予也无 dispatch；
    dispatch 阻塞到 worker 跑完，报告返回后 orchestrator 才产出最终结果（串行）。"""
    directory = SubagentDirectory()
    directory.definitions["orchestrator"] = make_defn(
        tmp_path, name="orchestrator", tools=["dispatch_agent"]
    )
    directory.definitions["worker"] = make_defn(
        tmp_path, name="worker", tools=["dispatch_agent", "bash"]  # 故意授予，验证深度上限仍然拦截
    )
    fake = ScriptedLLMClient([
        dispatch_call("worker", "Sub task"),                            # orch 第 1 步
        LLMResponse(content="WORKER FINAL", finish_reason="end_turn"),  # worker（嵌套发生）
        LLMResponse(content="ORCH FINAL", finish_reason="end_turn"),    # orch 第 2 步
    ])
    tool = DispatchAgentTool(
        directory, fake, base_tools=[NamedTool("bash")], workspace_dir=str(tmp_path)
    )
    result = await tool.execute(agent="orchestrator", task="Top task")
    assert result.success is True
    assert result.content == "ORCH FINAL"
    # 第 1 次调用 = orchestrator：工具表含 dispatch_agent
    assert any(t.name == "dispatch_agent" for t in fake.seen_tools[0])
    # 第 2 次调用 = worker：工具表无 dispatch_agent（深度上限），有基座工具
    assert not any(t.name == "dispatch_agent" for t in fake.seen_tools[1])
    assert any(t.name == "bash" for t in fake.seen_tools[1])
    # worker 收到的是纯派发任务（system + user），串行证据：worker 先于 orch 第 2 步
    assert [m.role for m in fake.seen_messages[1]] == ["system", "user"]
    assert "Sub task" in fake.seen_messages[1][1].content


def test_enum_excludes_owner_name(tmp_path):
    directory = SubagentDirectory()
    directory.definitions["expert"] = make_defn(tmp_path, name="expert")
    directory.definitions["expert-clone"] = make_defn(tmp_path, name="expert-clone")
    tool = DispatchAgentTool(
        directory, FakeLLMClient(), base_tools=[],
        workspace_dir=str(tmp_path), owner_name="expert",
    )
    enum = tool.parameters["properties"]["agent"]["enum"]
    assert "expert" not in enum
    assert "expert-clone" in enum


def test_main_instance_enum_keeps_all(tmp_path):
    directory = SubagentDirectory()
    directory.definitions["expert"] = make_defn(tmp_path, name="expert")
    tool = DispatchAgentTool(
        directory, FakeLLMClient(), base_tools=[], workspace_dir=str(tmp_path)
    )
    assert tool.parameters["properties"]["agent"]["enum"] == ["expert"]


# ---- Final review fix pass: I-1 spawn 授予缓存 ----


def test_spawn_grants_cached_at_construction(tmp_path):
    """构造时解析出的 spawn 授予写入 directory.spawn_grants（解析结果是唯一事实源）。"""
    directory = SubagentDirectory()
    directory.definitions["granted"] = make_defn(
        tmp_path, name="granted", tools=["dispatch_agent", "bash"]
    )
    directory.definitions["plain"] = make_defn(tmp_path, name="plain", tools=None)
    directory.definitions["restricted"] = make_defn(
        tmp_path, name="restricted", tools=["read_file"]
    )
    DispatchAgentTool(
        directory, FakeLLMClient(),
        base_tools=[NamedTool("bash"), NamedTool("read_file")],
        workspace_dir=str(tmp_path),
    )
    assert directory.spawn_grants == {"granted": True, "plain": False, "restricted": False}


async def test_spawn_gate_uses_construction_time_grant(tmp_path):
    """门控只认构造时缓存：构造后突变 frontmatter 不改变 spawn 行为（I-1）。"""
    directory = SubagentDirectory()
    directory.definitions["orchestrator"] = make_defn(
        tmp_path, name="orchestrator", tools=["dispatch_agent", "bash"]
    )
    fake = FakeLLMClient()
    tool = DispatchAgentTool(
        directory, fake, base_tools=[NamedTool("bash")], workspace_dir=str(tmp_path)
    )
    directory.definitions["orchestrator"].tools = ["bash"]  # 构造后收回授予
    await tool.execute(agent="orchestrator", task="Go")
    assert any(t.name == "dispatch_agent" for t in fake.seen_tools[0])  # 缓存仍授予


# ---- Final review fix pass: I-2 unresolved 分类 ----


def test_unresolved_separates_exact_typos_from_zero_hit_wildcards(tmp_path):
    """精确名未命中 → unresolved；零命中通配 → unresolved_wildcards（分类警告）。"""
    directory = SubagentDirectory()
    directory.definitions["expert"] = make_defn(
        tmp_path, name="expert", tools=["write_file", "nope_tool", "mcp__x__*"]
    )
    tool = DispatchAgentTool(
        directory, FakeLLMClient(), base_tools=[NamedTool("bash")],
        workspace_dir=str(tmp_path),
    )
    assert tool.unresolved == {"expert": ["write_file", "nope_tool"]}
    assert tool.unresolved_wildcards == {"expert": ["mcp__x__*"]}


def test_format_unresolved_warnings_two_categories():
    """两类警告逐 agent 排序输出：精确名在前，零命中通配带原因提示。"""
    from mini_agent.multi_agent.dispatch_tool import format_unresolved_warnings

    lines = format_unresolved_warnings(
        {"b": ["typo_tool"], "a": ["read_fiel"]},
        {"c": ["mcp__subledger__*"]},
    )
    assert lines == [
        "⚠️  a: 未解析工具（已忽略）: read_fiel",
        "⚠️  b: 未解析工具（已忽略）: typo_tool",
        "⚠️  c: 零命中通配模式（MCP 未安装或拼写有误，已忽略）: mcp__subledger__*",
    ]
