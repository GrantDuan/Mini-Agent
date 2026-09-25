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
