# MCP server-memory：知识图谱记忆的原理与价值

> 学习笔记：`@modelcontextprotocol/server-memory` 的数据模型、工具接口，
> 以及"知识图谱"相比纯文本记忆真正贵在哪、值在哪。

## 它是什么

MCP 官方参考实现之一，把 LLM 的长期记忆存成一张知识图谱。
**底层就是一个 JSON 文件**（无索引、无事务、无查询语言、无嵌入），可用
`MEMORY_FILE_PATH` 环境变量指定存储位置，默认在包安装目录下的 `memory.json`。

Server 本身完全被动——它只是 9 个工具的"数据库壳子"，没有任何自动记忆逻辑。
**何时存、存什么、何时读、搜什么，全部由模型（AI）决定**；模型"会不会想起来
去用"，很大程度取决于 system prompt 有没有引导（不提，模型经常根本不用）。

## 数据模型：三样东西

```
实体 Entity        关系 Relation             观察 Observation
┌───────────┐     ┌──────────────────┐     ┌──────────────────┐
│ name: 用户 │ ──→ │ 用户 —喜欢→ 简体中文 │     │ "使用 Windows 11" │
│ type: person│    │ from → to (有向)   │     │ "在做 Mini-Agent" │
│ observations│    └──────────────────┘     │ （挂在实体上）      │
└───────────┘                              └──────────────────┘
```

- **实体（节点）**：`{name, entityType, observations[]}`，name 唯一标识
- **关系（边）**：`{from, to, relationType}`，有向三元组
- **观察（属性）**：挂在实体上的事实条目（字符串数组）

教科书说知识图谱 = "实体 + 关系"，但这里 **Observation 才是真正存记忆的地方**。
底层 JSON 长这样：

```json
{
  "entities": [{ "name": "...", "entityType": "...", "observations": ["..."] }],
  "relations": [{ "from": "...", "to": "...", "relationType": "..." }]
}
```

## 注册的工具（9 个）

| 类别 | 工具 | 作用 |
|---|---|---|
| 节点 | `create_entities` | 创建实体 |
| | `create_relations` | 创建有向关系 |
| | `delete_entities` / `delete_relations` | 删除（删实体时级联删其关系） |
| | `add_observations` / `delete_observations` | 实体事实的追加 / 删除 |
| 查询 | `read_graph` | 读出整张图谱 |
| | `search_nodes` | 按名称/类型/观察内容模糊搜索 |
| | `open_nodes` | 给定实体名，返回节点及其一跳邻居 |

查询工具都是只读的，这就是"查它存了什么"的入口；更省事的办法是直接看 JSON 文件。

## 一个完整例子：抽象劳动如何被复用

**写入前**，用户随口一句：

> "明天我打算用 glm 跑一遍 Mini-Agent 的评测，记得提醒我先看看配置。"

**写入时**，模型做一次理解与拆解（贵的部分），构造出：

```json
{
  "entities": [
    { "name": "Mini-Agent 评测计划", "entityType": "task",
      "observations": ["计划于 2026-09-16 执行", "使用 glm 模型", "执行前先检查配置"] },
    { "name": "Grant", "entityType": "person",
      "observations": ["正在开发 Mini-Agent 项目"] },
    { "name": "glm", "entityType": "model" }
  ],
  "relations": [
    { "from": "Grant", "to": "Mini-Agent 评测计划", "relationType": "plans" },
    { "from": "Mini-Agent 评测计划", "to": "glm", "relationType": "uses" }
  ]
}
```

注意这步发生了什么：**非结构化的一句话被拆成机器可寻址的部件**——
"明天"换算成绝对日期，"记得提醒"固化成 observation，隐含的人-任务-模型关系被显式画出。

**读取时**，一周后新会话里用户问"帮我检查下配置文件有没有问题"，模型先
`search_nodes`，返回的是带指针的结构：

```
Grant —plans→ Mini-Agent 评测计划 —uses→ glm
                └ observations: ["执行前先检查配置", "使用 glm 模型"]
```

模型由此知道：这个用户有个评测计划挂着"先检查配置"的待办——提醒跨会话兑现了。

## 核心洞察：贵在写入的抽象，不在存储

- **纯文本记忆**（往 notes 文件 append）：写入零成本，但每次读取都要靠模型
  现场重新解析——"明天"是哪天？和谁有关？——**把理解成本转移到了每次读取**，
  且句子间的关联要靠文字巧合。
- **知识图谱**：**读取时把理解成本一次性付掉**。写入时模型多做一步抽象，
  换来理解的结果被固化成 `from/to/name` 这样的"地址"，之后任何会话都能精确地
  查到、更新到、连到它（`add_observations` 追加进展、`delete_observations`
  把"明天"改为已完成、`create_relations` 连接新事物），不用碰其他记忆。

一句话：**JSON 文件确实简陋，但它保存的不是字节，是模型已经理解过的结构。**

## 局限与祛魅

- 名字唬人（继承自 RDF/Neo4j 那套学术语境），实现就是 JSON + 十几个 CRUD
  函数，几百行代码——"三元组存储的 Hello World 版"。
- `search_nodes` 只是字符串匹配，没有向量/语义相似度；不会自动去重、
  不会遗忘。所有"聪明"的部分全靠模型调用时自己做对。
- 它是**参考实现**，目的不是生产级产品，而是示范"这类能力的接口长什么样"。
  换 Neo4j、加向量检索都不影响工具接口——价值在约定，不在技术。
- 对学习 agent 机制来说，"薄"反而是优点：读完一个 `index.ts` 源码，
  就能看透"所谓 MCP server 不过是进程间的一组工具约定"。

## 配置备忘

在 `mini_agent/config/mcp.json` 中：

```json
"memory": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-memory"],
  "disabled": false
}
```

建议显式指定存储路径，方便查看和备份：

```json
"env": { "MEMORY_FILE_PATH": "E:/ai-agents/Mini-Agent/downloads/memory.json" }
```

想让模型真正用起来，需在 system prompt 中加入使用策略，例如：
"会话开始时用 read_graph/search_nodes 拉取相关记忆；用户说出重要事实或计划时，
主动用 create_entities / add_observations 保存。"
