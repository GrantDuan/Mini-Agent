"""DispatchAgentTool - 主 agent 把任务委派给插件 subagent。

每次委派都用 AgentDefinition 构造一个全新的 Agent（全新上下文，与
Claude Code subagent 语义一致），跑完把最终报告作为工具结果返回。
不注册进 AgentRegistry，辩论模式（DebateOrchestrator）不受影响。

已知限制（M1）：subagent 运行期间不响应 Esc 取消（cancel_event=None），
主 agent 在 dispatch 返回后才检查取消。

spawn 时工具集由 agent 定义 frontmatter 的 tools: 解析决定
（缺省 = 全部基座 + 本插件 skills；见 resolve_tools 与 _resolve_directory）。
串行链：dispatch 阻塞到子 agent 跑完、最终报告作为工具结果返回；
子 agent 再派生受深度上限与显式授予门控（L2 为叶子，不持有 dispatch 实例）。
"""

from __future__ import annotations

import fnmatch
from typing import Any

from mini_agent.agent import Agent
from mini_agent.multi_agent.plugin_loader import AgentDefinition, SubagentDirectory
from mini_agent.tools.base import Tool, ToolResult


def build_subagent_base_tools(tools: list) -> list:
    """从主 agent 工具集中构造 subagent 基座工具集。

    排除所有名为 get_skill 的工具：Agent.tools 按名字建 dict，主 agent 的
    get_skill 若混入基座，会与插件 skill 工具静默互相覆盖。插件的
    get_skill 由 SubagentDirectory.skill_tools 单独提供，不经过这里。
    """
    return [t for t in tools if t.name != "get_skill"]


# 被派 agent 最大层数：主(0) → L1(1) → L2(2)，L2 为叶子（不持有 dispatch 实例）。
MAX_SPAWN_DEPTH = 2


def resolve_tools(definition: AgentDefinition, pool: list) -> tuple[bool, list, list[str]]:
    """把 AgentDefinition.tools 解析成实际工具。

    返回 (grants_dispatch, resolved, unresolved)：
    - grants_dispatch: tools: 显式列出 dispatch_agent（spawn 授予标记，不进 resolved）
    - resolved: 命中的池内工具；精确条目按条目序、通配符按池序展开，名字去重
    - unresolved: 解析不到的条目原样列出（含零命中的通配符）
    """
    grants = False
    resolved: list = []
    seen: set[str] = set()
    unresolved: list[str] = []
    for entry in definition.tools:
        if entry == "dispatch_agent":
            grants = True
            continue
        if "*" in entry:
            matches = [t for t in pool if fnmatch.fnmatch(t.name, entry)]
            if not matches:
                unresolved.append(entry)
                continue
            hits = matches
        else:
            hit = next((t for t in pool if t.name == entry), None)
            if hit is None:
                unresolved.append(entry)
                continue
            hits = [hit]
        for tool in hits:
            if tool.name not in seen:
                seen.add(tool.name)
                resolved.append(tool)
    return grants, resolved, unresolved


def format_unresolved_warnings(
    unresolved: dict[str, list[str]], unresolved_wildcards: dict[str, list[str]]
) -> list[str]:
    """启动时逐 agent 的未解析工具警告行（精确名与零命中通配分列，按 agent 名排序）。"""
    lines: list[str] = []
    for name in sorted(set(unresolved) | set(unresolved_wildcards)):
        if unresolved.get(name):
            lines.append(f"⚠️  {name}: 未解析工具（已忽略）: {', '.join(unresolved[name])}")
        if unresolved_wildcards.get(name):
            lines.append(
                f"⚠️  {name}: 零命中通配模式（MCP 未安装或拼写有误，已忽略）: "
                f"{', '.join(unresolved_wildcards[name])}"
            )
    return lines


class DispatchAgentTool(Tool):
    """把任务委派给已加载插件的某个 subagent。"""

    def __init__(
        self,
        directory: SubagentDirectory,
        llm_client: Any,
        base_tools: list,
        workspace_dir: str = "./workspace",
        max_steps: int = 30,
        depth: int = 0,
        owner_name: str | None = None,
    ) -> None:
        self.directory = directory
        self.llm_client = llm_client
        self.base_tools = list(base_tools)
        self.workspace_dir = workspace_dir
        self.max_steps = max_steps
        self.depth = depth              # 持有本实例的 agent 层级：主 agent=0
        self.owner_name = owner_name    # 持有者的定义名：enum 排除自身，防自递归
        self.unresolved: dict[str, list[str]] = {}
        self.unresolved_wildcards: dict[str, list[str]] = {}  # 零命中通配模式（多为未安装的 MCP）
        self._resolve_directory()

    def _resolve_directory(self) -> None:
        """对目录内每个 agent 解析 tools: 并缓存（幂等：子实例跳过已缓存的）。

        - 缺省（frontmatter 没写 tools:）→ 缓存 base_tools 副本，行为与 M1 一致
        - 写了 → 缓存 resolve_tools 结果；未解析条目按精确名/零命中通配分类收集
          供启动警告（精确名多为拼写错误，零命中通配多为 MCP 未安装）
        """
        for name, defn in self.directory.definitions.items():
            if name in self.directory.resolved_tools:
                continue
            if not defn.tools:
                self.directory.resolved_tools[name] = list(self.base_tools)
                self.directory.spawn_grants[name] = False
                continue
            grant, resolved, unresolved = resolve_tools(defn, self.base_tools)
            self.directory.resolved_tools[name] = resolved
            self.directory.spawn_grants[name] = grant
            for entry in unresolved:
                bucket = self.unresolved_wildcards if "*" in entry else self.unresolved
                bucket.setdefault(name, []).append(entry)

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
                    "enum": self._available_names(),
                },
                "task": {
                    "type": "string",
                    "description": "Complete, self-contained task description "
                    "for the subagent",
                },
            },
            "required": ["agent", "task"],
        }

    def _available_names(self) -> list[str]:
        """可派发的 agent 名：全部定义去掉自身（owner_name 为 None 时不排除）。"""
        names = self.directory.names()
        if self.owner_name is None:
            return names
        return [n for n in names if n != self.owner_name]

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

        resolved = self.directory.resolved_tools.get(agent, self.base_tools)
        tools = list(resolved) + list(self.directory.skill_tools.get(agent, []))

        # spawn 门控：显式授予（构造时解析缓存，唯一事实源）+ 深度上限（子层级 < MAX_SPAWN_DEPTH，L2 为叶子）
        child_level = self.depth + 1
        if self.directory.spawn_grants.get(agent, False) and child_level < MAX_SPAWN_DEPTH:
            tools.append(
                DispatchAgentTool(
                    directory=self.directory,
                    llm_client=self.llm_client,
                    base_tools=self.base_tools,
                    workspace_dir=self.workspace_dir,
                    max_steps=self.max_steps,
                    depth=child_level,
                    owner_name=agent,
                )
            )

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
