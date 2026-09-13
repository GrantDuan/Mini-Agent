# Mini-Agent Skills 机制总结

> 基于 `mini_agent/tools/skill_loader.py`、`skill_tool.py`、`cli.py` 的源码分析。

## 1. 核心设计：三级渐进式披露（Progressive Disclosure）

Skills 的全部成本模型都围绕一个原则：**只把当前需要的内容送进 LLM 上下文**。

| 级别 | 内容 | 何时进入上下文 | Token 成本 |
|---|---|---|---|
| Level 1 | skill 名称 + 一句描述 | 启动时注入 system prompt | 每个 skill 一行，常驻 |
| Level 2 | SKILL.md 完整正文 | LLM 调 `get_skill(skill_name)` 时 | 按需，一次 |
| Level 3 | 参考文档、脚本、资源 | LLM 调 `read_file` / bash 时 | 按需，可能多次 |

例：`pdf` skill 的 `reference.md` 有几千行，不需要它的任务全程只付一行描述的代价。

## 2. 初始化阶段的数据流

```
启动 (cli.py)
  │
  ├─ ① 定位 skills 目录（优先级搜索，取第一个存在的）
  │     ./skills → ./mini_agent/skills → site-packages/mini_agent/skills
  │
  ├─ ② SkillLoader.discover_skills()
  │     rglob("SKILL.md") 递归扫描 → 逐个 load_skill()
  │     ├─ 正则切分 YAML frontmatter（^---\n(.*?)\n---\n(.*)$）
  │     ├─ yaml.safe_load 解析，校验必填字段 name / description
  │     ├─ _process_skill_paths()：正文相对路径 → 绝对路径（见 §3）
  │     └─ 存入 loaded_skills[name] 字典（内容已在内存，但未进 prompt）
  │
  ├─ ③ 注册 get_skill 工具（唯一的 skill 相关 tool）
  │
  └─ ④ get_skills_metadata_prompt() 生成元数据清单
        → 替换 system_prompt.md 中的 {SKILLS_METADATA} 占位符
```

注意：**"加载所有 skills"发生在启动阶段**（磁盘扫描 + YAML 解析），但 token 成本延迟到真正使用时才付出。

## 3. 路径重写（`_process_skill_paths`）

启动时用三个正则把 SKILL.md 正文里的相对引用改写为绝对路径，让 Agent 在任意工作目录都能找到资源：

| 模式 | 匹配示例 | 改写结果 |
|---|---|---|
| 目录引用 | `python scripts/foo.py` | 绝对路径（仅当文件真实存在） |
| 文档引用 | `see reference.md` | 绝对路径 + `(use read_file to access)` |
| Markdown 链接 | `[Guide](./reference/guide.md)` | 绝对路径 + read_file 提示 |

**已知局限**：
- 词表/标点白名单导致漏网 — 如 `follow the instructions in forms.md`（`in` 不在词表）、`(see forms.md)`（后跟 `)` 不匹配）不会被改写
- 兜底机制：`Skill.to_prompt()` 注入 **Skill Root Directory**，LLM 据此可自行拼接路径
- 写 SKILL.md 的最佳实践：统一用 Markdown 链接或 `see xxx.md.` 形式引用资源

## 4. 脚本如何被调用：不注册成 tool，直接 bash

Skill 的 `scripts/*.py` **永远不会注册为 Agent 工具**，也永远不会被框架执行。调用链：

```
LLM 读到 SKILL.md/forms.md 里的命令行指令
  → 理解为建议的 bash 命令，自己拼参数
  → 调 bash 工具执行：python <绝对路径>/scripts/extract_form_field_info.py input.pdf out.json
  → stdout/stderr/exit_code 作为 tool result 返回
  → LLM 根据输出走文档里的分支逻辑（如 forms.md 的 "depending on the result..."）
```

为什么这样设计（对比注册成 tool）：

| | 注册成 tool | 文档 + bash |
|---|---|---|
| 启动成本 | 每个脚本都要 import + 注册 | 零 |
| 上下文成本 | tool schema 常驻 prompt | 零 |
| 灵活性 | 只能按预设参数调用 | 可组合：管道、重定向、前后处理 |
| 新增脚本 | 改代码 | 放个文件即可 |

脚本类型也不限于 Python — 框架视一切为文件、LLM 视一切为 bash：`node`、`bash`、编译型二进制、甚至"读出来抄进代码"的模板都可以。唯一的类型耦合在路径重写正则的白名单里（Pattern 3 只覆盖 `.md|txt|json|yaml|js|py|html`）。

## 5. LLM 为什么"会用" skill？

Skill 是一个**纯 prompt 协议**，不依赖任何模型侧专属机制。模型收到的三重信号：

1. **System prompt 方法论**（`system_prompt.md`）：明确教了三步 — "Check metadata → Call `get_skill` → Follow instructions"
2. **Level 1 元数据**：知道"什么时候该用哪个"
3. **Tool description**：`get_skill` 的描述说明它是按需加载动作

模型训练（tool use + instruction following）只提供底座能力。能力强的模型几乎不用教；弱模型可能出现"该调 get_skill 时硬答"或"加载了不照做"的问题。

## 6. 一个完整任务的时间线（以填 PDF 表单为例）

```
用户："帮我填这个 PDF 表单"
  │
  ├─ LLM 看到 Level 1 元数据里有 `pdf`，判断相关
  ├─ 调 get_skill("pdf")           ← Level 2：拿到 SKILL.md 全文
  ├─ 读到 "fill out a PDF form → read forms.md"
  ├─ 调 read_file(forms.md)        ← Level 3：拿到填表单指南
  ├─ 按 forms.md 指引调 bash 执行 check_fillable_fields.py 检查表单
  ├─ 根据输出走 "Fillable fields" 分支
  ├─ bash 执行 fill_fillable_fields.py 填表
  └─ 验证输出，向用户报告
```

## 7. 设计要点速记

- **发现的粒度是 `SKILL.md` 文件**，不是目录名 — 递归扫描，嵌套任意深度
- **frontmatter 必填 `name` + `description`**，description 写得好坏直接决定 LLM 会不会选它（它是唯一的路由信号）
- **所有 skill 启动时进内存，但只有元数据进 prompt** — 解析成本一次性，token 成本按需
- **框架只做信息调度**（何时给什么内容），执行、纠错、路径拼接全交给 LLM + 通用工具
- **绝对路径重写是上下文工程的实用技巧**：把"LLM 需要知道的环境事实"提前烘焙进文档，省掉它探索的成本
