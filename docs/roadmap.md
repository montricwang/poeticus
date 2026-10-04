# Poeticus Roadmap

> **发布状态快照（2026-10-04）**：Poeticus `v0.1.0` 已在 [Railway](https://poeticus-web-production.up.railway.app/) 正式公开，并有 [GitHub Release](https://github.com/montricwang/poeticus/releases/tag/v0.1.0)。当前已交付宋词目录（3491 首）、查询/阅读、原文选区提问、多轮 SSE 伴读、整首赏析和最小匿名调用保护；不等于长期的个人研究工作区、专业检索或正式评测已经全部完成。
>
> **当前工作方式**：先进行已发布架构的学习与复盘，暂不新增功能；发现的问题留在 [Issues](https://github.com/montricwang/poeticus/issues) 中。移动端文字越界/目录分页 [#85](https://github.com/montricwang/poeticus/issues/85)、iOS 划词同步 [#86](https://github.com/montricwang/poeticus/issues/86)、匿名 AI 安全跟进 [#77](https://github.com/montricwang/poeticus/issues/77) 仍待处理。以下原有路线保留了此前阶段的规划语言，不能把计划当作已实现事实。

> 更新日期：2026-09-30  
> 当前目标：在 2026-10-31 前，把 Poeticus 做成一个可以公开展示、可以用于求职面试、并真正支撑 AI 应用工程学习的项目。

## 1. 项目的当前定位

Poeticus 当前首先是一个 **项目驱动学习（Project-based Learning）+ 求职作品集**。

产品思维仍然重要，因为真实的产品边界能够迫使工程设计围绕真实问题展开；但现阶段不以“尽快商业化”作为最高目标，也不为了追求所谓生产级完整性无限扩张范围。

十月底以前，项目要同时完成两件事：

1. **做出一个真正能使用、能演示的古典诗词 AI 阅读产品。**
2. **让简历中的核心 AI / 后端工程能力都有真实项目经验支撑。**

因此，Poeticus 后续版本不是单纯增加功能，而是有意识地逐步打开不同工程问题域：

```text
v0.1  AI 阅读闭环
  ↓
v0.2  Data / PostgreSQL / ETL / Search / Minimal RAG
  ↓
v0.3  Skills / Agent Orchestration / Evaluation
  ↓
Spikes  MCP / Rerank / Cache / Memory / ...
```

目标不是把所有技术名词都塞进系统，而是让每一项进入简历的能力至少经历：

> **做过 → 遇到过真实问题 → 能解释为什么这样设计、还有什么取舍。**

---

## 2. 产品方向：精品馆藏，而不是“数据库越大越好”

Poeticus 不必把“收录中国古典诗词最多”作为前台产品目标。

更适合当前方向的是：

> **以人物和精选作品为中心的深度阅读馆。**

公共馆藏可以体现明确的编辑选择与个人品位，例如围绕苏轼、周邦彦、辛弃疾、姜夔等词人组织作品，而不是把几十万首作品直接平铺给读者。

长期可以区分三层：

### 2.1 Curated Library：公共精品馆藏

由 Poeticus 主动选择、组织和维护的作品。

对这一层承担较高质量责任，包括：

- 稳定作品 ID；
- 作者、题名、词牌、正文；
- 来源与版本记录；
- 审核状态；
- 人物、时期、主题或专题选集；
- 更完整的阅读与赏析体验。

### 2.2 Personal Library：个人书架

用户主动找到、收藏或讨论过的作品。

作品不必属于公共精品馆藏，但可以保存为用户自己的长期阅读对象，并继续围绕它建立 Conversation。

### 2.3 External Discovery：外部作品发现

当用户点名一首馆藏中没有的作品时，可以通过外部诗词库、Wikisource、CNKGraph 或其他可靠来源寻找候选正文，再临时转换成 Poeticus 的 `Poem`。

这意味着：

> **Poeticus 可以拥有“找到很多诗”的能力，但不必把所有诗都当成正式馆藏。**

大规模外部语料仍然有工程价值，但更多可以作为检索、导入和数据工程的后备池，而不是前台产品必须直接暴露的全部内容。

---

## 3. v0.1 — AI 阅读闭环

**目标发布时间：2026-09-30（目标，不因新增远期能力继续拖延）**

### 3.1 v0.1 要证明什么

v0.1 要证明：

> Poeticus 已经不是一个单轮 Prompt Demo，而是一个围绕真实诗歌阅读对象工作的 AI 应用。

当前已经具备：

- React + TypeScript 阅读界面；
- 稳定 `Poem` / `PoemContext`；
- 原文划选与引用提问；
- FastAPI 后端；
- LangGraph ReAct Agent；
- CNKGraph 典故 Tool / Evidence；
- 流式回答；
- 多轮 Conversation Context；
- 按作品隔离的当前 Conversation；
- localStorage 会话与草稿恢复；
- 整首作品赏析；
- LangSmith Trace；
- 基础自动化测试。

### 3.2 v0.1 的内容策略

v0.1 **不引入数据库**。

当前作品继续使用静态结构：

```text
frontend/src/data/poems/
├── index.json
├── poem-a.json
├── poem-b.json
└── ...
```

构建时由前端加载这些 JSON。

对于约几十至一百首作品，这种方案简单、透明、易于调试，暂时没有必要引入 PostgreSQL、分页 API、连接池、Migration 等额外复杂度。

v0.1 内容可以进一步收束为：

> **Poeticus · 苏轼词选**

目标可扩展到约 50–100 首苏轼词，但**固定数量不是发布阻塞条件**。如果今天只能稳定导入、展示并检查其中一部分，应优先发布一个完整闭环，而不是为了凑到“100 首”继续延迟。

作品质量状态应保留明确区分，例如：

- `reviewed`
- `imported_unreviewed`
- `needs_review`
- `disputed`

少量用于 Demo、截图和重点阅读的作品可以优先核对；批量导入作品不应因为进入仓库就假装已经完成校勘。

### 3.3 v0.1 发布前剩余工作

v0.1 只做发布收口，不再增加新的核心 AI 架构。

优先完成：

1. **内容整理**
   - 决定首版苏轼词选范围；
   - 批量导入时统一转换到现有 `Poem` schema；
   - 保留来源和 `review_status`。

2. **测试收口**
   - 补齐 `/analyze` 的最小自动化回归测试；
   - 不把完整 AI Eval Baseline 作为 v0.1 发布阻塞项。

3. **文档与 Issue 对齐**
   - README 更新到当前真实能力；
   - 删除“尚不支持多轮”等已经过期的描述；
   - 检查已经实现但仍处于 open 状态的旧 Issue，关闭或更新状态；
   - 当前代码、README、Issues 三者保持一致。

4. **Release Smoke Test**
   - `pytest`
   - `npm run lint`
   - `npm run build`
   - 人工走一遍：
     - 选择作品；
     - 划词；
     - 普通提问；
     - 需要典故 Tool 的问题；
     - 连续追问；
     - 切换作品后恢复 Conversation；
     - 刷新恢复；
     - 整首赏析；
     - 失败 / 中断路径没有明显回归。

5. **发布**
   - README 可供外部读者理解；
   - 打 `v0.1.0` Release / Tag；
   - 保留一套可重复演示的代表性作品和问题。

### 3.4 v0.1 明确不做

以下内容不阻塞 v0.1：

- PostgreSQL；
- 85 万首全量作品库；
- 完整 RAG；
- 多个赏析 Skill；
- 完整 AI Eval Dataset；
- MCP；
- Reranker；
- Redis；
- 服务端 Conversation persistence；
- 多 Conversation UI；
- Cross-conversation Memory；
- 跨作品长期 Memory；
- 生产级账号与权限系统。

---

## 4. v0.2 — Data + PostgreSQL + Minimal RAG

v0.2 的目标不是单纯“增加很多诗”，而是故意打开 **数据工程与 RAG** 这两个问题域。

### 4.1 Data / Database

v0.1 的静态 JSON 在几十至一百首规模下是合理方案。

当尝试接入几十万甚至 85 万级外部语料时，数据访问方式发生变化：

```text
Static JSON
   ↓
规模扩大
   ↓
External Corpus
   ↓
ETL / Normalize
   ↓
PostgreSQL
   ↓
Search API
   ↓
Frontend
```

可选择的数据源包括：

- `chinese-poetry/chinese-poetry`
- `Werneror/Poetry`
- 其他后续确认的开放诗词语料

这一阶段重点不是“最终到底有多少首”，而是实际走通：

- 外部 CSV / JSON 导入；
- Canonical `Poem` schema；
- stable ID；
- 作者 / 朝代 / 标题规范化；
- 基础去重；
- provenance / source；
- review status；
- PostgreSQL；
- Migration；
- Index；
- Pagination；
- 作者 / 标题 / 正文搜索；
- API 查询；
- 基础查询性能测量。

如果最终导入 40 万或 85 万首，可以作为规模指标，但简历真正有价值的是：

> **如何把多源、大规模、质量不一的数据变成一个可查询、可维护的作品库。**

### 4.2 Minimal RAG

RAG 必须真实走一遍，但十月份不要求做到研究级深度。

优先选择一种对 Poeticus 真正有意义的资料，例如：

- 苏轼编年资料；
- 可靠注释；
- 历代评论；
- 词话或诗学资料；
- 人物生平材料。

完成一个完整最小闭环：

```text
Source
  ↓
Parse / Chunk
  ↓
Metadata
  ↓
Embedding / Index
  ↓
Retrieval
  ↓
（可选）Rerank
  ↓
Context
  ↓
Answer
  ↓
Citation / Provenance
```

必须至少真实理解和经历：

- 为什么这里需要 RAG；
- chunk 粒度怎么决定；
- metadata 如何设计；
- 不同问题是否应检索不同资料；
- retrieval scope 怎么限制；
- 如何保留来源；
- 怎么避免“检索到了 ≠ 回答正确”；
- 怎样初步判断 retrieval 是否改善了回答。

重点是建立真实手感，而不是为了简历机械写“用了向量数据库”。

---

## 5. v0.3 — Skills + Agent Orchestration + Evaluation

v0.3 用来证明 Poeticus 不只是“一个 Agent + 一个 Tool”。

### 5.1 Skill

完整的文学赏析未来可能拆成多个维度，例如：

- 炼字 / 语言；
- 意象；
- 时空；
- 章法；
- 声律；
- 典故与互文；
- 历代评论；
- 知人论世。

但十月底以前**不要求一次实现全部八个维度**。

优先实现 2–3 个真正不同的 Skill，使它们在数据依赖和验证方式上有明显差异。

例如：

1. **章法 / 文本分析 Skill**
   - 主要依赖当前作品；
   - 输出结构化分析；
   - 不强制外部 Evidence。

2. **典故 / Evidence Skill**
   - 明确需要 Tool / Retrieval；
   - 输出候选出处和证据；
   - 强调来源。

3. **知人论世 / Context Skill**
   - 依赖人物、编年或历史资料；
   - 可以与 RAG 结合。

Skill 不应只理解为“多写几个 Prompt 文件”。

至少需要明确：

- 输入；
- 输出契约；
- 是否需要外部 Tool / RAG；
- 错误和降级路径；
- 能否并行；
- 是否依赖其他 Skill；
- Agent 什么时候调用；
- 综合结果如何处理冲突。

### 5.2 Agent Orchestration

继续深化对 Agent 的理解：

- 什么由确定性 Workflow 决定；
- 什么交给模型选择；
- Tool Calling 与 Skill Routing 的关系；
- ReAct 在当前任务中的边界；
- 为什么不把所有步骤都交给自由规划；
- Tool / Skill 失败时怎样降级。

Poeticus 已经经历过：

```text
固定 Intent Router
        ↓
发现意图枚举会持续膨胀
        ↓
迁移到 ReAct Agent
```

后续需要保留并能解释这段架构演进，而不是把旧方案当成“做错了”。

### 5.3 Evaluation

建立一套小而真实的 AI Eval Baseline。

第一阶段可以只有 10–20 个案例，但必须可重复。

区分两类问题：

#### 硬事实 / Evidence

例如：

- 作者；
- 年代；
- 典故；
- 人物关系；
- 原文出处。

可以关注：

- retrieval recall；
- factual correctness；
- citation correctness；
- Tool 是否该用时用了；
- 是否无依据编造。

#### 文学解释

例如：

- 意象；
- 章法；
- 炼字；
- 风格；
- 情感结构。

不能简单用“答案是否与标准答案完全一致”判断，而应关注：

- 是否真正基于原文；
- 是否指出具体字句；
- 是否有空泛套话；
- 是否把解释说成唯一事实；
- 是否自相矛盾；
- 是否区分事实与解释。

继续使用 LangSmith 做 Trace / Observability，并开始记录：

- Tool 调用；
- latency；
- token / cost；
- 失败路径；
- Prompt / 模型变更前后差异。

---

## 6. Learning Spikes：为了理解而做的小实验

有些技术不应该为了“简历上有”而直接改造主架构，但可以做小型 Spike。

原则：

> **Spike 可以是短生命周期实验，但必须真实运行过，并能说清它解决什么问题。**

候选包括：

### MCP Spike

可以尝试把 Poeticus 的部分能力暴露成 MCP Server：

- `get_poem`
- `search_poem`
- `lookup_allusion`

目标不是把整个系统强行 MCP 化，而是实际理解：

- MCP Server / Client；
- Tool Schema；
- Transport；
- MCP 与 REST API 的区别；
- MCP 与模型 Tool Calling 的关系；
- 什么能力适合暴露为 MCP Tool。

### 其他可选 Spike

根据剩余时间和真实需求选择：

- Hybrid Search；
- Reranker；
- Redis Cache；
- LangGraph Checkpointer；
- Server-side Conversation persistence；
- Summary Memory；
- Retrieval Memory；
- 多作品 Comparison Context；
- External Poem Resolver；
- User Personal Library。

这些属于 Backlog / Spike，不自动进入某个 Release。

---

## 7. 十月份的能力地图

十月底以前，希望 Poeticus 至少让下面几条主线都有真实实践：

```text
Poeticus
│
├─ LLM / Context
│   ├─ Prompt
│   ├─ Structured Output
│   └─ Multi-turn Context
│
├─ Agent
│   ├─ ReAct
│   ├─ Tool Calling
│   ├─ Routing / Tool Selection
│   └─ MCP Spike
│
├─ RAG
│   ├─ Chunking
│   ├─ Metadata
│   ├─ Retrieval
│   ├─ Citation
│   └─ Rerank（可选）
│
├─ Data
│   ├─ ETL
│   ├─ PostgreSQL
│   ├─ Index
│   ├─ Search
│   └─ Large Corpus
│
├─ Skill
│   ├─ Text Analysis
│   ├─ Evidence-based Skill
│   └─ Skill Orchestration
│
└─ Evaluation
    ├─ Unit / Regression
    ├─ AI Eval
    ├─ LangSmith Trace
    └─ Cost / Latency
```

不是每个叶子节点都必须做到很深。

优先级是：

> **主干走通，重点节点做深；能够真实解释，而不是只认识名词。**

---

## 8. 什么技术可以写进简历

一个技术词准备进入简历之前，至少满足：

> **做过 → 遇到问题 → 能解释取舍。**

例如：

### RAG

至少能回答：

- 为什么这个场景要用 RAG；
- 数据从哪里来；
- 怎么切；
- metadata 是什么；
- 怎么检索；
- 为什么某些问题不应该走同一种检索；
- 怎么判断检索是否有帮助；
- citation 怎样保留。

### PostgreSQL / Data Engineering

至少能回答：

- 为什么 v0.1 不需要数据库；
- 为什么规模扩大后需要；
- schema 怎么设计；
- 外部数据怎样 normalize；
- 索引为什么这样建；
- 去重和 provenance 怎么处理；
- 查询性能怎么观察。

### Agent

至少能回答：

- 当前为什么选择 ReAct；
- Tool Calling 的循环是什么；
- 固定 Router 为什么被替换；
- 哪些动作仍然应该保持确定性；
- Tool 失败怎么处理；
- Agent 与 Workflow 的边界。

### Skill

至少能回答：

- Skill 与 Prompt 文件有什么区别；
- 输入输出契约是什么；
- 哪些 Skill 要 RAG / Tool；
- 如何编排多个 Skill；
- 如何避免“八个 Prompt 并排放”。

### Evaluation

至少能回答：

- 单元测试、回归测试、AI Eval、Trace 的区别；
- 硬事实和文学解释为什么不能用同一套指标；
- 如何做固定 Baseline；
- Prompt / Tool 改动后怎么判断退化。

### MCP

只有实际运行过 Server / Client，并能解释它与 REST / Tool Calling 的关系后，才写进简历。

---

## 9. 文档与项目事实怎么保存

Poeticus 的项目事实以 GitHub 仓库为 Source of Truth。

### `README.md`

面向外部读者：

- Poeticus 是什么；
- 当前能做什么；
- 如何运行；
- 当前版本状态。

README 不承担完整 Roadmap。

### `docs/roadmap.md`

记录：

- 当前阶段目标；
- 近期版本方向；
- 学习 / 求职能力主线；
- Release 与 Backlog 的边界。

它不是开发任务清单。

### `docs/architecture/`

记录当前系统真正采用的架构。

例如：

- LangGraph；
- Conversation state；
- 未来新形成的 RAG / Data / Skill 架构。

### `docs/devlog/`

记录已经发生的开发事实、当天决策和复盘。

### GitHub Issues

负责具体可执行任务和验收。

原则：

> **当前 Issue 负责当前闭环；未来方向进入 Roadmap / Backlog，不把所有未来设想塞进当前实现。**

### Architecture / Decision Tracker

关键架构长期演进可以使用 Architecture Issue 或 ADR 保存：

- 当时为什么采用 A；
- 什么事实让系统改成 B；
- 哪个 Issue / Commit 完成了变化。

### ChatGPT Project / Library

用于：

- 教学与开发协作手册；
- 项目迁移与交接摘要；
- 历史技术资产审计；
- 跨对话长期学习经验。

ChatGPT 中的内容不作为项目当前状态的唯一事实来源。

---

## 10. 十月底以前的建议节奏

这是目标节奏，不是不可调整的硬性承诺。

### 2026-09-30：v0.1

完成：

- 当前 AI 阅读闭环；
- 内容与 README 收口；
- 测试 / smoke test；
- 发布 `v0.1.0`。

### 10 月上旬：v0.2 Data / RAG

重点体验：

- ETL；
- PostgreSQL；
- Index / Search；
- 大规模 Corpus；
- 第一版 RAG；
- Citation。

### 10 月中旬：v0.3 Skill / Evaluation

重点体验：

- 2–3 个 Skill；
- Skill / Tool 编排；
- AI Eval；
- LangSmith；
- Prompt / Retrieval 前后对比。

### 10 月下旬：求职展示收口

重点不再无限扩功能，而是：

- 修关键 Bug；
- 补演示数据；
- 梳理架构图；
- 完善 README；
- 准备 Demo；
- 整理面试讲述；
- 把简历中的每一个技术名词映射到真实实现、问题和取舍。

---

## 11. 当前最重要的停止线

Poeticus 有足够多可以继续扩展的方向，但十月底以前最危险的事情是同时展开所有方向。

因此每个阶段都遵守：

1. 先明确这一阶段要学习 / 证明什么；
2. 做一个最小但真实的闭环；
3. 真实运行、观察、记录问题；
4. 能解释取舍；
5. 再决定是否深入。

最终目标不是在一个月内造出最大的诗词平台，而是：

> **完成一个能够公开展示的垂直 AI 产品，并通过它真实走过 Agent、Tool、RAG、Data、Skill、Evaluation 等现代 AI 应用工程的核心路径。**
