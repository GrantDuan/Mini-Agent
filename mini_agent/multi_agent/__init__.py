"""多 Agent 协作系统。

公共设施（protocol / registry / orchestrator）模式无关；具体协作
模式在 modes/ 下实现，首个模式为 Debate（多空辩论 + 裁决）。
将来可按同样方式新增 Pipeline / Parallel / Hierarchical。
"""

from mini_agent.multi_agent.modes.debate import DebateOrchestrator
from mini_agent.multi_agent.orchestrator import BaseOrchestrator
from mini_agent.multi_agent.protocol import BROADCAST, AgentMessage, SharedTranscript
from mini_agent.multi_agent.registry import AgentRegistry

__all__ = [
    "AgentMessage",
    "AgentRegistry",
    "BROADCAST",
    "BaseOrchestrator",
    "DebateOrchestrator",
    "SharedTranscript",
]
