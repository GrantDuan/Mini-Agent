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


def build_subagent_base_tools(tools: list) -> list:
    """从主 agent 工具集中构造 subagent 基座工具集。

    排除所有名为 get_skill 的工具：Agent.tools 按名字建 dict，主 agent 的
    get_skill 若混入基座，会与插件 skill 工具静默互相覆盖。插件的
    get_skill 由 SubagentDirectory.skill_tools 单独提供，不经过这里。
    """
    return [t for t in tools if t.name != "get_skill"]


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
