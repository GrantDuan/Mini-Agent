"""Test plugin loader (Claude Code format agents/skills)."""

from pathlib import Path

import pytest

from mini_agent.multi_agent.plugin_loader import (
    AgentDefinition,
    discover_plugins,
    parse_agent_md,
)


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


def write_config(tmp_path: Path, tools_block: str = "") -> Path:
    """写一个最小合法 config.yaml（from_yaml 要求顶层非占位 api_key）。"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        f"api_key: test-key-123\n{tools_block}",
        encoding="utf-8",
    )
    return cfg_file


def test_config_plugins_fields(tmp_path):
    from mini_agent.config import Config

    cfg_file = write_config(
        tmp_path, "tools:\n  enable_plugins: false\n  plugins_dir: ./custom-plugins\n"
    )
    config = Config.from_yaml(cfg_file)
    assert config.tools.enable_plugins is False
    assert config.tools.plugins_dir == "./custom-plugins"


def test_config_plugins_defaults(tmp_path):
    from mini_agent.config import Config

    config = Config.from_yaml(write_config(tmp_path))
    assert config.tools.enable_plugins is True
    assert config.tools.plugins_dir == "./plugins"


def test_discover_plugins_survives_gbk_stdout(tmp_path):
    """GBK 控制台下 create_skill_tools 内部的 ✅ print 不得让插件加载崩溃。"""
    import io
    import sys

    plugin_dir = tmp_path / "p"
    (plugin_dir / "agents").mkdir(parents=True)
    (plugin_dir / "agents" / "expert.md").write_text(
        "---\nname: expert\ndescription: An expert\n---\n\nBody.\n", encoding="utf-8"
    )
    (plugin_dir / "skills" / "s1").mkdir(parents=True)
    (plugin_dir / "skills" / "s1" / "SKILL.md").write_text(
        "---\nname: s1\ndescription: A skill\n---\n\nDo it.\n", encoding="utf-8"
    )

    fake = io.TextIOWrapper(io.BytesIO(), encoding="gbk", errors="strict")
    real_stdout = sys.stdout
    sys.stdout = fake
    try:
        directory = discover_plugins(tmp_path)
    finally:
        sys.stdout = real_stdout
    assert "expert" in directory.definitions
    assert "expert" in directory.skill_tools


def test_parse_agent_md_tools_as_yaml_list(tmp_path):
    """Review Focus #3：tools: 用 YAML 列表形式书写也照样解析。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    md = agents_dir / "listy.md"
    md.write_text(
        "---\nname: listy\ndescription: d\ntools:\n  - read_file\n  - bash\n---\n\nBody.\n",
        encoding="utf-8",
    )
    defn = parse_agent_md(md, plugin_name="p")
    assert defn is not None
    assert defn.tools == ["read_file", "bash"]


_REPO_PLUGINS = Path(__file__).resolve().parents[1] / "mini_agent" / "plugins"


@pytest.mark.skipif(
    not (_REPO_PLUGINS / "gl-reconciler").exists(),
    reason="mini_agent/plugins/ 不入库（.gitignore）：本机回归用，仓库无该目录时跳过",
)
def test_gl_reconciler_plugin_loads():
    """Review Focus #5：仓库真实插件目录的回归——4 个角色可加载，frontmatter
    为 Mini-Agent 工具名，reader 只持 read_file，全部角色拿到本插件 skills。
    真实文件若被存成 CRLF/BOM 也必须通过（_read_text 归一化）。"""
    repo_plugins = _REPO_PLUGINS
    directory = discover_plugins(repo_plugins)
    assert {"gl-reconciler", "reader", "critic", "resolver"} <= set(directory.names())

    assert directory.definitions["gl-reconciler"].tools == [
        "read_file", "bash", "dispatch_agent", "mcp__internal-gl__*", "mcp__subledger__*",
    ]
    assert directory.definitions["reader"].tools == ["read_file"]
    assert directory.definitions["critic"].tools == ["read_file", "bash"]
    assert directory.definitions["resolver"].tools == ["read_file", "write_file"]

    # 全部 4 个角色都属于 gl-reconciler 插件 → 都拿到本插件 skill 工具
    for name in ("gl-reconciler", "reader", "critic", "resolver"):
        skill_tool = directory.skill_tools[name][0]
        assert skill_tool.name == "get_skill"
        assert skill_tool.skill_loader.get_skill("gl-recon") is not None
