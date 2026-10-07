# Poeticus Roadmap

> 更新日期：2026-10-07  
> 当前状态：`v0.1.0` 已公开发布；3491 首宋词、PostgreSQL 阅读 API、多轮 SSE 伴读、整首赏析、典故工具和匿名 AI 保护均已上线。

Roadmap 只记录**下一阶段方向**。已经完成的发布过程不再混在未来计划里；具体任务和验收进入 GitHub Issues。

## 1. 当前基线

Poeticus 已经走通：

- React / TypeScript / Vite 阅读界面；
- FastAPI 同源后端；
- PostgreSQL 作品库与 3491 首宋词；
- 私人 EPUB → JSON → 私人 DB → 公网 DB 的数据链；
- LangGraph ReAct Agent；
- CNKGraph 典故工具；
- bounded multi-turn context；
- SSE 流式回答；
- localStorage Conversation persistence；
- Railway 公网部署；
- Python、前端 build/lint 和 Node 回归测试；
- 匿名 AI 的限额、并发和预算保护。

因此后续不再把“是否要引入 PostgreSQL”“是否要做多轮”等已完成事项当作未来目标。

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

### 2.2 Evidence / RAG

当前重点已经从“要不要做 Retrieval”进入“怎样建立真实可验证的前代文本检索链”。

当前路线：

```text
Werneror Corpus
→ Work / Chunk
→ Embedding Artifact
→ Vector / Lexical Retrieval
→ Candidate Fusion
→ DeepSeek / Agent 判断
```

近期按以下顺序推进：

1. 完成 Qwen sentence / clause 与 BERT-CCPoem clause Artifact 的真实 Eval 对照；
2. 分别做 pgvector 与 FAISS spike，用同一批 Artifact 比较过滤、性能和部署边界；
3. 增加 Lexical Retrieval baseline，优先从 character n-gram / 近似字面检索开始；
4. 根据真实结果决定是否进入 Hybrid Retrieval；
5. 最后再接成正式 Agent Tool。

当前已经明确：

- Retrieval hit 只是候选，不自动等于文学关系成立；
- Corpus Chunking 与 Query Strategy 分开；
- Query 需要比较整句、分句和多粒度策略；
- 向量索引与 Embedding Artifact 解耦；
- 语料与朝代高度静态，因此允许预计算、多索引，必要时也允许多后端；
- 新增语料通常做增量 Embedding，不重新全库计算；
- 古汉语分词属于可替换的 Query / Text Analysis 组件，不提前扩张成独立项目；先验证字符级检索是否已经足够。

候选资料仍包括：

- 可靠注释；
- 词话与历代评论；
- 作者编年/生平资料；
- 可追溯的作品出处。

Document Corpus 与实时业务信息继续分开：相对静态知识适合 RAG，真正实时状态更适合 API / Database Tool。

### 2.3 Evaluation

建立小而稳定的 AI Eval baseline，优先覆盖：

- 工具该用时是否使用；
- 工具不该用时是否克制；
- 典故/年代/人物等硬事实；
- 多轮指代；
- 文学解释是否落在原文而不是套话；
- Prompt、模型或 retrieval 变化是否造成退化。

Retrieval 继续优先复用现有 intertext Eval，不为了“严谨”重复制造一套同等复杂度的 Benchmark。

单元测试、AI Eval、LangSmith Trace 和真实浏览器验收继续分层，不互相冒充。

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

允许做短期 Spike，但进入主线前必须回答“它解决 Poeticus 的哪个真实问题”。

当前有明确学习 / 选型价值的 Spike：

- pgvector：SQL + metadata filtering + vector index；
- FAISS：独立向量索引、ANN、索引文件与回表；
- Hybrid Search：Lexical + Dense 的候选融合；
- Reranker：只在现有召回候选质量证明需要时再引入。

MCP、Redis、Checkpointer 等仍然按真实需求购买复杂度。

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
Evidence / Retrieval
   ↓
PostgreSQL / pgvector / FAISS / Data Pipeline
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
