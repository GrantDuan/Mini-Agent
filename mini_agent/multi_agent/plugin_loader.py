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

from mini_agent.tools.skill_tool import create_skill_tools

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
