"""Agent 注册表：按名字注册/查找协作中的 Agent 角色。

Coordinator/Specialist 架构下，任务分发就是"按名字从 registry 取
agent"；Hierarchical 模式的动态分派直接复用这里。
"""

from __future__ import annotations

from mini_agent.agent import Agent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._descriptions: dict[str, str] = {}

    def register(self, name: str, agent: Agent, description: str = "") -> None:
        if name in self._agents:
            raise ValueError(f"Agent '{name}' is already registered")
        self._agents[name] = agent
        self._descriptions[name] = description

    def get(self, name: str) -> Agent:
        if name not in self._agents:
            raise KeyError(f"Unknown agent: '{name}' (registered: {self.names()})")
        return self._agents[name]

    def has(self, name: str) -> bool:
        return name in self._agents

    def names(self) -> list[str]:
        return list(self._agents.keys())

    def describe(self) -> list[tuple[str, str]]:
        """返回 (name, description) 列表，供 coordinator prompt 等使用。"""
        return [(name, self._descriptions[name]) for name in self._agents]
