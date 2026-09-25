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

import re
from dataclasses import dataclass
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
