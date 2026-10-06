# Poeticus Roadmap

> 更新日期：2026-10-06  
> 当前状态：公网阅读与 AI 伴读已经形成稳定基线；当前工程重点转向 Evidence、Evaluation 与下一阶段 Text Retrieval 实验。

Roadmap 只记录**下一阶段方向**。已经完成的发布过程不再混在未来计划里；具体任务和验收进入 GitHub Issues。

## 1. 当前基线

Poeticus 已经走通：

- React / TypeScript / Vite 阅读界面；
- FastAPI 同源后端；
- PostgreSQL 作品库与 3491 首宋词；
- 私人 EPUB → JSON → 私人 DB → 公网 DB 的数据链；
- LangGraph ReAct Agent；
- CNKGraph Evidence，以及 `lookup_allusion` / `lookup_reference` 两类 Tool；
- bounded multi-turn context；
- SSE 流式回答；
- localStorage Conversation persistence；
- Railway 公网部署；
- Python、前端 build/lint 和 Node 回归测试；
- 匿名 AI 的限额、并发和预算保护；
- 一套可重复运行的 Seed AI Eval，对照 `control_no_tools` 与当前 Agent，并记录 Process Trace。

因此后续不再把“是否要引入 PostgreSQL”“是否要做多轮”“是否要建立第一套 AI Eval”之类已完成事项当作未来目标。

## 2. 近期优先级

### 2.1 Corpus quality

当前最大的事实风险不是“作品数量不够”，而是 `imported_unreviewed` 数据质量。

近期重点：

- 修复已经发现的 EPUB 结构误判；
- 为小序、注释、寓声、缺文等边界补回归样本；
- 保持可重建的数据链；
- 逐步建立 curated/editorial correction 与原始抽取之间的明确边界。

原则仍是：

> 找到第一层错误数据就停在那里修，不跨层打补丁。

### 2.2 Evidence / Text Retrieval

当前生产 Agent 已有两类 CNKGraph Tool：

- `lookup_allusion`：人物、故事、典故性短语；
- `lookup_reference`：前代成句、近似文本和部分化用候选。

它们都返回 Evidence 候选，不自动证明出处关系。Seed Eval 也已经暴露当前边界：保留明显文本锚点的关系相对容易，高度压缩、反用或大幅改写仍不稳定。

下一阶段由 #119 把“文本相似 / 化用候选”单独作为 Retrieval 问题研究。第一步不是直接接 Agent 或向量数据库，而是先检查真实外部语料、建立可信实验输入，再决定 Corpus / Chunk / Benchmark 需要什么结构。只有 Retrieval baseline 证明有稳定增量后，才考虑 pgvector、ANN 或生产 Tool 接入。

需要实际回答：

- 第一版真实 Corpus 应包含什么；
- 原始作品怎样切成可检索单元；
- Ground Truth 是否确实存在于 Corpus；
- Embedding 是否真的把正确来源排到前面；
- 未命中究竟来自 Corpus、Retriever 还是关系本身超出当前能力；
- 命中候选以后怎样保留出处并避免把相似文本误写成确定来源。

### 2.3 Evaluation

Seed AI Eval baseline 已建立，但 Dataset 仍保持小规模、可人工复核，不追求一个总分。

当前重点：

- 工具该用时是否使用；
- 工具不该用时是否克制；
- 典故/年代/人物等硬事实；
- 前代文本 / 出处类问题的 Tool 选择与查询质量；
- 多轮指代；
- 文学解释是否落在原文而不是套话；
- Prompt、模型或 Evidence 变化是否造成退化；
- Ground Truth 本身是否需要修正。

Run 同时保留 Tool Call、Tool Result 和 Evidence 摘要，使失败可以继续定位到 Dataset、Agent / 路由、Tool Coverage 或当前能力边界，而不是只看最终答案。

单元测试、AI Eval、运行 Trace 和真实浏览器验收继续分层，不互相冒充。

### 2.4 UX reliability

已发布后的体验问题以 Issue 为准，例如：

- 移动端与窄屏；
- iOS 选区行为；
- Conversation 交互；
- SSE 中断与失败恢复；
- 长对话的可读性。

这类问题按真实用户路径修，不为了“重构漂亮”提前扩张。

## 3. 中期方向

### Conversation

当前 Conversation 存在浏览器 localStorage。只有当出现明确需求时，再考虑：

- 一首作品多个 Conversation；
- 服务端 Conversation persistence；
- 跨设备同步；
- resumable generation；
- 跨作品比较；
- 长期记忆。

### Skills

如果把文学分析拆成 Skill，需要有真实不同的输入、数据依赖和验证方式，而不是简单增加几个 Prompt 文件。

可能的方向：

- 文本/章法分析；
- 典故与 Evidence；
- 知人论世；
- 多作品比较。

### Engineering spikes

MCP、Reranker、Hybrid Search、Redis、Checkpointer 等可以做短期 Spike，但进入主线前必须回答“它解决 Poeticus 的哪个真实问题”。

## 4. 求职与学习目标

一个技术点准备写进简历前，至少满足：

> 做过 → 遇到过问题 → 能解释为什么这样做，以及没有这样做会怎样。

Poeticus 的价值不是覆盖最多名词，而是用一个真实产品贯穿：

```text
Frontend
   ↓
API / Validation
   ↓
Agent / LLM / Tool
   ↓
Evidence
   ↓
PostgreSQL / Data Pipeline
   ↓
Deployment / Observability / Evaluation
```

## 5. 停止线

每个阶段只打开当前真正需要的一层：

1. 明确问题；
2. 做最小真实闭环；
3. 运行并观察；
4. 记录取舍；
5. 再决定是否深入。

当前不追求把 Poeticus 变成“什么都有”的平台。优先保持现有闭环可信、可解释、可维护。
