"""Agent 间通信协议。

定义所有协作模式共用的消息信封（AgentMessage）和公共辩论记录
（SharedTranscript）。Agent 之间不直接共享各自的对话历史，而是通过
transcript 交换消息，由编排器决定注入时机，与现有单 Agent 循环兼容。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

BROADCAST = "broadcast"


@dataclass
class AgentMessage:
    """协作中一条被投递的消息。

    sender: 发送方角色名，如 "bull"、"coordinator"。
    receiver: 接收方角色名；发给所有人时用 BROADCAST。
    round: 轮次/序号，含义由具体协作模式定义（debate 里是辩论轮次）。
    content: 正文文本。
    artifacts: 结构化载荷，如引用的工具结果、置信度、中间产物，
        供将来 Pipeline / Parallel 等模式传递数据用。
    """

    sender: str
    receiver: str
    round: int
    content: str
    artifacts: dict[str, Any] = field(default_factory=dict)


class SharedTranscript:
    """所有 AgentMessage 的公共记录，模式无关。"""

    def __init__(self) -> None:
        self.messages: list[AgentMessage] = []

    def append(self, message: AgentMessage) -> None:
        self.messages.append(message)

    def for_agent(self, name: str) -> list[AgentMessage]:
        """取某个 agent 收到的消息（发给它本人或广播）。"""
        return [m for m in self.messages if m.receiver in (name, BROADCAST)]

    def last_from(self, sender: str) -> AgentMessage | None:
        """取某发送方最近一条消息，没有则返回 None。"""
        for m in reversed(self.messages):
            if m.sender == sender:
                return m
        return None

    def render(self) -> str:
        """渲染成人类可读的全文（给裁判或落盘用）。"""
        lines: list[str] = []
        for m in self.messages:
            header = f"[Round {m.round}] {m.sender} → {m.receiver}"
            lines.append(f"### {header}\n\n{m.content}\n")
        return "\n".join(lines) if lines else "(empty transcript)"

    def __len__(self) -> int:
        return len(self.messages)
