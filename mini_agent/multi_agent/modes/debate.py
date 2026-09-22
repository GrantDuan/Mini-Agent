"""Debate 协作模式：多空对抗 N 轮后由裁判裁决。

典型场景是投资决策：多方（bull）与空方（bear）各自使用工具查真实
行情/公告来支撑论点，逐轮反驳；裁判（judge）不给工具，只依据公共
transcript 裁决。
"""

from __future__ import annotations

from pathlib import Path

from mini_agent.multi_agent.orchestrator import BaseOrchestrator
from mini_agent.multi_agent.protocol import AgentMessage, BROADCAST, SharedTranscript
from mini_agent.multi_agent.registry import AgentRegistry

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "config" / "debate_prompts"

DEFAULT_NUM_ROUNDS = 2


def load_prompt(role: str) -> str:
    """加载某个辩手/裁判角色的 system prompt。"""
    path = PROMPTS_DIR / f"{role}.md"
    if not path.exists():
        raise FileNotFoundError(f"Debate prompt not found: {path}")
    return path.read_text(encoding="utf-8")


class DebateOrchestrator(BaseOrchestrator):
    def __init__(self, num_rounds: int = DEFAULT_NUM_ROUNDS, on_turn_start=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.num_rounds = max(1, num_rounds)
        self.on_turn_start = on_turn_start  # callable(role: str, round: int)，供 UI 打印轮次标头

    async def run(self, topic: str) -> str:
        bull = self._spawn("bull", load_prompt("bull"))
        bear = self._spawn("bear", load_prompt("bear"))

        for round_no in range(1, self.num_rounds + 1):
            await self._agent_turn(bull, "bull", topic, round_no, opener=(round_no == 1))
            if self._aborted():
                return "Task cancelled by user."
            await self._agent_turn(bear, "bear", topic, round_no)
            if self._aborted():
                return "Task cancelled by user."

        if self._aborted():
            return "Task cancelled by user."
        return await self._judge(topic)

    def _aborted(self) -> bool:
        return self.cancel_event is not None and self.cancel_event.is_set()

    async def _agent_turn(
        self, agent, role: str, topic: str, round_no: int, opener: bool = False
    ) -> str:
        """组装注入内容并让该辩手发言，记录进 transcript。"""
        if self.on_turn_start:
            self.on_turn_start(role, round_no)
        parts = [f"辩论主题：{topic}", f"当前轮次：第 {round_no} 轮（共 {self.num_rounds} 轮）"]

        if opener:
            parts.append("这是开场陈词，你先发言。请先用工具核实关键数据，再基于数据立论。")
        else:
            opponent = "bear" if role == "bull" else "bull"
            opponent_msg = self.transcript.last_from(opponent)
            if opponent_msg:
                parts.append(
                    f"对方（{opponent}）上一轮的完整论点如下：\n\n---\n{opponent_msg.content}\n---"
                )
                parts.append(
                    "请直接回应对方的关键论点（哪些成立、哪些被证据推翻），"
                    "并用工具核实数据后补充或修正己方论点。不要重复对方已说的内容。"
                )

        content = await self._turn(agent, "\n\n".join(parts))
        self.transcript.append(AgentMessage(role, BROADCAST, round_no, content))
        return content

    async def _judge(self, topic: str) -> str:
        judge = self._spawn("judge", load_prompt("judge"), tools=[])
        final_round = self.num_rounds
        if self.on_turn_start:
            self.on_turn_start("judge", final_round)
        content = await self._turn(
            judge,
            f"辩论主题：{topic}\n以下是多空双方共 {final_round} 轮辩论的完整记录，请做出裁决：\n\n"
            + self.transcript.render(),
        )
        self.transcript.append(AgentMessage("judge", BROADCAST, final_round, content))
        return content
