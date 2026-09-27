# Mini Agent (Learning Fork)

English | [中文](./README_CN.md)

## About This Repository

This project is a personal learning fork of [MiniMax-AI/Mini-Agent](https://github.com/MiniMax-AI/Mini-Agent) — a minimal yet professional demo project showcasing best practices for building agents with the MiniMax M2.5 model via an Anthropic-compatible API.

The `docs/lessons/` directory contains lesson notes copied from the [AI Product from Scratch](https://github.com/pguso/ai-product-from-scratch) project, which teaches agent concepts from first principles (LLM chat → system prompts → structured output → tools → agent loop → memory → planning → evals → telemetry).

**The purpose of this repository is my personal study of AI Agents**, combining the two projects: reading the lessons to understand the concepts, then implementing and extending the same ideas inside the real Mini-Agent codebase.

## What I Changed (vs. upstream `main`)

All changes are on this branch, made as hands-on exercises while learning:

### 1. Evaluation Framework (`evals/`)
A full agent evaluation suite, following the "evals" lesson:
- `evals/golden_datasets.py` — golden datasets covering structured output, tool calls, decision making, memory cycles, and **real end-to-end agent tasks** (the agent actually runs in a sandboxed workspace and the result is checked).
- `evals/evals.py` — evaluation data models and result/report types.
- `evals/run.py` — the runner: executes each suite, scores cases, tracks **efficiency metrics** (steps, tokens, wall time), and prints a summary report.

### 2. Streaming & Live Output
- `mini_agent/llm/openai_client.py` / `anthropic_client.py` — streaming support for both clients, with improved timeout handling: the read timeout now measures the gap **between chunks** instead of the whole request.
- `mini_agent/stream_display.py` — a live streaming strip in the CLI that renders LLM output in place (a small scrolling window), cleared automatically when each stream ends.
- Integrated into the CLI (`mini_agent/cli.py`) and the `LLMClient` base class via `stream_callback` / `stream_end_callback` hooks.

### 3. LLM Request Timeout Configuration
- Timeout is now configurable in `config.yaml` (`timeout: 600.0` seconds, default 600) and threaded through `config.py`, both LLM clients, and `llm_wrapper.py`.
- On timeout the request is retried per the existing retry config.

### 4. Markdown Rendering in the Terminal
- `mini_agent/utils/markdown_renderer.py` — renders agent replies as Markdown in the CLI instead of raw text.
- `tests/test_markdown_renderer.py` — unit tests for the renderer.

### 5. New Tool
- `mini_agent/tools/calculator_tool.py` — a simple calculator tool, added as a "write your first tool" exercise.

### 6. Environment
- Project-level PyPI mirror (Tsinghua) pinned for reproducible installs in my network environment, with `uv.lock` re-locked.

### 7. Documentation
- `docs/lessons/` — lesson notes from AI Product from Scratch (some annotated with my own study summaries), plus a skills-mechanism deep-dive doc and learning-plan notes.

## What the Base Project Provides (upstream features)

- ✅ Full agent execution loop with a basic toolset for file system and shell operations
- ✅ Persistent memory via a Session Note tool, retained across sessions
- ✅ Intelligent context management — auto-summarizes history up to a configurable token limit
- ✅ Claude Skills integration (professional skills for documents, design, testing, development)
- ✅ MCP tool integration (knowledge graph, web search)
- ✅ Comprehensive logging of every request, response, and tool execution

## Quick Start

### 1. Get an API Key

MiniMax provides global and China platforms:

| Version    | Platform                                                       | API Base                   |
| ---------- | -------------------------------------------------------------- | -------------------------- |
| **Global** | [https://platform.minimax.io](https://platform.minimax.io)     | `https://api.minimax.io`   |
| **China**  | [https://platform.minimaxi.com](https://platform.minimaxi.com) | `https://api.minimaxi.com` |

Register, then go to **Account Management > API Keys** and create a key.

### 2. Install & Configure

Requires [uv](https://docs.astral.sh/uv/). Clone this repo and set up:

```bash
# Install dependencies
uv sync

# Copy the example config and fill in your API key
cp mini_agent/config/config-example.yaml mini_agent/config/config.yaml
```

Edit `mini_agent/config/config.yaml`:

```yaml
api_key: "YOUR_API_KEY_HERE"
api_base: "https://api.minimax.io"   # or https://api.minimaxi.com (China)
model: "MiniMax-M2.5"
timeout: 600.0                        # per-request LLM timeout (seconds)
```

### 3. Run

```bash
# Interactive CLI
uv run python -m mini_agent.cli

# Or run a one-shot task (see examples/ for scripts)
uv run python examples/basic_usage.py
```

#### Global Install (optional)

The package already defines a `mini-agent` console script in `pyproject.toml`.
To make the command available globally (from any directory):

```bash
uv pip install -e .          # uses the Tsinghua mirror pinned in pyproject.toml
mini-agent --help            # now works from any directory
mini-agent -w ./my-ws -t "do a task"
```

Note: on Windows, make sure the venv's `Scripts` directory is on your `PATH`
(e.g. `E:\ai-agents\Mini-Agent\.venv\Scripts`). If you prefer not to touch
PATH, `uv run mini-agent --help` from the repo root works too.

### 4. Run the Evals

```bash
uv run python -m evals.run            # run default suites
uv run python -m evals.run --help     # see suite/full/only options
```

### 5. Tests

```bash
uv run pytest tests/
```

## Learning Path (`docs/lessons/`)

1. [Basic LLM Chat](docs/lessons/01_basic_llm_chat.md)
2. [System Prompt](docs/lessons/02_system_prompt.md)
3. [Structured Output](docs/lessons/03_structured_output.md)
4. [Decision Making](docs/lessons/04_decision_making.md)
5. [Tools](docs/lessons/05_tools.md)
6. [Agent Loop](docs/lessons/06_agent_loop.md)
7. [Memory](docs/lessons/07_memory.md)
8. [Planning](docs/lessons/08_planning.md)
9. [Atomic Actions](docs/lessons/09_atomic_actions.md)
10. [Atom of Thought](docs/lessons/10_atom_of_thought.md)
11. [Evals](docs/lessons/11_evals.md)
12. [Telemetry](docs/lessons/12_telemetry.md)

## License

MIT — see [LICENSE](LICENSE). Original work by MiniMax-AI; lesson notes from AI Product from Scratch.
