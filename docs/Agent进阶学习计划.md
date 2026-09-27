# Mini Agent 进阶学习计划

> 本计划适用于已经学习了 lessons 和 mini-agent 代码的学习者

## 📚 学习路线图（原计划）

> ⚠️ 这是最初拟定的路线。**修订后的顺序见下一节**，差异处以下一节为准。

```
Week 1-2:  运行 examples → 创建自定义工具
Week 3-4:  深入 agent loop → Memory 系统
Week 5-6:  MCP 集成 → Skills 开发
Week 7-8:  Planning & AoT → 并行执行
Week 9-10: Evals → Telemetry → 监控
Week 11+:  实战项目 → 多 agent 系统
```

---

## 📍 学习进度与路线修订

> 更新于 2026-09-10

### 已完成

| 项 | 产出 / 证据 |
|---|---|
| 阶段一 #1 运行 Examples | — |
| 阶段一 #2 构建自定义工具 | [`weather_tool.py`](../mini_agent/tools/weather_tool.py) |
| 阶段一 #3 深入 Agent Loop | [Agent上下文管理机制详解.md](./Agent上下文管理机制详解.md) |
| 阶段二 #5 MCP 工具集成 | 自建 xueqiu-quote MCP 服务器；通读 [`mcp_loader.py`](../mini_agent/tools/mcp_loader.py) |
| 阶段三 #10 上下文管理（认知部分） | 同上文档：五层机制拆解 |

> 上表是从仓库产出推断的，请自行核对补全。

### 本次修订了什么

**① #4 Memory 实现四件套 → 降级为"按需"。** 理由见下文 #4 的修订说明。

**② #5 MCP → 标记"够用"而非"吃透"。** server 侧已能独立完成，client 侧流程已能讲清；剩余协议原语标记为"按需再查"。

**③ #8 Evals → 提前，建议作为下一步。** 理由见下文 #8 的修订说明。

**④ #10 上下文管理 → 从"认知"转入"实现"。** 你的详解文档描述的是 mini-agent **现有**机制，它当地基；下一步是在它之上实现**新**策略。

### 修订后的推荐顺序

| 阶段 | 内容 |
|---|---|
| ✅ 已完成 | Examples → 自定义工具 → Agent Loop → MCP（够用）→ 上下文管理（认知） |
| 🔜 下一步（高杠杆） | **#10 上下文管理（实现）** ← 详解文档是地基<br>**#8 Evals** ← 把玩具和生产分开的那道坎<br>**#5 MCP 收尾**（按需）← resources / prompts / sampling |
| 📅 之后 | #7 Planning & AoT → #9 Telemetry → #6 Skills → #11/#12 实战与多 Agent |
| 💤 按需回补 | #4 Memory 实现四件套（做会话型 agent 时它才会变成核心） |

> **为什么调整顺序**：MCP、Memory、Skills 这些都属于"**能力扩展**"——学会给 agent 加东西。而 #8 Evals 和 #10 上下文管理属于"**质量与边界**"——决定 agent 在真实负载下能不能用。前者容易上瘾，后者才拉开差距。

---

## 🔗 耦合原则

> 更新于 2026-09-12 · 本节解决的是"**怎么学才算数**"（学什么 ≠ 会用），下面的阶段划分管的是"学什么"

### 问题

"读完了 agent 的每个模块"和"用 agent 把事情做成"是两种能力，它们**不会自动互相转化**。

读完 `agent.py` 不会让你更会写 prompt；写完 10 个 eval case 也不会让你更懂 `_summarize_messages`。
除非中间加上一个动作：**让两者互相对质**。

### 原则

> **源码给的是假设（hypothesis），真实使用给的是证据（evidence）。
> 两者对质的那一刻，知识才变成能力。**

读代码得到的是"作者**当时为什么**这么写"的推测——它对不对、够不够，只有真实负载下跑过才知道。

### 三个耦合动作

| 动作 | 怎么做 | 你得到什么 |
|---|---|---|
| **① 预测 → 验证** | 读某模块**之前**先写下"我猜它会怎么处理 X"，再读代码对答案。**差的那部分才是收获** | 把被动阅读变成主动检验 |
| **② 用 Evals 当显微镜** | 针对一个内部机制写 case，**它坏掉时该 case 必须失败**。做不到，就说明还没理解这个机制 | 机制理解 + 质量护栏，一次拿两样 |
| **③ 改一个机制，看后果** | 改一处（把 `token_limit` 调小、给工具输出加截断），跑一遍，观察行为变化 | 从"我知道它这么写"到"我知道它**为什么必须**这么写" |

### 实例：本仓库已发生的一次耦合

- **假设**（来自文档）：[`_create_summary`](../mini_agent/agent.py#L262) 会把工具输出截断到 200 字符再喂给总结模型
- **证据**（来自代码 + 真实运行）：**没有截断**——你自己的总结示例里，2800 行技能内容原样进了 prompt
- **升级后的认知**：总结本身就是一次完整历史开销，"压缩"并不免费 → 引出 #10 的「**工具上下文预算**」

这一轮里**文档是错的，代码和运行结果是对的**。这就是为什么要跑，而不是只读。

### 什么不算数

- ❌ 读完文档 = 学会了（文档会过时，也可能本来就是错的）
- ❌ 代码跑通 = 会用（跑通的是作者的场景，不是你的）
- ❌ 记得概念名词 = 有能力（**说不清它在什么情况下会失败，就是没懂**）

---

## 阶段一：实践与验证（1-2周）

### 1. 运行并修改 Examples

**目标**：通过实际运行加深理解

**任务**：
- 依次运行 `examples/01_basic_tools.py` 到 `examples/06_tool_schema_demo.py`
- 修改每个示例，添加自己的功能（如：在 calculator.py 中添加新的数学函数）
- 观察工具调用、错误处理、多轮对话的实际效果

**验证标准**：
- ✅ 所有示例都能成功运行
- ✅ 理解每个工具的调用流程
- ✅ 能够修改示例并添加新功能

---

### 2. 构建自定义工具

**目标**：掌握工具开发

**任务**：
- 阅读 `mini_agent/tools/base.py` 理解 `BaseTool` 接口
- 创建 3 个自定义工具：
  - **简单工具**：如天气查询、时间转换
  - **有状态工具**：如任务列表管理
  - **复杂工具**：如数据库查询、API 调用
- 将工具集成到 agent 中测试

**示例项目**：
```python
# 天气查询工具
class WeatherTool(BaseTool):
    name = "get_weather"
    description = "获取指定城市的天气信息"
    
    def execute(self, city: str) -> dict:
        # 实现天气查询逻辑
        pass
```

**验证标准**：
- ✅ 理解 BaseTool 接口的设计
- ✅ 能够独立创建工具并集成
- ✅ 工具能够正确处理错误情况

---

### 3. 深入理解 Agent Loop

**目标**：掌握 agent 执行流程

**任务**：
- 在 `mini_agent/agent.py` 中添加详细的日志
- 追踪一次完整的执行：用户输入 → 思考 → 工具调用 → 响应
- 理解 `max_steps`、错误恢复、上下文管理的机制

**关键代码位置**：
- `agent.py:run()` - 主执行循环
- `agent.py:_process_tool_calls()` - 工具调用处理
- `agent.py:_handle_error()` - 错误恢复

**验证标准**：
- ✅ 能够画出 agent loop 的流程图
- ✅ 理解每个步骤的输入输出
- ✅ 知道如何调试 agent 执行问题

---

## 阶段二：高级功能探索（2-3周）

### 4. Memory 系统实战

> #### 📌 修订（2026-09-10）：本项降级为"按需"
>
> **决定**：暂不深入 Memory 的**实现**，保留**概念**。
>
> **理由**：
>
> 1. **概念和实现要分开。** "context vs 持久存储 / 检索如何进入 prompt / 什么值得存"是 agent 的通用概念——已通过 Lesson 07 和通读 `note_tool.py` 拿到。而下面列的向量搜索、优先级、过期、图谱，学的是**某个记忆后端的工程实现**，不是 agent 的通用概念。花两周接上 FAISS，主要学到的是 FAISS。
>
> 2. **对编码类 agent，自动记忆的边际收益本就低。** 仓库本身就是持久、共享、可 diff、可回滚的事实载体；再叠一套向量记忆等于给仓库做**有损的影子副本**，还要付同步漂移的代价。编码 agent 真正需要记住的是用户偏好这类**不在仓库里**的信息，而它因为量小、写错代价高，**人工策展的文件（CLAUDE.md / AGENTS.md）比自动提取更可靠**。`note_tool.py` 里"LLM 自己决定存什么"恰好是最不该自动化的那部分。
>
> 3. **"1000+ 条记忆"是个误导性指标。** 真正的难点不是数据量（1000 条对任何检索方式都很小），而是**词汇不匹配**——用户不会用你存的时候的那些词来提问。而比检索更难的**矛盾消解**（先说"我在北京"、后说"搬到上海了"，两条都留着，检索可能召回错的那条）和**跨会话整合**，本项的四件套一个都没覆盖。
>
> **保留的认知**：Memory 的概念会在 **#10 上下文管理** 以真正重要的形态重新出现。
>
> **什么时候回来做**：将来若要构建**会话型 / 陪伴型 agent**（多轮跨会话、无固定产物、一个主题散落在多个会话里），本项会从"可跳过"变成"核心"。

**目标**：构建持久化记忆系统

**任务**：
- 研究 `mini_agent/tools/note_tool.py`
- 扩展 Memory 功能：
  - **向量搜索**：使用 embeddings 实现语义搜索
  - **优先级管理**：重要记忆优先召回
  - **过期机制**：自动清理过时信息
  - **知识图谱**：构建关联记忆网络
- 测试跨会话的记忆效果

**技术栈**：
- 向量数据库：FAISS / ChromaDB
- Embedding 模型：OpenAI / Sentence Transformers
- 图数据库：NetworkX / Neo4j

**验证标准**：
- ✅ 实现语义搜索功能
- ✅ 记忆能够跨会话持久化
- ✅ 能够处理大量记忆（1000+ 条）

---

### 5. MCP 工具集成

> #### 📌 状态（2026-09-10）：已完成，标记为"够用"
>
> **已达成的认知**（可迁移，不是管道细节）：
> - **工具抽象**：`MCPTool` 继承 `Tool`，远程工具与本地工具在 agent 眼里无区别
> - **工具集是运行时可变的**，不是构造 agent 时静态确定的
> - **长驻进程 + 分层超时**的生命周期模型（连接建立后活到进程结束）
>
> **未碰、标记"按需再查"**：
> - `resources` / `prompts` 两个原语。MCP 的 tools / resources / prompts = **模型控制 / 应用控制 / 用户控制**，这个三分是协议设计的骨架，目前只用了一格
> - `sampling` / `elicitation` / `roots`。协议是**双向**的，服务端可反向调用客户端——这才是 MCP 不只是"工具注册表"的地方
> - `notifications/tools/list_changed`。[`mcp_loader.py:208`](../mini_agent/tools/mcp_loader.py#L208) 只在 connect 时取一次工具快照，服务端运行时增删工具，agent 看不见
>
> **待自查的验证标准**：原计划要求"成功集成至少 3 个 MCP 服务器"。目前已知的是 1 个（自己写的）。这条是否达标请自行核对。
>
> #### ➕ 补充：MCP 与上下文预算（通向 #10）
>
> 加载 MCP server 的真实代价不在协议，在 **context**。每个 server 的工具 schema 全量进 system prompt，而 [`mcp_loader.py:414`](../mini_agent/tools/mcp_loader.py#L414) 是 `all_tools.extend(...)`——**没有去重、没有命名空间、没有裁剪**。真连上 GitHub + Slack + Database 之后，几十上百个工具的描述会在用户说第一句话之前就吃掉一大块窗口。
>
> 注意这件事的性质：**它不是 MCP 问题，是上下文管理问题**，MCP 只是把它放大了。这是 #10 的一个具体入口。

**目标**：掌握外部工具集成

**任务**：
- 阅读 `mini_agent/tools/mcp_loader.py`
- 集成更多 MCP 服务器：
  - GitHub - 代码仓库操作
  - Slack - 消息发送
  - Database - 数据库查询
- 创建自己的 MCP 服务器
- 理解工具发现、加载、调用的完整流程

**参考资源**：
- [MCP 协议文档](https://github.com/modelcontextprotocol/protocol)
- [MCP Servers 仓库](https://github.com/modelcontextprotocol/servers)

**验证标准**：
- ✅ 成功集成至少 3 个 MCP 服务器
- ✅ 创建一个自定义 MCP 服务器
- ✅ 理解 MCP 的通信协议

---

### 6. Skills 系统研究

**目标**：理解复杂技能的组织方式

**任务**：
- 研究 `mini_agent/skills/` 下的现有技能
- 选择一个技能（如 `document-skills`）深入分析其架构
- 创建自己的 Skill：
  - 定义 skill manifest
  - 实现多步骤工作流
  - 添加依赖和配置管理

**Skill 结构**：
```
my-skill/
├── skill.yaml          # Skill 定义
├── README.md           # 使用文档
├── scripts/            # 执行脚本
│   ├── __init__.py
│   └── main.py
└── tests/              # 测试用例
    └── test_skill.py
```

**验证标准**：
- ✅ 理解 Claude Skills 的设计理念
- ✅ 创建一个可复用的 Skill
- ✅ Skill 能够被 agent 正确调用

---

## 阶段三：系统优化与生产化（2-4周）

### 7. Planning 系统优化

**目标**：实现更智能的规划

**任务**：
- 研究 Lesson 08 (Planning) 和 Lesson 10 (AoT)
- 实现依赖图的可视化
- 添加并行执行能力
- 实现动态规划调整（根据执行结果修改计划）

**核心概念**：
- **原子操作 (Atomic Actions)**：不可再分的最小任务单元
- **依赖图 (Dependency Graph)**：任务之间的依赖关系
- **并行执行**：独立任务同时执行
- **动态调整**：根据执行反馈修改计划

**实现要点**：
```python
# 依赖图示例
plan = {
    "actions": [
        {"id": "A", "deps": [], "action": "读取文件"},
        {"id": "B", "deps": ["A"], "action": "处理数据"},
        {"id": "C", "deps": ["A"], "action": "生成摘要"},
        {"id": "D", "deps": ["B", "C"], "action": "生成报告"}
    ]
}
# A 可以立即执行
# B 和 C 可以在 A 完成后并行执行
# D 必须等待 B 和 C 都完成
```

**验证标准**：
- ✅ 能够生成正确的依赖图
- ✅ 实现并行执行，提升效率
- ✅ 能够处理执行失败的情况

---

### 8. 评估系统（Evals）

> #### 📌 修订（2026-09-10）：本项提前，建议作为下一步
>
> **为什么提前**：Memory / MCP / Skills 都属于"**给 agent 加能力**"，而 Evals 决定"**加完之后变好了还是变坏了**"。没有基线，后面所有的"优化"都只是感觉。而且它几乎是所有人都会跳过、回报却最高的一环。
>
> **为什么现在成本很低**：你手上已经有 [`tests/`](../tests/)（含 `test_agent.py`、`test_session_integration.py`）、稳定的 agent loop、真实工具集。**不必从零搭框架**，先做最朴素的一层就够：
>
> 1. 用固定任务集跑 agent，**断言工具选择是否正确**——不是断言最终文本（文本断言又脆又难写）
> 2. 记录每例的**步数与 token 消耗**，作为效率基线
> 3. 注入失败场景（工具报错、超时、返回空），看**错误恢复**是否有效
> 4. 每次改动前后重跑同一套，看指标涨跌
>
> **先有基线，"优化"才有方向。** 这也是 #9 Telemetry 的地基——Evals 是离线跑，Telemetry 是在线收，两者量的是同一批指标。
>
> **一个容易踩的坑**：评测用例别只挑"能成功的任务"。真正暴露问题的是边界——工具该用而没用、不该用却用了、一步能做完却绕了五步。

**目标**：建立质量保证机制

**任务**：
- 研究 Lesson 11 (Evals)
- 创建测试用例集：
  - **工具调用准确性**：工具选择是否正确
  - **多步任务完成率**：复杂任务的完成情况
  - **错误恢复能力**：遇到错误时的处理
  - **输出质量**：生成内容的质量评估
- 实现自动化评估流水线
- 添加性能指标监控

**评估维度**：
1. **正确性 (Correctness)**：任务是否正确完成
2. **效率 (Efficiency)**：使用的步骤数和时间
3. **鲁棒性 (Robustness)**：处理异常的能力
4. **可解释性 (Interpretability)**：决策过程是否清晰

**测试框架**：
```python
class AgentEvaluation:
    def __init__(self, agent, test_cases):
        self.agent = agent
        self.test_cases = test_cases
    
    def run_evals(self):
        results = []
        for case in self.test_cases:
            result = self.evaluate_case(case)
            results.append(result)
        return self.generate_report(results)
```

**验证标准**：
- ✅ 创建至少 20 个测试用例
- ✅ 实现自动化评估流程
- ✅ 生成可视化的评估报告

---

### 9. 遥测与监控

**目标**：生产环境可观测性

**任务**：
- 研究 Lesson 12 (Telemetry)
- 集成日志系统（结构化日志）
- 添加性能追踪：
  - Token 使用量统计
  - 响应时间监控
  - 工具调用频率
  - 错误率追踪
- 实现错误告警机制
- 可视化 agent 执行流程

**监控指标**：
- **性能指标**：
  - 平均响应时间
  - Token 消耗率
  - 并发请求数
- **质量指标**：
  - 任务完成率
  - 工具调用成功率
  - 用户满意度
- **业务指标**：
  - 日活跃用户
  - 任务类型分布
  - 高频使用场景

**技术栈**：
- 日志：structlog / loguru
- 监控：Prometheus + Grafana
- 追踪：OpenTelemetry
- 可视化：Streamlit / Dash

**验证标准**：
- ✅ 实现完整的日志记录
- ✅ 搭建监控仪表板
- ✅ 能够快速定位问题

---

### 10. 上下文管理优化

> #### 📌 修订（2026-09-10）：认知部分已完成，本项转入"实现"
>
> **已完成**：现有机制的完整认知——见 [Agent上下文管理机制详解.md](./Agent上下文管理机制详解.md)（五层机制：累积 / 配对 / 监控 / 压缩 / 元认知）。那份文档描述的是 mini-agent **现有**做法，作为地基足够扎实。
>
> **因此下面「策略」清单要重新划分**——原来四条，前两条你已经在认知层面拿下了：
>
> | 原策略 | 状态 |
> |---|---|
> | 1. 摘要压缩 | ✅ 已理解（`_summarize_messages()`） |
> | 2. 对话摘要 | ✅ 已理解（`_create_summary()`） |
> | 3. 重要性评分 | ⬜ 待实现 |
> | 4. 分层记忆 | ⬜ 待实现 |
> | 5. 检索增强 | ⬜ 待实现 |
> | **6. 工具上下文预算（新增）** | ⬜ 待实现——见 #5 补充说明 |
>
> #### 从"懂"到"做"：四个具体的切入点
>
> 读懂 `_summarize_messages()` 是理解，能设计出**比它更好的**策略才是掌握。以下都是从现有实现的边界里长出来的：
>
> **① 压缩粒度是"整轮"，没有分诊。** 现在的逻辑是按 user 边界切轮次，轮内所有消息一视同仁地压成一条摘要（[`agent.py:225-248`](../mini_agent/agent.py#L225-L248)）。但轮内的信息价值差别很大——文件路径、报错信息、决策结论值得留全文，中间的探索过程可以只留摘要。**在压缩前加一层"分诊"**，这正是原策略 2（重要性评分）的具体化。
>
> **② 工具输出是"先全量进 context，再整体压缩"。** 大输出（比如你的雪球 server 一次返回上百只股票）会先进 context，等下一轮检查才发现超限。中间那一轮已经付了 token 成本。**在工具结果进入 messages 之前就做截断/摘要**，是更早的一道闸——这同时也是 #5 里"工具上下文预算"的落点。
>
> **③ `_create_summary` 自己有溢出风险。** 它把整轮的工具输出**原样**拼进总结 prompt（[`agent.py:285-286`](../mini_agent/agent.py#L285-L286)，只追加了一个字面量 `"..."`，内容没有截断）。如果单轮内容本身就超限，**总结调用自己会爆**——本该救火的那一步成了起火点。需要的是总结前的预截断或分块。这是个明确可做的改进。
>
> **④ 压缩没有保真度校验。** 现在压完只打印 token 降幅（`✓ Summary completed, local tokens: X → Y`）。但**token 降幅是虚荣指标**——压得越狠当然降得越多。真正要量的是"压缩后关于已压缩轮次的问题还答不答得上"。这是 #8 Evals 和本项的交汇点，也是本项最值得先做的一件。
>
> **验证标准（修订）**：
> - ✅ 支持 100+ 轮对话（原标准）
> - ✅ Token 使用保持在合理范围（原标准）
> - ⚠️ "关键信息不丢失" → 需**量化**：做压缩前/后的**信息保留率**对比，不能只看 token 降幅
> - ➕ **单轮超大工具输出**也需覆盖（原标准只测了轮数，没测单轮体量）

**目标**：处理长对话和大规模任务

**任务**：
- 实现智能上下文压缩
- 添加对话摘要功能
- 实现上下文窗口滑动策略
- 测试极限场景（100+ 轮对话）

**策略**：
1. **摘要压缩**：定期总结历史对话
2. **重要性评分**：保留关键信息，丢弃冗余
3. **分层记忆**：短期 + 长期记忆
4. **检索增强**：按需加载相关上下文

**实现示例**：
```python
class ContextManager:
    def __init__(self, max_tokens=100000):
        self.max_tokens = max_tokens
        self.messages = []
        self.summary = ""
    
    def add_message(self, message):
        self.messages.append(message)
        if self.get_token_count() > self.max_tokens:
            self.compress()
    
    def compress(self):
        # 摘要旧消息
        old_messages = self.messages[:10]
        self.summary += self.summarize(old_messages)
        self.messages = self.messages[10:]
```

**验证标准**：
- ✅ 支持 100+ 轮对话
- ✅ Token 使用保持在合理范围
- ✅ 关键信息不丢失

---

## 阶段四：实战项目（持续）

### 11. 构建垂直领域 Agent

选择一个方向，构建完整的应用：

#### 选项 A：代码助手

**功能**：
- 代码审查 agent
- 重构建议 agent  
- 文档生成 agent
- 测试用例生成

**技术要点**：
- AST 解析
- 静态代码分析
- Git 集成
- IDE 插件开发

---

#### 选项 B：数据分析 Agent

**功能**：
- 自动化数据清洗
- 统计分析和可视化
- 报告自动生成
- 异常检测

**技术要点**：
- Pandas / Polars
- Matplotlib / Plotly
- 统计建模
- 自然语言生成

---

#### 选项 C：内容创作 Agent

**功能**：
- 多平台内容生成
- SEO 优化建议
- 图文自动排版
- 内容质量评估

**技术要点**：
- 文本生成优化
- 图像处理
- HTML/CSS 生成
- 内容分发

---

#### 选项 D：DevOps Agent

**功能**：
- 自动化部署
- 日志分析和告警
- 故障诊断和恢复
- 性能优化建议

**技术要点**：
- CI/CD 集成
- 日志解析
- 监控系统
- 自动化脚本

---

### 12. 多 Agent 协作系统

**目标**：构建 agent 网络

**任务**：
- 实现 agent 间通信协议
- 构建任务分发机制
- 实现协作规划
- 添加冲突解决策略

**架构设计**：
```
Coordinator Agent (协调者)
    ↓
    ├── Specialist Agent 1 (专家1)
    ├── Specialist Agent 2 (专家2)
    └── Specialist Agent 3 (专家3)
```

**协作模式**：
1. **Pipeline**：串行协作，输出传递
2. **Parallel**：并行协作，结果聚合
3. **Debate**：多 agent 辩论，达成共识
4. **Hierarchical**：层次化管理

**实现要点**：
```python
class MultiAgentSystem:
    def __init__(self):
        self.coordinator = CoordinatorAgent()
        self.specialists = [
            CodeAgent(),
            DataAgent(),
            WritingAgent()
        ]
    
    async def execute_task(self, task):
        # 1. 协调者分析任务
        plan = await self.coordinator.plan(task)
        
        # 2. 分配给专家
        results = []
        for subtask in plan.subtasks:
            agent = self.select_agent(subtask)
            result = await agent.execute(subtask)
            results.append(result)
        
        # 3. 聚合结果
        final_result = await self.coordinator.aggregate(results)
        return final_result
```

**验证标准**：
- ✅ 实现至少 2 种协作模式
- ✅ 能够处理复杂的多步任务
- ✅ Agent 间能够有效通信

---

## 学习资源与工具

### 📖 推荐阅读

#### 论文：
1. **ReAct: Synergizing Reasoning and Acting in Language Models**
   - 链接：https://arxiv.org/abs/2210.03629
   - 核心：推理和行动的结合

2. **Chain-of-Thought Prompting Elicits Reasoning in LLMs**
   - 链接：https://arxiv.org/abs/2201.11903
   - 核心：思维链提示

3. **Tree of Thoughts: Deliberate Problem Solving with LLMs**
   - 链接：https://arxiv.org/abs/2305.10601
   - 核心：树状思维结构

4. **Reflexion: Language Agents with Verbal Reinforcement Learning**
   - 链接：https://arxiv.org/abs/2303.11366
   - 核心：自我反思和改进

#### 开源项目：
- **LangChain**：Agent 框架
- **AutoGPT**：自主 Agent 实现
- **BabyAGI**：任务驱动的自主 Agent
- **Claude Skills**：高质量 Skill 示例
- **MCP Servers**：标准工具集成

---

### 🛠️ 调试技巧

#### 1. 详细日志
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### 2. 断点调试
```python
# 在关键位置添加断点
import pdb; pdb.set_trace()
```

#### 3. 可视化思考过程
```python
def visualize_thinking(agent):
    for step in agent.steps:
        print(f"Step {step.number}:")
        print(f"  Thought: {step.thought}")
        print(f"  Action: {step.action}")
        print(f"  Result: {step.result}")
```

#### 4. 记录所有交互
```python
class LoggingLLMClient:
    def __init__(self, client):
        self.client = client
        self.logs = []
    
    async def chat(self, messages):
        self.logs.append({"input": messages})
        response = await self.client.chat(messages)
        self.logs.append({"output": response})
        return response
```

---

### 📊 每周检查点

建议每周回答以下问题：

1. ✅ **理解检验**：我能用自己的话解释这周学习的概念吗？
2. ✅ **实践能力**：我能独立实现相关功能吗？
3. ✅ **问题记录**：我遇到了什么问题？如何解决的？
4. ✅ **目标设定**：下周的学习目标是什么？

**学习日志模板**：
```markdown
# Week X 学习日志

## 学习内容
- 完成了...
- 阅读了...
- 实现了...

## 收获
- 理解了...
- 掌握了...

## 遇到的问题
- 问题1：...
  - 解决方案：...
- 问题2：...
  - 解决方案：...

## 下周计划
- [ ] 任务1
- [ ] 任务2
- [ ] 任务3
```

---

## 学习建议

### 🎯 学习原则

> 最核心的一条是 [**耦合原则**](#-耦合原则)——源码给假设，真实使用给证据，两者对质才算学会。下面几条是它的展开。

1. **理论与实践结合**
   - 先理解概念，再动手实现
   - 不要只看代码，要运行和修改

2. **循序渐进**
   - 不要跳步，扎实掌握每个阶段
   - 遇到困难回到基础重新理解

3. **主动思考**
   - 问"为什么这样设计？"
   - 思考"如果我来做会怎么做？"

4. **记录总结**
   - 写学习笔记
   - 记录遇到的问题和解决方案
   - 分享你的理解和心得

5. **寻求反馈**
   - 在社区提问
   - 与其他学习者交流
   - 参与开源贡献

---

### 🚀 快速开始

**现在就开始！从这里开始你的第一步：**

```bash
# 1. 运行第一个示例
cd Mini-Agent
uv run python examples/01_basic_tools.py

# 2. 修改示例，添加你自己的功能
# 3. 观察输出，理解执行流程
# 4. 尝试创建你的第一个自定义工具
```

**第一周目标**：
- ✅ 运行所有 examples
- ✅ 创建 1-2 个自定义工具
- ✅ 理解 agent loop 的基本流程

---

## 学习路径图

```mermaid
graph TD
    A[学习 Lessons] --> B[运行 Examples]
    B --> C[创建自定义工具]
    C --> D[深入 Agent Loop]
    D --> F[MCP 集成]
    F --> E2[上下文管理]
    E2 --> I[Evals 评估]
    I --> H[Planning & AoT]
    H --> J[Telemetry 监控]
    J --> G[Skills 开发]
    G --> K[实战项目]
    K --> L[多 Agent 系统]
    E[Memory 系统<br/>按需回补] -.-> E2

    classDef done fill:#d4edda,stroke:#28a745,color:#155724
    classDef next fill:#fff3cd,stroke:#ffc107,color:#856404
    classDef later fill:#e2e3e5,stroke:#6c757d,color:#383d41
    class A,B,C,D,F done
    class E2,I next
    class H,J,G,K,L later
    class E later
```

> 🟩 已完成　🟨 下一步　⬜ 之后　┈> 按需回补
>
> 与原图的两处差异：**Memory 移出主线**（降为按需回补，虚线），**Evals 提前到上下文管理之后**（原图排在 Planning 和 Telemetry 之后）。

---

## 参考资源

### 官方文档
- [Mini Agent README](../README.md)
- [开发指南](./DEVELOPMENT_GUIDE.md)
- [生产部署指南](./PRODUCTION_GUIDE.md)
- [Lessons 目录](./lessons/)

### 社区
- [GitHub Issues](https://github.com/MiniMax-AI/Mini-Agent/issues)
- [Discussions](https://github.com/MiniMax-AI/Mini-Agent/discussions)
- MiniMax 官方微信群

### 相关项目
- [Claude Skills](https://github.com/anthropics/skills)
- [MCP Protocol](https://github.com/modelcontextprotocol/protocol)
- [MCP Servers](https://github.com/modelcontextprotocol/servers)

---

## 贡献指南

在学习过程中，你可以：
- 提交 bug 报告
- 改进文档
- 分享学习笔记
- 贡献代码示例
- 创建新的 Skills

**欢迎在学习过程中为社区做出贡献！**

---

**祝学习愉快！🎉**

如有问题，欢迎在 GitHub Issues 中提问。
