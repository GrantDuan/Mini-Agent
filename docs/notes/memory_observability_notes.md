# Memory 使用观测：日志设计与"忘了用 memory"的分析

> 学习笔记：Mini-Agent 新增的 memory 专属日志（`memory_run_*.log`）记录什么、
> 为什么这样设计，以及"LLM 忘了使用 memory"如何用日志归因。

## 日志文件

每次 agent run 生成一个 `~/.mini-agent/log/memory_run_YYYYMMDD_HHMMSS.log`，
JSON lines，每行一个事件。与 `agent_run_*.log`（完整交互记录）并行，互不干扰。

| 事件类型 | 记录内容 |
|---|---|
| `run_started` | 可用 memory 工具列表、策略是否注入（policy_injected）、system_prompt 哈希与长度、memory_judge 标志 |
| `memory_tool_call` | turn_index、tool_name、arguments |
| `memory_tool_result` | success、content_summary（截 300 字符）、error、latency_ms |
| `turn_signal` | 每轮：user_excerpt（截 100 字符）、可用 memory 工具、policy_injected、memory_tools_called、tools_called |
| `run_summary` | total_turns、memory_tool_calls、memory_tool_errors、counts_by_tool |

关键设计：**"忘了用 memory"是"没有发生的事"，本身不会留下日志**。
所以每轮写一条 `turn_signal`，把"当时模型能看到什么"（策略在不在、工具有哪些、
用户说了什么）和"它实际做了什么"（调了哪些工具）并排记录，让"该用而没用"
变成事后可以审计的问题。

## "忘了用 memory"的成因 → 日志信号对照

| 成因 | 日志信号 | 处理方向 |
|---|---|---|
| 策略未注入 | `turn_signal.policy_injected = false`（mcp.json 里 memory server 被禁用/没配） | 修配置 |
| 策略太弱/措辞不触发 | policy_injected=true 但 memory_tools_called 长期为空，看 user_excerpt 与策略条文是否对得上 | 改 `MEMORY_POLICY_TEXT`（mini_agent/memory.py） |
| 用户措辞没触发检索 | 某轮 user_excerpt 明显涉及过去/事实，但 memory_tools_called=[] | 这正是策略文案要覆盖的场景；改文案后复测 |
| 模型判断与记忆无关 | 同上，人工复盘觉得"其实该查" | 将来 LLM 裁判解决的正是这类边界判断 |
| 工具失败后模型放弃 | `memory_tool_result.success=false` 且后续 turn 不再有调用 | 看 error：npx 冷启动超时？server 崩了？ |
| 记忆库为空/检索无果 | content_summary 出现 "0 entities" / "No entities found" | 正常现象；若频繁出现说明写入端没跑起来 |
| 上下文超长挤掉注意力 | run_summary.total_turns 很大；agent_run 日志里历史膨胀 | system prompt 不会被 summarize 挤掉，但注意力会稀释——精简策略文案 |

## 为什么不每轮调一个小模型当裁判

"每轮结束后用 LLM 判断'这轮是否该读/存记忆'"技术上可行，但：

1. **成本与延迟**：绝大多数轮与记忆无关，逐轮裁判是在为 5% 的轮次付 100% 的税
2. **裁判自己也不可靠**：判断"该不该查记忆"需要理解整个任务上下文，小模型判错会污染日志信号
3. **数据先于算法**：turn_signal 已经把归因所需的原始信号全留下了，人工复盘前几十条就能知道主要成因；等真的需要自动化再上离线批量裁判（对已有日志跑，不影响线上）

因此 `--memory-judge` / `AgentConfig.memory_judge` 目前是**预留开关（no-op）**，
只写入 `run_started` 事件，保证将来裁判上线时日志格式不用再改。

## 使用方式

```bash
# 正常使用即自动记录（memory server 可用时）
mini-agent -w <workspace> -t "记住我在做 Mini-Agent，明天要用 glm 跑评测"

# 快速复盘一次 run
cat ~/.mini-agent/log/memory_run_*.log
# 只看"该用没用"的信号
grep turn_signal ~/.mini-agent/log/memory_run_*.log
```
