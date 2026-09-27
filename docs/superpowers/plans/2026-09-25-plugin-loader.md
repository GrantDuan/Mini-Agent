# 插件加载器（运行层 M1）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mini-Agent 启动时扫描 `mini_agent/plugins/` 下的 Claude Code 格式插件，把每个插件的 `agents/*.md` 变成可委派的 subagent，主 agent 通过 `dispatch_agent` 工具把任务委派出去并拿回最终报告。

**Architecture:** 两个新模块 + 一处接线。`mini_agent/multi_agent/plugin_loader.py` 是纯解析层（md/清单 → `AgentDefinition` + 按插件隔离的 skill 工具）；`mini_agent/multi_agent/dispatch_tool.py` 是 `Tool` 子类，每次委派用 `AgentDefinition` 构造**全新** `Agent`（全新上下文，与 Claude Code subagent 语义一致）跑完返回最终文本；`cli.py`/`config.py` 负责启动加载、挂工具、往主 agent system prompt 追加可用 subagent 清单。核心循环（Agent/SkillLoader/AgentRegistry/DebateOrchestrator）零改动。

**Tech Stack:** Python 3.11+、pydantic（config）、PyYAML（frontmatter）、pytest（`asyncio_mode = "auto"`，异步测试**不需要** `@pytest.mark.asyncio` 装饰器）。

**Spec:** 无独立 spec 文件 — 设计于 2026-09-25 会话中确认（"加载器 + dispatch_agent 委派工具"方案，M1 运行层先行）。关键决策记录在本 header 与各任务中。

## Global Constraints

- Windows 环境：所有文件 IO 必须 `encoding="utf-8"`；读插件 md 用 `utf-8-sig`（防 BOM）并在正则前把 `\r\n` 归一为 `\n`（CRLF 会破坏 frontmatter 正则）。
- 测试命令一律在仓库根目录运行：`python -m pytest tests/<file> -v`。
- 不修改 `Agent` / `SkillLoader` / `AgentRegistry` / `DebateOrchestrator` 的现有行为与签名。
- `mini_agent/plugins/` 下已有 10 个真实插件，是**数据**不是待创建物；加载器只读，不修改它们。
- 每次委派构造全新 `Agent`；**不**注册进 `AgentRegistry`（辩论模式继续用实例注册，互不干扰）。
- 提交信息末尾加：`Co-Authored-By: Claude Code <noreply@anthropic.com>`。

## Review Focus

按出现概率排序的未覆盖失败模式（每条已把测试钉进对应任务）：

1. **CRLF/BOM frontmatter 失败**（Windows 拷贝的 md 文件）→ 期望：照样解析成功。测试：Task 1 `test_parse_agent_md_crlf_and_bom`。
2. **跨插件同名 agent 静默覆盖** → 期望：先加载的获胜 + 启动告警。测试：Task 2 `test_discover_plugins_duplicate_agent_first_wins`。
3. **主 agent 的 `get_skill` 与插件 skill 工具重名**：`Agent.tools` 是按名字建 dict，两个 `get_skill` 会静默互相覆盖 → 期望：subagent 只拿插件版 get_skill（接线时过滤，Task 4 代码内写明），插件 skill 工具真实挂上（测试：Task 3 `test_dispatch_includes_skill_tools`）。过滤本身无自动化测试，列入 Task 5 人工验证。
4. **插件 frontmatter 引用不存在的工具**（`mcp__factset__*` 等）→ 期望：启动时警告一次并忽略，不阻塞加载。人工验证：Task 5（代码在 Task 4）。
5. **Esc 取消不传播到 subagent** → 已知限制（M1 不修）：subagent 用 `cancel_event=None` 运行，主 agent 在 dispatch 返回后才检查取消。已写进 `DispatchAgentTool` docstring，不测试。
6. **空 skills/ 目录或损坏 SKILL.md** → 复用 `create_skill_tools` 现有降级行为（get_skill 空转、报错列出可用列表），不新增测试。

---

### Task 1: `parse_agent_md` — 解析单个 agent 定义文件

**Files:**
- Create: `mini_agent/multi_agent/plugin_loader.py`
- Test: `tests/test_plugin_loader.py`

**Interfaces:**
- Consumes: `yaml.safe_load`（PyYAML，skill_loader.py 已用）。
- Produces: `AgentDefinition` dataclass（字段 `name: str`、`description: str`、`tools: list[str]`、`system_prompt: str`、`plugin_name: str`、`agent_path: Path`）和 `parse_agent_md(path: Path, plugin_name: str) -> AgentDefinition | None`（无 frontmatter / YAML 坏 / frontmatter 非字典 → None）。Task 2、3 依赖这两个名字。

- [ ] **Step 1: Write the failing test**

创建 `tests/test_plugin_loader.py`：

```python
"""Test plugin loader (Claude Code format agents/skills)."""

from pathlib import Path

from mini_agent.multi_agent.plugin_loader import AgentDefinition, parse_agent_md


def make_agent_md(
    plugin_dir: Path,
    name: str = "test-agent",
    description: str = "A test agent",
    tools: str = "Read, Write, mcp__factset__*",
    body: str = "You are a test agent.",
) -> Path:
    """在 plugin_dir/agents/ 下写一个标准 agent md，返回其路径。"""
    agents_dir = plugin_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    md = agents_dir / f"{name}.md"
    md.write_text(
        f"---\nname: {name}\ndescription: {description}\ntools: {tools}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return md


def test_parse_agent_md_valid(tmp_path):
    md = make_agent_md(tmp_path)
    defn = parse_agent_md(md, plugin_name="my-plugin")
    assert defn is not None
    assert defn.name == "test-agent"
    assert defn.description == "A test agent"
    assert defn.tools == ["Read", "Write", "mcp__factset__*"]
    assert defn.system_prompt == "You are a test agent."
    assert defn.plugin_name == "my-plugin"


def test_parse_agent_md_crlf_and_bom(tmp_path):
    """Windows 现实：拷贝来的文件可能带 BOM 和 CRLF，必须照样解析。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    md = agents_dir / "crlf.md"
    md.write_bytes(
        b"\xef\xbb\xbf---\r\nname: crlf-agent\r\ndescription: d\r\n---\r\n\r\nBody line.\r\n"
    )
    defn = parse_agent_md(md, plugin_name="p")
    assert defn is not None
    assert defn.name == "crlf-agent"
    assert defn.system_prompt == "Body line."


def test_parse_agent_md_no_frontmatter_returns_none(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    md = agents_dir / "plain.md"
    md.write_text("Just some text, no frontmatter.\n", encoding="utf-8")
    assert parse_agent_md(md, plugin_name="p") is None


def test_parse_agent_md_missing_name_falls_back_to_stem(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    md = agents_dir / "fallback-name.md"
    md.write_text("---\ndescription: no name here\n---\n\nBody.\n", encoding="utf-8")
    defn = parse_agent_md(md, plugin_name="p")
    assert defn is not None
    assert defn.name == "fallback-name"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_plugin_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mini_agent.multi_agent.plugin_loader'`

- [ ] **Step 3: Write minimal implementation**

创建 `mini_agent/multi_agent/plugin_loader.py`：

```python
"""插件加载器 - 从 mini_agent/plugins/ 读取 Claude Code 格式插件。

每个插件目录结构（与 Claude Code 插件一致）:

    <plugins_dir>/<plugin-name>/
    ├── .claude-plugin/plugin.json   # 可选，提供插件名
    ├── agents/*.md                  # subagent 定义（frontmatter + 正文即 system prompt）
    └── skills/<skill>/SKILL.md      # 该插件专属技能

加载结果是一个 SubagentDirectory：agent 名 -> AgentDefinition，
以及每个 agent 专属的 skill 工具（按插件隔离，避免跨插件重名）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# 与 tools/skill_loader.py 相同的 frontmatter 解析约定
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


@dataclass
class AgentDefinition:
    """一个 subagent 的静态定义（agents/*.md 的解析结果）。"""

    name: str
    description: str
    tools: list[str]        # frontmatter tools 原样条目，如 ["Read", "mcp__factset__*"]
    system_prompt: str      # frontmatter 之后的正文
    plugin_name: str
    agent_path: Path


def _read_text(path: Path) -> str:
    """读文本并归一化：utf-8-sig 去 BOM、CRLF -> LF（否则 frontmatter 正则失配）。"""
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def _parse_tools_field(raw: object) -> list[str]:
    """frontmatter tools 字段 -> 列表。支持 YAML 列表或逗号分隔字符串。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def parse_agent_md(path: Path, plugin_name: str) -> AgentDefinition | None:
    """解析单个 agents/*.md。无 frontmatter / YAML 坏 / 非字典时返回 None。"""
    content = _read_text(path)
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None
    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(frontmatter, dict):
        return None
    name = str(frontmatter.get("name") or "").strip() or path.stem
    description = str(frontmatter.get("description") or "").strip()
    return AgentDefinition(
        name=name,
        description=description,
        tools=_parse_tools_field(frontmatter.get("tools")),
        system_prompt=match.group(2).strip(),
        plugin_name=plugin_name,
        agent_path=path,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_plugin_loader.py -v`
Expected: PASS（4 个测试全绿）

- [ ] **Step 5: Commit**

```bash
git add mini_agent/multi_agent/plugin_loader.py tests/test_plugin_loader.py
git commit -m "feat: parse Claude Code format agent definition files

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: `discover_plugins` + `SubagentDirectory` — 扫描插件目录

**Files:**
- Modify: `mini_agent/multi_agent/plugin_loader.py`（追加）
- Test: `tests/test_plugin_loader.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `parse_agent_md` / `AgentDefinition`；现有 `create_skill_tools(skills_dir: str) -> tuple[List[Tool], Optional[SkillLoader]]`（from `mini_agent.tools.skill_tool`）。
- Produces:
  - `SubagentDirectory` dataclass：字段 `definitions: dict[str, AgentDefinition]`、`skill_tools: dict[str, list]`（agent 名 -> 该 agent 专属 skill 工具）、`warnings: list[str]`；方法 `names() -> list[str]`、`describe() -> list[tuple[str, str]]`、`prompt_section() -> str`。
  - `discover_plugins(plugins_dir: Path) -> SubagentDirectory`。
  Task 3 依赖 `SubagentDirectory` 的字段与方法，Task 4 依赖 `discover_plugins` 与 `prompt_section()`。

- [ ] **Step 1: Write the failing test**

在 `tests/test_plugin_loader.py` 追加（import 行改为同时导入 `discover_plugins`）：

```python
from mini_agent.multi_agent.plugin_loader import discover_plugins


def make_skill(plugin_dir: Path, skill_name: str, description: str) -> None:
    """在 plugin_dir/skills/<skill_name>/ 下写一个标准 SKILL.md。"""
    skill_dir = plugin_dir / "skills" / skill_name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: {description}\n---\n\nDo the thing.\n",
        encoding="utf-8",
    )


def test_discover_plugins_full(tmp_path):
    p1 = tmp_path / "earnings-reviewer"
    (p1 / ".claude-plugin").mkdir(parents=True)
    (p1 / ".claude-plugin" / "plugin.json").write_text(
        '{"name": "earnings-reviewer"}', encoding="utf-8"
    )
    make_agent_md(p1, name="earnings-reviewer", description="Reviews earnings")
    make_skill(p1, "earnings-analysis", "Analyze an earnings call")

    p2 = tmp_path / "market-researcher"
    p2.mkdir()
    make_agent_md(p2, name="market-researcher", description="Researches markets")
    make_skill(p2, "comps-analysis", "Build comps")

    directory = discover_plugins(tmp_path)
    assert set(directory.names()) == {"earnings-reviewer", "market-researcher"}
    assert directory.describe()[0][1] in {"Reviews earnings", "Researches markets"}
    # 插件 skill 工具真实挂上，且 loader 能取到该插件的 skill
    skill_tool = directory.skill_tools["earnings-reviewer"][0]
    assert skill_tool.name == "get_skill"
    assert skill_tool.skill_loader.get_skill("earnings-analysis") is not None


def test_discover_plugins_skill_isolation(tmp_path):
    """两个插件都有同名 skill 时，各自 agent 只能看到自己插件的版本。"""
    pa = tmp_path / "plugin-a"
    pa.mkdir()
    make_agent_md(pa, name="agent-a")
    make_skill(pa, "xlsx-author", "Plugin A version")

    pb = tmp_path / "plugin-b"
    pb.mkdir()
    make_agent_md(pb, name="agent-b")
    make_skill(pb, "xlsx-author", "Plugin B version")

    directory = discover_plugins(tmp_path)
    tool_a = directory.skill_tools["agent-a"][0]
    tool_b = directory.skill_tools["agent-b"][0]
    assert tool_a.skill_loader.get_skill("xlsx-author").description == "Plugin A version"
    assert tool_b.skill_loader.get_skill("xlsx-author").description == "Plugin B version"


def test_discover_plugins_duplicate_agent_first_wins(tmp_path):
    pa = tmp_path / "plugin-a"
    pa.mkdir()
    make_agent_md(pa, name="dup", description="from a")
    pb = tmp_path / "plugin-b"
    pb.mkdir()
    make_agent_md(pb, name="dup", description="from b")

    directory = discover_plugins(tmp_path)
    assert directory.definitions["dup"].description == "from a"
    assert any("dup" in w for w in directory.warnings)


def test_discover_plugins_missing_dir(tmp_path):
    directory = discover_plugins(tmp_path / "nope")
    assert directory.definitions == {}
    assert directory.warnings


def test_discover_plugins_skips_non_plugin_dirs(tmp_path):
    (tmp_path / "random-folder").mkdir()
    (tmp_path / "random-folder" / "notes.txt").write_text("hi", encoding="utf-8")
    directory = discover_plugins(tmp_path)
    assert directory.definitions == {}
    assert directory.warnings == []


def test_prompt_section_lists_agents(tmp_path):
    pa = tmp_path / "plugin-a"
    pa.mkdir()
    make_agent_md(pa, name="agent-a", description="Does A things")
    directory = discover_plugins(tmp_path)
    section = directory.prompt_section()
    assert "agent-a" in section
    assert "Does A things" in section
    assert "dispatch_agent" in section
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_plugin_loader.py -v`
Expected: FAIL — `ImportError: cannot import name 'discover_plugins'`

- [ ] **Step 3: Write minimal implementation**

在 `mini_agent/multi_agent/plugin_loader.py` 追加（文件顶部 import 区补充 `from mini_agent.tools.skill_tool import create_skill_tools`）：

```python
@dataclass
class SubagentDirectory:
    """全部已加载 subagent 的目录，供 DispatchAgentTool 与主 agent prompt 使用。"""

    definitions: dict[str, AgentDefinition] = field(default_factory=dict)
    skill_tools: dict[str, list] = field(default_factory=dict)  # agent 名 -> 专属 skill 工具
    warnings: list[str] = field(default_factory=list)

    def names(self) -> list[str]:
        return list(self.definitions.keys())

    def describe(self) -> list[tuple[str, str]]:
        """返回 (name, description) 列表，供 prompt 与错误信息使用。"""
        return [(d.name, d.description) for d in self.definitions.values()]

    def prompt_section(self) -> str:
        """生成追加给主 agent system prompt 的可用 subagent 清单段落。"""
        lines = [
            "## Available Subagents",
            "",
            "You can delegate tasks to these expert subagents with the dispatch_agent tool.",
            "Each runs in a fresh context with its own system prompt and skills, "
            "and returns its final report to you.",
            "When delegating, write a complete, self-contained task description — "
            "the subagent cannot see this conversation.",
            "",
        ]
        for name, desc in self.describe():
            lines.append(f"- **{name}**: {desc}")
        return "\n".join(lines)


def _plugin_name(plugin_dir: Path, warnings: list[str]) -> str:
    """插件名：优先 .claude-plugin/plugin.json 的 name，否则目录名。"""
    manifest = plugin_dir / ".claude-plugin" / "plugin.json"
    if manifest.exists():
        try:
            data = json.loads(_read_text(manifest))
            name = str(data.get("name") or "").strip()
            if name:
                return name
        except (json.JSONDecodeError, OSError):
            warnings.append(f"⚠️  {manifest} 解析失败，使用目录名作为插件名")
    return plugin_dir.name


def discover_plugins(plugins_dir: Path) -> SubagentDirectory:
    """扫描插件目录，返回 SubagentDirectory。

    - 每个 <plugins_dir>/<name>/ 视为一个插件（不含 agents/ 且不含 skills/ 的目录跳过）
    - agents/*.md -> AgentDefinition；同名 agent 先到先得并告警
    - skills/ 目录 -> create_skill_tools 加载，只挂给本插件的 agent
    """
    directory = SubagentDirectory()
    plugins_dir = Path(plugins_dir)
    if not plugins_dir.exists():
        directory.warnings.append(f"⚠️  插件目录不存在: {plugins_dir}")
        return directory

    for plugin_dir in sorted(p for p in plugins_dir.iterdir() if p.is_dir()):
        if not (plugin_dir / "agents").exists() and not (plugin_dir / "skills").exists():
            continue  # 不是插件结构的目录，跳过
        plugin_name = _plugin_name(plugin_dir, directory.warnings)

        # 1) agents/*.md -> AgentDefinition
        agents_dir = plugin_dir / "agents"
        if agents_dir.exists():
            for md in sorted(agents_dir.glob("*.md")):
                defn = parse_agent_md(md, plugin_name)
                if defn is None:
                    directory.warnings.append(f"⚠️  跳过 {md}: 缺少 YAML frontmatter")
                    continue
                if defn.name in directory.definitions:
                    directory.warnings.append(
                        f"⚠️  agent '{defn.name}' 重复定义（{md}），保留先加载的版本"
                    )
                    continue
                directory.definitions[defn.name] = defn

        # 2) skills/ -> 本插件专属 skill 工具
        skills_dir = plugin_dir / "skills"
        if skills_dir.exists():
            tools, _loader = create_skill_tools(str(skills_dir))
            for defn in directory.definitions.values():
                if defn.plugin_name == plugin_name:
                    directory.skill_tools[defn.name] = tools

    return directory
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_plugin_loader.py -v`
Expected: PASS（11 个测试全绿；`create_skill_tools` 会打印 `✅ Discovered N Claude Skills`，属现有行为）

- [ ] **Step 5: Commit**

```bash
git add mini_agent/multi_agent/plugin_loader.py tests/test_plugin_loader.py
git commit -m "feat: discover plugins and build per-plugin skill tool sets

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: `DispatchAgentTool` — 委派工具

**Files:**
- Create: `mini_agent/multi_agent/dispatch_tool.py`
- Test: `tests/test_dispatch_tool.py`

**Interfaces:**
- Consumes: Task 2 的 `SubagentDirectory`（字段 `definitions` / `skill_tools`，方法 `names()`）；`Agent(llm_client, system_prompt, tools, max_steps, workspace_dir)`、`agent.add_user_message(task)`、`await agent.run() -> str`；`Tool` / `ToolResult` 基类。
- Produces: `DispatchAgentTool(directory, llm_client, base_tools, workspace_dir, max_steps)`，工具名 `dispatch_agent`，参数 `{agent: string(enum), task: string}`，`execute(agent: str, task: str) -> ToolResult`。Task 4 接线只构造它，不改它。
- 导入安全：`multi_agent/dispatch_tool.py` 顶部 `from mini_agent.agent import Agent` 与 `registry.py` 同款，无循环导入（agent.py 只依赖 `tools.base`，不反向依赖 multi_agent）。

- [ ] **Step 1: Write the failing test**

创建 `tests/test_dispatch_tool.py`：

```python
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
        assert len(call_messages) == 1  # 只有本次 task，无历史残留


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dispatch_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mini_agent.multi_agent.dispatch_tool'`

- [ ] **Step 3: Write minimal implementation**

创建 `mini_agent/multi_agent/dispatch_tool.py`：

```python
"""DispatchAgentTool - 主 agent 把任务委派给插件 subagent。

每次委派都用 AgentDefinition 构造一个全新的 Agent（全新上下文，与
Claude Code subagent 语义一致），跑完把最终报告作为工具结果返回。
不注册进 AgentRegistry，辩论模式（DebateOrchestrator）不受影响。

已知限制（M1）：subagent 运行期间不响应 Esc 取消（cancel_event=None），
主 agent 在 dispatch 返回后才检查取消。
"""

from __future__ import annotations

from typing import Any

from mini_agent.agent import Agent
from mini_agent.multi_agent.plugin_loader import SubagentDirectory
from mini_agent.tools.base import Tool, ToolResult


class DispatchAgentTool(Tool):
    """把任务委派给已加载插件的某个 subagent。"""

    def __init__(
        self,
        directory: SubagentDirectory,
        llm_client: Any,
        base_tools: list,
        workspace_dir: str = "./workspace",
        max_steps: int = 30,
    ) -> None:
        self.directory = directory
        self.llm_client = llm_client
        self.base_tools = list(base_tools)
        self.workspace_dir = workspace_dir
        self.max_steps = max_steps

    @property
    def name(self) -> str:
        return "dispatch_agent"

    @property
    def description(self) -> str:
        return (
            "Delegate a task to an expert subagent. The subagent runs in a fresh "
            "context with its own system prompt and skills, and its final report "
            "is returned as the result. Use this for specialized work covered by "
            "a subagent's description, and give it a complete, self-contained task."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "Name of the subagent to dispatch to",
                    "enum": self.directory.names(),
                },
                "task": {
                    "type": "string",
                    "description": "Complete, self-contained task description "
                    "for the subagent",
                },
            },
            "required": ["agent", "task"],
        }

    async def execute(self, agent: str, task: str) -> ToolResult:
        defn = self.directory.definitions.get(agent)
        if defn is None:
            available = ", ".join(self.directory.names()) or "(none)"
            return ToolResult(
                success=False,
                content="",
                error=f"Unknown subagent '{agent}'. Available: {available}",
            )
        if not task.strip():
            return ToolResult(success=False, content="", error="Task must not be empty")

        tools = self.base_tools + list(self.directory.skill_tools.get(agent, []))
        sub_agent = Agent(
            llm_client=self.llm_client,
            system_prompt=defn.system_prompt,
            tools=tools,
            max_steps=self.max_steps,
            workspace_dir=self.workspace_dir,
        )
        sub_agent.add_user_message(task)
        result = await sub_agent.run()
        return ToolResult(success=True, content=result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dispatch_tool.py -v`
Expected: PASS（5 个测试全绿）

- [ ] **Step 5: Run the full test suite（确保没碰坏现有行为）**

Run: `python -m pytest tests/ -v --ignore=tests/test_integration.py --ignore=tests/test_agent.py --ignore=tests/test_session_integration.py --ignore=tests/test_llm.py --ignore=tests/test_llm_clients.py --ignore=tests/test_mcp.py --ignore=tests/test_acp.py`
Expected: PASS（排除的是打真 API / 真集成的那批；如个别排除文件不存在按实际名字调整）

- [ ] **Step 6: Commit**

```bash
git add mini_agent/multi_agent/dispatch_tool.py tests/test_dispatch_tool.py
git commit -m "feat: add dispatch_agent tool for delegating tasks to plugin subagents

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: config 字段 + cli 接线

**Files:**
- Modify: `mini_agent/config.py`（`ToolsConfig` 类体，约 51-70 行；`from_yaml` 的 tools 解析段，约 157-159 行）
- Modify: `mini_agent/cli.py`（主装配区：`add_workspace_tools(...)` 调用之后、memory policy 注入块之后，约 768 行与 808 行附近）
- Test: `tests/test_plugin_loader.py`（追加 config 解析测试）

**Interfaces:**
- Consumes: Task 2 的 `discover_plugins` / `SubagentDirectory.prompt_section()`；Task 3 的 `DispatchAgentTool(directory, llm_client, base_tools, workspace_dir, max_steps)`；现有 `Config.get_package_dir()`、`Colors`、`config.agent.max_steps`。
- Produces: `config.tools.enable_plugins: bool = True`、`config.tools.plugins_dir: str = "./plugins"`；启动时主 agent 多一个 `dispatch_agent` 工具、system prompt 末尾多一段 `## Available Subagents`。

- [ ] **Step 1: Write the failing test**

在 `tests/test_plugin_loader.py` 追加：

```python
def test_config_plugins_fields(tmp_path):
    from mini_agent.config import Config

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "tools:\n  enable_plugins: false\n  plugins_dir: ./custom-plugins\n",
        encoding="utf-8",
    )
    config = Config.from_yaml(cfg_file)
    assert config.tools.enable_plugins is False
    assert config.tools.plugins_dir == "./custom-plugins"


def test_config_plugins_defaults(tmp_path):
    from mini_agent.config import Config

    config = Config.from_yaml(tmp_path / "missing.yaml")
    assert config.tools.enable_plugins is True
    assert config.tools.plugins_dir == "./plugins"
```

注意：先跑一下确认 `Config.from_yaml` 对缺文件 / 仅 tools 段的 yaml 的现有行为；若它要求文件必须存在或必须含 llm 段，按现有 `from_yaml` 的默认值处理方式微调这两个测试（保持断言不变，调整输入构造），不改 config.py 的现有解析结构。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_plugin_loader.py -v -k config`
Expected: FAIL — `AttributeError: 'ToolsConfig' object has no attribute 'enable_plugins'`（或 from_yaml 对缺文件的处理与断言不符，先按注调整测试输入）

- [ ] **Step 3: Implement config fields**

`mini_agent/config.py` 的 `ToolsConfig` 类体加两个字段（紧挨 `enable_skills` / `enable_mcp` 的风格）：

```python
    enable_plugins: bool = True
    plugins_dir: str = "./plugins"
```

`from_yaml` 的 tools 解析段（`enable_mcp=...` 那组）加：

```python
            enable_plugins=tools_data.get("enable_plugins", True),
            plugins_dir=tools_data.get("plugins_dir", "./plugins"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_plugin_loader.py -v`
Expected: PASS（13 个测试全绿）

- [ ] **Step 5: Wire up cli.py**

`mini_agent/cli.py` 主装配区，`add_workspace_tools(tools, config, workspace_dir)` 调用之后插入（步骤注释顺延编号不必改动，沿用现有 `# N.` 风格写 `# 4.5`）：

```python
    # 4.5 Load plugins (Claude Code format agents/skills from mini_agent/plugins)
    plugin_directory = None
    if config.tools.enable_plugins:
        from mini_agent.multi_agent.dispatch_tool import DispatchAgentTool
        from mini_agent.multi_agent.plugin_loader import discover_plugins

        plugins_path = Path(config.tools.plugins_dir).expanduser()
        search_paths = [
            plugins_path,                              # ./plugins
            Path("mini_agent") / plugins_path,         # ./mini_agent/plugins
            Config.get_package_dir() / plugins_path,   # site-packages/mini_agent/plugins
        ]
        plugins_dir = next((p.resolve() for p in search_paths if p.exists()), None)
        if plugins_dir:
            plugin_directory = discover_plugins(plugins_dir)
            for warning in plugin_directory.warnings:
                print(f"{Colors.YELLOW}{warning}{Colors.RESET}")
            if plugin_directory.definitions:
                # 排除主 agent 的 get_skill：Agent.tools 按名字建 dict，
                # 两个 get_skill 会静默互相覆盖；subagent 只用插件版 skill 工具。
                base_for_subagents = [t for t in tools if t.name != "get_skill"]
                dispatch_tool = DispatchAgentTool(
                    directory=plugin_directory,
                    llm_client=llm_client,
                    base_tools=base_for_subagents,
                    workspace_dir=str(workspace_dir),
                    max_steps=config.agent.max_steps,
                )
                tools.append(dispatch_tool)
                print(
                    f"{Colors.GREEN}✅ Loaded plugins: {len(plugin_directory.definitions)} "
                    f"subagents ({', '.join(plugin_directory.names())}){Colors.RESET}"
                )
                # frontmatter 里引用的、本机没有的工具（mcp__factset__* 等）警告一次
                known = {t.name for t in tools}
                unresolved = sorted(
                    {t for d in plugin_directory.definitions.values() for t in d.tools}
                    - known
                )
                if unresolved:
                    print(
                        f"{Colors.YELLOW}⚠️  插件引用的不可用工具（已忽略）: "
                        f"{', '.join(unresolved)}{Colors.RESET}"
                    )
            else:
                print(f"{Colors.YELLOW}⚠️  No plugin agents found in {plugins_dir}{Colors.RESET}")
```

然后在该文件 memory policy 注入块（`system_prompt.replace("{MEMORY_POLICY}", "")` 结尾处）之后插入：

```python
    # 6.6 Inject available subagents into system prompt
    if plugin_directory and plugin_directory.definitions:
        system_prompt = system_prompt + "\n\n" + plugin_directory.prompt_section()
```

- [ ] **Step 6: Verify import + offline startup**

Run: `python -c "from mini_agent.cli import main"`
Expected: 无异常（无循环导入）

Run: `python -c "
from pathlib import Path
from mini_agent.multi_agent.plugin_loader import discover_plugins
d = discover_plugins(Path('mini_agent/plugins'))
print(len(d.definitions), d.names())
print('warnings:', d.warnings)
"`
Expected: 打印 `10` 和 10 个插件 agent 名（earnings-reviewer、gl-reconciler、kyc-screener、market-researcher、meeting-prep-agent、model-builder、month-end-closer、pitch-agent、statement-auditor、valuation-reviewer）；warnings 为空或仅含无害告警

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest tests/ -v --ignore=tests/test_integration.py --ignore=tests/test_agent.py --ignore=tests/test_session_integration.py --ignore=tests/test_llm.py --ignore=tests/test_llm_clients.py --ignore=tests/test_mcp.py --ignore=tests/test_acp.py`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add mini_agent/config.py mini_agent/cli.py tests/test_plugin_loader.py
git commit -m "feat: wire plugin loading and dispatch_agent into CLI startup

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 人工冒烟验证（需要可用的 LLM key）

**Files:**
- 无代码改动；只验证

**Interfaces:**
- Consumes: Task 4 完成后的完整启动链路。
- Produces: 人工确认清单（通过/不通过）。

- [ ] **Step 1: 启动并确认插件加载横幅**

Run: `mini-agent`
Expected 启动输出包含：
- `✅ Loaded plugins: 10 subagents (earnings-reviewer, gl-reconciler, ...)`
- `⚠️  插件引用的不可用工具（已忽略）: mcp__factset__*, ...`（Review Focus 第 4 条）

- [ ] **Step 2: 委派闭环**

在交互界面输入（或用 `mini-agent --task "..."` 非交互执行）：

```
请用 dispatch_agent 把这个任务委派给 market-researcher：简单说明你能提供什么能力，两三句话即可。
```

Expected：
- 主 agent 调用 `dispatch_agent(agent="market-researcher", task=...)`
- subagent 的流式输出可见（与主 agent 共用 llm_client 的 stream_callback）
- 主 agent 最终回复包含 subagent 的报告内容

- [ ] **Step 3: 回归主流程**

随便问一个会用到工具的普通问题（如"帮我看看当前目录有什么文件"），确认主 agent 自身工具（read/bash）与原有 skills（get_skill）仍正常，辩论模式入口不受影响。

- [ ] **Step 4: 收尾提交（如有人工调整）**

```bash
git add -A
git commit -m "fix: adjustments from plugin loader smoke test

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

（若 Step 1-3 全部一次通过且无代码改动，跳过本步。）
