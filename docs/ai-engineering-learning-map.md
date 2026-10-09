# Poeticus · AI 工程能力学习地图

> 更新日期：2026-10-09。本文是**个人 AI 工程能力与求职作品集的学习规划**，不是 Poeticus 的当前架构，也不是功能 Backlog。  
> 核心原则：**求职所需的可迁移工程能力，优先级略高于 Poeticus 的功能扩张；学习实验可以没有产品收益，但不能无期限扩张或破坏生产。**
>
> **分工**：[产品 Roadmap](roadmap.md) 管“Poeticus 下一步交付什么”；[数字人文资源地图](digital-humanities-resources.md) 管“哪些外部资料/工具可复用”；**本页只管“哪些技术我要掌握到什么深度”**。执行及实验结果仍进入相关 Issue/PR，不在这里维护第二套实现状态。

## 1. 四种学习深度：从直接复用到亲自构建

| 层级 | 目标 | 完成证据 | 明确不要求 |
| --- | --- | --- | --- |
| **L0 · 知道边界，直接复用** | 说清楚解决什么、为何成本高、适用条件、基本限制 | 会做选型判断，知道去哪查资料 | 为证明技术能力从零重做 |
| **L1 · 能调用并解释** | 接入 API/SDK/数据，理解输入输出、内部主要环节、错误与费用 | 真实调用样例 + 能解释调用链与风险 | 重建工具内部引擎 |
| **L2 · 亲手跑通、拆解、对照** | 本地部署或集成一个小实验，改参数，观察成功、失败、耗时/成本 | 可重复 Demo + 一组对照 Case + 结论 | 直接替换生产架构或全量规模化 |
| **L3 · 独立组合核心流程** | 给一个没有现成垂直工具的新领域，能用通用基础组件设计、实现、验证小系统 | 可运行端到端流程 + Eval + 失败排查 + 取舍说明 | 手写模型内核、FAISS 引擎、数据库存储引擎或完整训练框架 |

**“自己造轮子”的边界**：L3 是独立实现领域级解决方案，而不是重新实现底层框架。例如自己搭 RAG，但仍可调用 Embedding Model、FAISS、PostgreSQL；自己建小型知识图谱，但仍可用 LLM、关系表和成熟图算法库。

学习等级与生产采用是两条轴：**L2 学习完成、生产暂不采用，完全可以视为成功**。已有代码也不意味着自己已经真正掌握；需要能解释数据流、边界、失败和为何如此设计。

## 2. 技术清单（优先级 × 学习深度）

说明：
- **P0 = 求职应能熟练讲解、操作的核心能力**；**P1 = 值得安排有界实践**；**P2 = 按兴趣或面试方向选择，不要求短期全部做完**。
- “仓库已实现”只表示 Poeticus 曾有可核对的实现/实验，**不代表个人已经全部理解**；“待做”也不表示产品必须上新功能。
- 优先级反映当前以 AI 应用/RAG/Agent 工程为主的求职方向，不等于对所有 AI 岗位通用。

### A. RAG、检索与知识工程

| 技术能力 | 目标深度 | 现有基础 / 下一份学习证据 | 优先级 |
| --- | --- | --- | --- |
| **标准 RAG 全链路**：文本→清洗→Chunk→Embedding→索引→召回→回答与引用 | L3 | 现有 Corpus / Tool 链已实践；复盘每层输入输出、召回缺陷和可替换点 | P0 |
| **Dense / Lexical / Hybrid**：向量检索、BM25、RRF、Query Plan、过滤 | L3 | 已有约 85 万作品的多粒度检索；结合 [#119](https://github.com/montricwang/poeticus/issues/119) / [架构文档](architecture/text-retrieval.md) 复盘；不重写 FAISS 算法 | P0 |
| **Reranking**：Bi-Encoder 与 Cross-Encoder、精排与粗召回的不同 | L2 | [#119](https://github.com/montricwang/poeticus/issues/119) 已规划固定候选池 + Cross-Encoder 离线对照；尚非线上决策 | P1 |
| **向量数据库**：FAISS（索引库）与 pgvector/Qdrant 等数据库能力差别 | L2 | **FAISS 已实践，但不等于用过向量数据库**。任选一种做小数据 CRUD、过滤、向量检索、索引更新及性能对照；不用迁移生产 | P1 |
| **分层/父子块 RAG**：文档→章节→段落→证据句，检索与阅读上下文分离 | L3（小型） | 在 [#133](https://github.com/montricwang/poeticus/issues/133) 的 2–3 部词话上实现最小“短块召回、上级上下文回读”，可独立演示 | P1 |
| **多轮/多跳证据检索（Agentic RAG）**：查→读→改 Query→再查→归因 | L2–L3 | 已有工具循环与 Query reformulation Case；用 [#154](https://github.com/montricwang/poeticus/issues/154) / [#174](https://github.com/montricwang/poeticus/issues/174) 验证失败、Tool budget 与来源 | P1 |
| **知识图谱构建**：实体抽取、对齐、关系、来源与审核 | L3（几十条关系） | 用约 10–20 条词话样本做最小 KG（JSON/SQL 即可），验证消歧、证据、错误、更新；参考 [#149](https://github.com/montricwang/poeticus/issues/149) | P2 |
| **GraphRAG / Graph-based Retrieval**：实体关系辅助召回、多跳关系查证 | L2 | 先做小图 + 5 个跨文献问题，对照普通 RAG 是否真正漏查；不预设需要微软 GraphRAG 整套 Pipeline 或 Neo4j | P2 |
| **领域数据清洗、版本、来源追溯** | L3 | EPUB → 作品库已实践；复盘来源权限、规范化、异文、错误回滚、批处理与 Eval | P0 |

### B. LLM 应用、Agent、协议与评测

| 技术能力 | 目标深度 | 现有基础 / 下一份学习证据 | 优先级 |
| --- | --- | --- | --- |
| **LLM API、结构化输出、Prompt 与模型边界** | L3（应用层） | 已有模型调用与 Pydantic；能说明抽取失败、幻觉、Token/延迟/费用、回退和 Schema 验证 | P0 |
| **Tool Calling 与 Agent Loop** | L3 | LangGraph 已实现 ReAct 式 Tool 决策；掌握何时调用、错误结果、预算、停止条件、状态与流式响应；见 [Agent 架构](architecture/langgraph.md) | P0 |
| **MCP Server + Client**：Tools、Resources、Prompts、发现、传输、权限 | **L2（亲自做）** | [#185 MCP 学习 Spike](https://github.com/montricwang/poeticus/issues/185)：薄封装一个只读 Poeticus Service，Server/Client/Inspector 实测，生产暂不迁移 | **P1（优先）** |
| **Tool Routing / 外部 Web Search / Evidence Contract** | L3 | 已有 EvidenceService；[#153](https://github.com/montricwang/poeticus/issues/153) / [#154](https://github.com/montricwang/poeticus/issues/154) 补真实 Case，区分 Candidate 与已验证事实 | P1 |
| **AI Eval / Observability**：离线样本、工具 Trace、回归、判分误差 | L3 | 已有 Seed Eval / Retrieval Eval；复盘 baseline、同条件对照、错误分类、追踪实际来源、LangSmith/可替换 Trace | P0 |
| **长期 Memory / Critic Persona / Self-refine** | L2，真实需求才升 L3 | [#148](https://github.com/montricwang/poeticus/issues/148) / [#150](https://github.com/montricwang/poeticus/issues/150)；选小实验，严禁 AI 的自生成内容自证正确 | P2 |
| **Fine-tuning / LoRA / PEFT** | L1（理解）→ 可选 L2（小实验） | Poeticus 近期不需要训练自己的模型；可通过历史工作经验讲清 SFT 与 RAG 的边界。若岗位明确要求，再做限定数据、成本的实验 | P2 |
| **从头预训练大模型** | **L0** | 掌握数据、算力、优化、评估和成本量级的心智模型即可；不在 Poeticus 动手造 | 不排期 |

### C. 通用工程（防止只会在 AI 框架应用层工作）

| 技术能力 | 目标深度 | 现有基础 / 下一份学习证据 | 优先级 |
| --- | --- | --- | --- |
| **Python / 异步 / HTTP / Pydantic / API 契约** | L3 | FastAPI、SSE 已实践；能够独立定位请求、序列化、超时、状态码与并发问题 | P0 |
| **SQL / PostgreSQL / 数据建模和迁移** | L3（应用数据层） | 公开作品库已用；学习关系、事务、索引、版本与 schema migration，不能只知道能执行 SELECT | P0 |
| **测试、CI、错误归因** | L3 | 项目已有 pytest、前端测试、AI Eval、E2E；能说明每层测什么及一次回归失败如何定位 | P0 |
| **Linux / 进程、网络、Nginx、TLS、日志与部署** | L2–L3 | 历史部署实战；由 [#166](https://github.com/montricwang/poeticus/issues/166) 补服务器/存储/网络基础 | P0 |
| **Docker / Compose / 可复现部署** | L2 | [#79](https://github.com/montricwang/poeticus/issues/79) 已有学习 Issue；本地或测试环境完成，勿为了学习迁移生产 | P1 |
| **身份验证、授权、限流、成本与密钥安全** | L2–L3 | 现有公开 AI API 已有限流/配额；增加测试失效路径，MCP 对外暴露时另做安全评估 | P1 |
| **大型分布式数据库引擎、自己实现 ANN、Kubernetes 集群** | L0–L1 | 能说明使用时机与核心概念，不在此项目自行实现或部署集群来增加复杂度 | 不排期 |

## 3. 关于 MCP 的特别决策

- **Tool Calling**：模型 / Agent 在当前上下文中决定调用哪个工具；这是我们已经实践的业务调用机制。
- **MCP**：约定不同 Host 和工具服务之间如何发现、调用并交换结构化上下文（Tools、Resources、Prompts）；是跨宿主复用接口，不是自动提升 Agent 推理质量的框架。
- 现有 `LangGraph → native Tool → domain service` 足够支撑 Poeticus 生产。学习路径可以增加并行的 `MCP Client → MCP Server → same domain service`，**不复制领域逻辑，也不提前把所有 Tool 搬迁到 MCP**。
- 当未来明确存在 IDE、其他 Agent 或多 Host 消费同一批能力时，再根据实测复杂度考虑生产 MCP；现在 **学习要做，生产迁移待定**。
- 官方 SDK 文档：[MCP Python SDK](https://py.sdk.modelcontextprotocol.io/)。

## 4. 执行顺序、停手条件和作品集证据

**不是要一次性完成本表。** 建议始终只保持 **一个主动的学习 Spike**（原有正常缺陷与生产维护另计），最多每次从学习地图挑一项：

1. **短期优先**：#185 MCP 动手实验；#119 Cross-Encoder；二者按时间先后开展，不同时开启两套新实验。
2. **下一阶段**：#133 小型有出处的词话 Document RAG（顺便学分层 RAG）；[#79](https://github.com/montricwang/poeticus/issues/79) Docker/Compose。
3. **视岗位和真正缺口**：向量数据库 PoC、知识图谱构建与 GraphRAG 对照。不要因为“没碰过”而要求它们全部进线上。
4. **只复盘不重复建设**：已有 Dense/BM25/RRF、Tool Calling、HTTP/数据库、EPUB 清洗。真正能自己说明后，不再为了“多一个框架”重搭一遍。

每个学习 Spike 的完成标准尽量统一：

- **能画清数据流**：谁输入什么、谁负责什么、哪一步会失败；
- **亲手运行或实现到了目标层级**；
- **有可重复的正/反样本**（至少一次异常场景、一次与基线对照）；
- **能讲出复用 vs 自建的真实取舍**，包括为什么不选择另一条路线；
- **留下一个可在面试展示的最小证据**：代码/测试/命令/简短结论，不堆一套永久学习文档。

**实验收口后，允许结论是“已经学会，但是 Poeticus 生产继续使用旧方案”。** 只有可测的产品收益才推动上线；学习动机本身足够启动有限的实验。

本页随真实学习目标调整，不代替简历，也不声称所有“仓库已经实现”的技术都被个人熟练掌握。
