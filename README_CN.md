# Mini Agent（学习分支）

[English](./README.md) | 中文

## 关于本仓库

本项目是 [MiniMax-AI/Mini-Agent](https://github.com/MiniMax-AI/Mini-Agent) 的个人学习 fork——上游项目是一个展示如何基于 MiniMax M2.5 模型（Anthropic 兼容 API）构建 Agent 的极简而专业的示例工程。

`docs/lessons/` 目录下的课程笔记拷贝自 [AI Product from Scratch](https://github.com/pguso/ai-product-from-scratch) 项目，该项目从第一性原理讲解 Agent（LLM 对话 → 系统提示词 → 结构化输出 → 工具 → Agent 循环 → 记忆 → 规划 → 评估 → 遥测）。

**本仓库的作用是我个人结合两个项目学习 AI Agent**：一边阅读课程理解概念，一边在真实的 Mini-Agent 代码库中动手实现和扩展同样的思想。

## 我做了哪些修改（相对上游 `main` 分支）

所有修改都在当前分支，是学习过程中的动手练习：

### 1. 评估框架（`evals/`）
按照 evals 课程实现的一套完整 Agent 评估体系：
- `evals/golden_datasets.py` — 覆盖结构化输出、工具调用、决策判断、记忆循环，以及**真实端到端 Agent 任务**（Agent 在隔离的 workspace 中真实执行，再校验结果）的黄金数据集。
- `evals/evals.py` — 评估数据模型与结果/报告类型。
- `evals/run.py` — 评估运行器：执行各测试套件、逐用例打分、统计**效率指标**（步数、token 数、耗时），并输出汇总报告。

### 2. 流式输出与实时展示
- `mini_agent/llm/openai_client.py` / `anthropic_client.py` — 两个客户端都支持流式请求，并改进了超时处理：读超时现在衡量的是**chunk 之间的间隔**，而不是整个请求时长。
- `mini_agent/stream_display.py` — CLI 中的实时流式展示条：在终端原地渲染 LLM 输出（小窗口滚动），每次流结束后自动清除。
- 通过 `stream_callback` / `stream_end_callback` 回调接入 CLI（`mini_agent/cli.py`）和 `LLMClient` 基类。

### 3. LLM 请求超时配置
- 超时时间可在 `config.yaml` 中配置（`timeout: 600.0` 秒，默认 600），并贯穿 `config.py`、两个 LLM 客户端和 `llm_wrapper.py`。
- 超时后按已有的 retry 配置自动重试。

### 4. 终端 Markdown 渲染
- `mini_agent/utils/markdown_renderer.py` — Agent 回复在 CLI 中以 Markdown 渲染，而不是原始文本。
- `tests/test_markdown_renderer.py` — 渲染器单元测试。

### 5. 新增工具
- `mini_agent/tools/calculator_tool.py` — 一个简单的计算器工具，作为"编写第一个工具"的练习。

### 6. 记忆可观测性
- `mini_agent/memory_logger.py` — 记忆工具使用的可观测性日志，并把记忆策略注入贯穿到 `agent.py`、`cli.py` 和 `note_tool.py`。
- `docs/notes/agent_memory_notes.md` / `docs/notes/memory_observability_notes.md` — 关于记忆结构与访问机制、可观测性设计的学习笔记。
- 另有一篇 MCP server-memory 知识图谱及其数据模型的详解文档。

### 7. 多 Agent 系统（`mini_agent/multi_agent/`）
- **辩论模式** — 编排器 + 多头/空头/裁判三种角色（`orchestrator.py`、`modes/debate.py`、`protocol.py`、`registry.py`），已接入 CLI。
- **插件子 Agent 与 `dispatch_agent` 工具** — 自动发现 `mini_agent/plugins/` 下的插件；解析其 Claude Code 格式的 Agent 定义文件（frontmatter）生成子 Agent，每个子 Agent 拥有基于技能的独立工具集。`plugin_loader.py` 和 `dispatch_agent` 已接入 CLI 启动流程。
- **Spawn 门控** — 子 Agent 工具集在构造 dispatch 时从定义文件 frontmatter 解析（`resolve_tools` + `MAX_SPAWN_DEPTH`）；串行 spawn 链有深度限制，dispatch 枚举自排除（子 Agent 不能再派发自己）；未解析的工具按 Agent 逐一告警，而不是整体忽略。覆盖测试：`tests/test_dispatch_tool.py`、`tests/test_plugin_loader.py` 及角色矩阵加载回归测试。
- **十个示例插件**（`mini_agent/plugins/` 下的 earnings-reviewer、gl-reconciler、kyc-screener、market-researcher、valuation-reviewer 等），并配有 GL 对账流水线的本地演示数据（`examples/gl-recon-demo/`）。

### 8. 设计文档
- `docs/superpowers/` — 串行流水线 + spawn 工具限制的设计规格与实施计划（`specs/`、`plans/`）。

### 9. 环境
- 项目级固定 PyPI 清华镜像源（适配我的网络环境），并重新 lock 了 `uv.lock`。

### 10. 文档
- `docs/lessons/` — 来自 AI Product from Scratch 的课程笔记（部分加了我自己的学习总结），另有 Skills 机制详解文档和学习计划笔记。

## 基础项目提供的能力（上游功能）

- ✅ 完整的 Agent 执行循环，内置文件系统和 Shell 基础工具集
- ✅ 通过 Session Note 工具实现跨会话的持久记忆
- ✅ 智能上下文管理——历史超限自动摘要，支持长任务
- ✅ Claude Skills 集成（文档、设计、测试、开发等专业技能）
- ✅ MCP 工具集成（知识图谱、网络搜索）
- ✅ 完整日志：记录每次请求、响应和工具执行，便于调试

## 快速开始

### 1. 获取 API Key

MiniMax 分国内和国际两个平台：

| 版本     | 平台                                                           | API Base                   |
| -------- | -------------------------------------------------------------- | -------------------------- |
| **国际** | [https://platform.minimax.io](https://platform.minimax.io)     | `https://api.minimax.io`   |
| **国内** | [https://platform.minimaxi.com](https://platform.minimaxi.com) | `https://api.minimaxi.com` |

注册后在 **账号管理 > API Keys** 中创建密钥。

### 2. 安装与配置

需要 [uv](https://docs.astral.sh/uv/)。克隆本仓库并初始化：

```bash
# 安装依赖
uv sync

# 复制示例配置并填入 API Key
cp mini_agent/config/config-example.yaml mini_agent/config/config.yaml
```

编辑 `mini_agent/config/config.yaml`：

```yaml
api_key: "YOUR_API_KEY_HERE"
api_base: "https://api.minimaxi.com"   # 国内；国际填 https://api.minimax.io
model: "MiniMax-M2.5"
timeout: 600.0                          # 单次 LLM 请求超时（秒）
```

### 3. 运行

```bash
# 交互式 CLI
uv run python -m mini_agent.cli

# 或运行一次性任务（脚本见 examples/）
uv run python examples/basic_usage.py
```

### 4. 运行评估

```bash
uv run python -m evals.run            # 运行默认测试套件
uv run python -m evals.run --help     # 查看 suite/full/only 参数
```

### 5. 测试

```bash
uv run pytest tests/
```

## 学习路径（`docs/lessons/`）

1. [基础 LLM 对话](docs/lessons/01_basic_llm_chat.md)
2. [系统提示词](docs/lessons/02_system_prompt.md)
3. [结构化输出](docs/lessons/03_structured_output.md)
4. [决策判断](docs/lessons/04_decision_making.md)
5. [工具](docs/lessons/05_tools.md)
6. [Agent 循环](docs/lessons/06_agent_loop.md)
7. [记忆](docs/lessons/07_memory.md)
8. [规划](docs/lessons/08_planning.md)
9. [原子动作](docs/lessons/09_atomic_actions.md)
10. [思维原子](docs/lessons/10_atom_of_thought.md)
11. [评估](docs/lessons/11_evals.md)
12. [遥测](docs/lessons/12_telemetry.md)

## 许可证

MIT — 见 [LICENSE](LICENSE)。原始代码归 MiniMax-AI 所有；课程笔记来自 AI Product from Scratch。
