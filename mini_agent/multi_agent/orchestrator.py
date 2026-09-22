"""协作编排器基类。

保存构建子 Agent 所需的公共资源（llm_client/tools 与主会话复用），
提供 _spawn / _turn 两个公共能力。将来 Pipeline（串行传递）、
Parallel（并行聚合）、Hierarchical（层次分发）各自实现 run() 即可。
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Optional

from mini_agent.agent import Agent
from mini_agent.multi_agent.protocol import SharedTranscript
from mini_agent.multi_agent.registry import AgentRegistry


class BaseOrchestrator(ABC):
    def __init__(
        self,
        registry: AgentRegistry,
        transcript: SharedTranscript,
        llm_client,
        tools: Optional[list] = None,
        max_steps: int = 30,
        workspace_dir: str = "./workspace",
        cancel_event: Optional[asyncio.Event] = None,
    ) -> None:
        self.registry = registry
        self.transcript = transcript
        self.llm_client = llm_client
        self.tools = tools or []
        self.max_steps = max_steps
        self.workspace_dir = workspace_dir
        self.cancel_event = cancel_event

    @abstractmethod
    async def run(self, task: str) -> str:
        """执行一次协作，返回最终产出（如裁决/聚合结果）。"""

    def _spawn(self, name: str, system_prompt: str, tools: Optional[list] = None) -> Agent:
        """创建一个有独立 system_prompt 和独立历史的子 Agent。

        tools 为 None 时继承公共工具集（让辩手等角色能查数据）；
        传空列表则不给工具（如只依据 transcript 裁决的裁判）。
        """
        agent = Agent(
            llm_client=self.llm_client,
            system_prompt=system_prompt,
            tools=self.tools if tools is None else tools,
            max_steps=self.max_steps,
            workspace_dir=self.workspace_dir,
        )
        agent.cancel_event = self.cancel_event
        self.registry.register(name, agent)
        return agent

    async def _turn(self, agent: Agent, user_content: str) -> str:
        """向某个 agent 注入一段上下文并跑一轮，返回其最终输出文本。"""
        agent.add_user_message(user_content)
        return await agent.run(cancel_event=self.cancel_event)
