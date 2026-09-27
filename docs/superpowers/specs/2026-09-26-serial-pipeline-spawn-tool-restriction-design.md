# 串行协作（Pipeline）+ spawn 时工具限制 — 设计文档

- **日期**：2026-09-26
- **状态**：待用户审查
- **前置**：M1 插件加载器（`docs/superpowers/plans/2026-09-25-plugin-loader.md`）已合入：`dispatch_agent` 单层委派可用，frontmatter `tools:` 已解析但被忽略
- **模式**：Pipeline（串行协作，输出传递）——对应 `docs/Agent进阶学习计划.md` §12 协作模式 1

## 1. 目标

让插件 subagent 能作为 orchestrator 继续派生下一层受限 agent，形成串行执行链（主 agent → orchestrator → worker），且**每次 spawn 都按 agent 定义限制工具**。验收标志：gl-reconciler 插件的完整工作流（reader → 根因 → critic → resolver）在本地 CSV 演示数据上端到端跑通，且日志能证明 reader 全程只持有 `read_file`。

## 2. 背景与缺口

M1 之后的现状（`mini_agent/multi_agent/dispatch_tool.py`、`plugin_loader.py`、`cli.py`）：

- 主 agent 可 `dispatch_agent` 委派插件 subagent，阻塞等报告返回（本身已是串行）
- subagent **拿不到** dispatch_agent（基座在挂 dispatch 前构建），链断在第一层
- frontmatter `tools:` 被解析进 `AgentDefinition.tools` 但从未生效——subagent 无条件获得全部基座工具 + 插件 skills
- 插件是 Claude Code 格式，`tools:` 写的是 Claude Code 工具名（`Read, Grep, Glob, mcp__internal-gl__*`），与 Mini-Agent 实际工具名（`read_file, write_file, edit_file, bash, calculator, get_skill` + MCP 原名）对不上
- gl-reconciler / valuation-reviewer 的 agent 定义描述了 orchestrator 派生 reader/critic/resolver 的串行链，且工具限制是安全设计的一部分（不可信内容只能被低权限 agent 接触；写权限只在 resolver）——当前运行时无法支撑

## 3. 关键决策（会话中确认）

| # | 决策 | 选择 | 落选方案 |
|---|---|---|---|
| 1 | 协作模式 | Pipeline（串行链，orchestrator 编排，输出经 orchestrator 传递） | 并行聚合、辩论（已有 DebateOrchestrator） |
| 2 | `tools:` 名字解析 | Mini-Agent 工具名精确匹配 + `*` 通配符（fnmatch）；插件 frontmatter 改写为 Mini-Agent 名 | 别名映射表（Grep/Glob 无对应物，半吊子映射制造隐性错误） |
| 3 | spawn 能力授予 | `dispatch_agent` 写进 `tools:` 才有；限制只来自定义文件，**调用参数不提供 allowed_tools**（调用方不能临时提权） | 所有 subagent 自动可 spawn（被注入的 reader 能 spawn 有 Write 的角色，防线失效） |
| 4 | 深度上限 | `MAX_SPAWN_DEPTH = 2`：被派 agent 最多两层，**L2 是叶子**（无 dispatch 工具） | 无上限（自递归风险）；L2 可再派（链过长难审计，无场景需要） |

## 4. 设计

### 4.1 `tools:` 语义规则

| 规则 | 内容 |
|---|---|
| 缺省 | frontmatter 无 `tools:` 字段 → 行为完全不变：全部基座工具 + 本插件 skill 工具（向后兼容，现有测试不动） |
| 匹配池 | 基座工具（主 agent 工具集去掉名为 `get_skill` 的，即 `build_subagent_base_tools` 结果）。本插件 skill 工具**不进池**，拼装时无条件附带（见下条） |
| 名字规则 | 无 `*` 的条目精确匹配工具名；含 `*` 的条目用 `fnmatch.fnmatch(tool_name, pattern)` 匹配（`mcp__internal-gl__*` 命中该 MCP 全部工具）。`tools: *` 等价全量，不特判 |
| spawn 授予 | 条目 `dispatch_agent` 不参与解析，作为授予标记消费（见 4.2） |
| skills 例外 | 本插件的 skill 工具（`get_skill`）**始终附带**，不参与解析与过滤——skills 是插件内容不是工具；同插件所有角色（含 reader）都拿到 |
| 解析失败 | 单个名字解析不到 → 启动时警告并丢弃；全部解析不到（摘掉 `dispatch_agent` 后零命中）→ 该 agent 基座工具集为空（`get_skill` 仍附带）+ 启动点名警告。宁可跑出没工具的废 agent，不静默回退全量权限 |
| 时机 | 启动时预计算：MCP 工具在 cli 步骤 4 已入池、插件在 4.5，池完整。每个 agent 解析一次并缓存，spawn 时直接拼装 |

### 4.2 运行时机制（串行链）

```
主 agent（level 0，现有 dispatch_agent 实例 depth=0）
  └─ dispatch → L1 orchestrator（实例 depth=1，tools: 含 dispatch_agent 时挂）
       └─ dispatch → L2 worker（agent 层级 2，不持有 dispatch 实例——叶子）
```

- `DispatchAgentTool` 新增构造参数 `depth: int = 0` 与 `owner_name: str | None = None`；实例的 `depth` = 持有它的 agent 的层级
- spawn 子 agent 时，挂 dispatch 的条件 = **子层级 < MAX_SPAWN_DEPTH(=2)** 且子定义 `tools:` 含 `dispatch_agent`；满足则给子 agent 构造 `DispatchAgentTool(depth=子层级, owner_name=子名)`。按此条件 L2 不持有任何 dispatch 实例
- 不满足 → 子 agent 根本看不到 dispatch 工具（不报错，与 `max_steps` 同为资源上限语义）
- 子 dispatch 实例的参数 `enum` = `directory.names()` 去掉 `owner_name`（防自递归；深度上限兜底）。主 agent 实例不排除任何名字
- 串行语义不变：dispatch 阻塞到子 agent 跑完、最终报告作为工具结果返回
- 解析纯函数 `resolve_tools(definition, pool) -> (grants_dispatch: bool, resolved: list, unresolved: list[str])`：摘出 `dispatch_agent` 条目作为授予标记返回 → 其余条目对池做精确/fnmatch 匹配 → 返回授予与否、命中工具与未命中条目。缓存放 `SubagentDirectory.resolved_tools: dict[str, list]`（agent 名 → 解析后的基座工具列表；不含 get_skill 与 dispatch 实例，spawn 时拼装）
- `DispatchAgentTool.__init__`（即 cli 4.5 步接线处，此时工具池已完整）对目录内每个 agent 跑一次解析，汇总 unresolved 警告——**取代**现有 `cli.py:809-819` 的整块"已忽略"警告；子实例构造时跳过已缓存的 agent（幂等）；`DispatchAgentTool.execute` 改为从缓存取工具集拼装
- `MAX_SPAWN_DEPTH` 为 `dispatch_tool.py` 模块常量，不进 config（YAGNI）

### 4.3 插件内容

**gl-reconciler 角色矩阵**（安全护栏落地为机制）：

| 角色 | `tools:` | 意图 |
|---|---|---|
| `gl-reconciler`（改写现有 md） | `read_file, bash, dispatch_agent, mcp__internal-gl__*, mcp__subledger__*` | orchestrator 无 `write_file`——"orchestrator never writes" 生效；正文增加编排说明（可派 reader/critic/resolver、各角色职责与产出传递顺序） |
| `reader`（新增） | `read_file` | 按 asset class 读数据找 break 候选；无 MCP 无写，专门接触不可信内容 |
| `critic`（新增） | `read_file, bash` | 独立复核每个 break，只读 |
| `resolver`（新增） | `read_file, write_file` | 唯一持有写权限，只吃验证过的 break 集，产出 exception report |

新增 md 均需 `name` / `description` / `tools` frontmatter + 简短角色正文；全文在实现计划中给出。三个新角色自动获得本插件 `get_skill`（按 4.1 skills 例外）。

**其余 9 个插件**：frontmatter 机械替换为 Mini-Agent 工具名（每文件一行），消除启动警告噪音，置于实现计划最后一个 task。

**演示数据**：`examples/gl-recon-demo/` 下提供 `gl_extract.csv` + `subledger_extract.csv`（含若干预设 break：timing / FX / mapping / duplicate 各至少一条）与 README（如何跑演示）。

### 4.4 演示场景与验收标准

1. workspace 放入演示 CSV，一句话任务："Run the GL reconciliation for trade date 2026-09-25, asset classes: equities, fixed income"
2. 主 agent → gl-reconciler → reader×2 → orchestrator 根因（bash）→ critic → resolver，全程串行
3. 验收点：
   - workspace 出现 resolver 写出的 exception report 文件
   - 日志能确认 reader 只调用过 `read_file`（无 bash / write_file / MCP / dispatch）
   - 整条链按顺序完成，报告逐层返回

## 5. 测试策略

单元（扩展 `tests/test_dispatch_tool.py`、`tests/test_plugin_loader.py`）：

1. `resolve_tools`：精确匹配、`*` 通配符、`tools: *` 全量、`dispatch_agent` 摘出为授予标记、unresolved 逐名返回
2. 缺省 `tools:` → 全量基座 + 本插件 get_skill（现有行为回归）
3. `tools:` 生效 → 子 agent 工具集 = 解析结果 + 本插件 get_skill
4. spawn 门控：`tools:` 无 `dispatch_agent` → 子 agent 无 dispatch 工具
5. 深度上限：L2 即使 `tools:` 授予也拿不到 dispatch 工具
6. enum 排除自身（`owner_name` 生效）
7. 解析失败：单名失败 → 警告+丢弃；全失败 → 空基座 + 警告；`get_skill` 始终附带
8. md 解析回归：新增 reader/critic/resolver 能被 `discover_plugins` 加载

集成：FakeLLM 驱动三级链 主→A→B，断言串行调用顺序、B 无 dispatch 工具、报告逐层返回。实现走 TDD。

## 6. 非目标与已知限制

- **不修** Esc 取消传播（M1 已知限制延续）：dispatch 阻塞期间不响应取消，链越深阻塞越久；docstring 注明
- **不做** spawn 时调用参数限制（`allowed_tools`）：限制只来自定义文件，防调用方提权
- **不做** 并行派发、结果聚合（学习计划协作模式 2，另行设计）
- **不动** AgentRegistry / DebateOrchestrator（辩论模式不受影响）
- **不做** Claude Code 工具名别名表：未来需要兼容外部 Claude Code 插件时再加（纯增量）
- subagent 系统提示不自动注入可用 subagent 清单：orchestrator 能派谁由 dispatch 工具的 `enum` 呈现，编排职责写进插件 md 正文

## 7. 涉及文件

| 文件 | 改动 |
|---|---|
| `mini_agent/multi_agent/dispatch_tool.py` | `resolve_tools`、`depth`/`owner_name`、门控、enum 排除自身、execute 读缓存 |
| `mini_agent/multi_agent/plugin_loader.py` | `SubagentDirectory` 加 `resolved_tools: dict[str, list]` 缓存字段 |
| `mini_agent/cli.py` | 4.5 步接线：预计算 + 警告块替换 |
| `mini_agent/plugins/gl-reconciler/agents/*.md` | 改写 gl-reconciler，新增 reader/critic/resolver |
| `mini_agent/plugins/<其余 9 个>/agents/*.md` | frontmatter 机械替换 |
| `examples/gl-recon-demo/` | 演示 CSV + README |
| `tests/test_dispatch_tool.py`、`tests/test_plugin_loader.py` | 新增用例 |
