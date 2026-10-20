# Poeticus Agent Capability Map

> 初版：2026-10-09。基于 `main` 的代码及已有架构文档建立的**能力基线**，不是工具目录、项目愿望清单或实时部署状态。
>
> 首次核查：[Issue #202](https://github.com/montricwang/poeticus/issues/202)；真实来源与授权状态：[数字人文资源地图](../digital-humanities-resources.md)、[Issue #184](https://github.com/montricwang/poeticus/issues/184)。

## 1. 从用户任务出发，而不是从供应商出发

Poeticus 的目标是帮助用户阅读中国古典诗词，必要时查阅**可追溯的原始资料**，比较不同解释并继续讨论。每次扩展先回答：

1. 用户具体要完成什么文学任务？给一个真实问题或回归 Case。
2. 现有 LLM、Agent、Corpus、Evidence Service 已能完成到哪一步？
3. 缺口发生在**资料、检索、判断、交互**中的哪一层？证据是什么？
4. 有现成资源可合法、稳定复用吗？自建时究竟需要做哪一段？
5. 最小验收标准与停止线是什么？

“能检索到候选”不等于“证实典故或化用”；“网页有搜索框”不等于“有可调用的搜索 API”；“代码实现”不等于“当前部署可用”。

## 2. 能力地图（初版，允许随真实 Case 修订）

| 能力领域 | 典型用户任务 | 现有 Poeticus 能力 | 当前待验证的缺口 / 责任 |
| --- | --- | --- | --- |
| **字词训诂** | “绸缪在这首词里作何解释？” | LLM 可以直接解释；`/api/analyze` 由模型输出 `glosses`；本地可选萌典单词义项查询，另有私有《詩詞曲語辭匯釋》离线 CLI（尚未接 Agent） | **部分具备**：可选萌典及离线词典尚需验证在语境中的义项命中、释义准确与来源授权；先由 [#24](https://github.com/montricwang/poeticus/issues/24) 验证词典增益，不预先接多个 Provider |
| **典故考证** | “‘前度刘郎’是什么故事、有哪些典源？” | `lookup_allusion` → CNKGraph；模型结合当前作品判断 | **已实现查询，质量待评估**：歧义、变体、未命中、实际典源及授权；相关 [#24](https://github.com/montricwang/poeticus/issues/24)、[#32](https://github.com/montricwang/poeticus/issues/32) |
| **文本互文** | “‘片片轻鸥落晚沙’与杜甫有什么关系？” | `lookup_reference`；另有条件开放的 `search_predecessor_texts` → 自建 Poem Retrieval（已启用 Werneror 拼接去重，[PR #286](https://github.com/montricwang/poeticus/pull/286)） | **检索与去重已验收，解释证据仍有缺口**：候选全文上下文、年代标签与“相似≠化用”；[#174](https://github.com/montricwang/poeticus/issues/174)、[#175](https://github.com/montricwang/poeticus/issues/175) |
| **古籍原文查证** | “这句话在《庄子》哪一篇？前后文是什么？” | 新增可选 CNKGraph 古籍短句查询及维基文库搜索/单页读取；仅本地研究、默认关闭，并非通用全文书库 | **待验证**：候选结果能否回读可靠上下文、定位原文并满足来源许可；归 [#184](https://github.com/montricwang/poeticus/issues/184)，不先复制整库 |
| **文学史事实** | “苏轼写这首词时在何处？相关人物是谁？” | 主要依赖 LLM 既有知识和作品上下文；本地可选 DeepSeek Search/Fetch 辅助查证，尚未作为公共服务启用 | **待验证**：高风险年代、人物关系需出处和交叉核验；联网工具仍需真实 Agent 质量与成本验证，CBDB 等仍为候选，见 [#154](https://github.com/montricwang/poeticus/issues/154)、[#184](https://github.com/montricwang/poeticus/issues/184) |
| **历代评论对读** | “张炎与王国维怎样分别评价姜夔？” | 本地开发环境已有 `search_documents` → PostgreSQL/pgvector + BM25 Hybrid；附卷则与 EPUB 位置 | **仅本地实验**：2026-10-20 私有库已扩为六书、1152 节/向量，跨书比较及扩容效果仍无成套 Gold 评测；尚无公开文献阅读入口、正式部署及许可核验；[#133](https://github.com/montricwang/poeticus/issues/133)、[#343](https://github.com/montricwang/poeticus/issues/343)、[#344](https://github.com/montricwang/poeticus/issues/344) |
| **文学分析与对话** | “这首词的句法、意象、声情如何？另一种解释是否成立？” | Agent Prompt + LLM；有短期历史、当前作品/选区及按需工具查询；整首赏析是独立模型调用 | **基本可用，仍需评估**：解释是否忠实于证据、能否比较冲突观点、是否受用户暗示；[#148](https://github.com/montricwang/poeticus/issues/148) |

**分类规则**：上表按用户任务分组，而不是一行对应一个工具、一个数据库或一个独立 Agent；一个 Corpus 可服务多类任务，某类能力也可以组合多种来源。

## 3. 已实现的 Agent 边界

- `backend/ai/graph.py` 采用单 Agent ReAct 流程：`agent → tools → agent`，模型也可以不调用工具直接回答。
- 原有四项 Tool **定义**：`lookup_allusion`、`lookup_reference`、`search_predecessor_texts`、`search_documents`；后两者分别由 Poem Retrieval URL 和本地 Document Corpus 配置启用。2026-10-20 `main` 新增三组默认关闭工具：**CNKGraph 词谱/韵书/古籍/实体研究（5 项）**、**DeepSeek Search/Fetch（2 项）**、**萌典及维基文库（3 项）**。开关、出处核查和限制见 [LangGraph](langgraph.md)、[开发指南](../development.md)。**代码有工具 ≠ 公开部署可用**；部分来源受非商业研究许可约束。
- `backend/config.py` 的 `AGENT_MAX_TOOL_CALLS = 2` 是**单次用户请求累计真实工具调用次数**，不是固定两轮推理；预算耗尽后仍应给出回答。
- `backend/evidence/provider.py` 已有最小 `EvidenceProvider` 接口；不能因为候选变多就提前扩展成所有外部资源的万能 Provider。
- `backend/ai/model.py::analyze_poem` 的整首赏析目前单独调用模型，**并不自动经过上述 Agent 工具循环**。
- 2026-10-14 已在 WSL 真实 HTTP、Cloudflare Tunnel 公网健康与 `poeticus.app` 正式 Agent 问答中验收陆游→杜甫检索及重复合集排除（[#151](https://github.com/montricwang/poeticus/issues/151) 已关闭）。**运行环境仍依赖当前 WSL 与 Tunnel 进程**，未来连通性与故障降级继续按 [#180](https://github.com/montricwang/poeticus/issues/180) 核对。数据流见 [LangGraph 架构](langgraph.md) 与 [Poem Retrieval 架构](text-retrieval.md)。

## 4. 自建、复用与选型判断

**Poeticus 自己掌握**：用户任务与质量标准、证据的内部身份和出处契约、检索候选与文学断言的区别、Agent 工具路由、不同来源的冲突解释、用户能否回到原文。

**外部资源优先承担**：古籍与词话的数字化、字词与典故条目、已有的人物关系资料、成熟的基础检索与文本处理组件。复用前必须检查实际响应、原始来源、维护状态、使用许可、访问限制及故障降级；“非商业研究可用”不能自动推断成“公开产品可用”。

**只自建缺失部分**：若来源提供合法原文但不提供可追溯检索，则自己实现索引与定位；若已有检索命中却缺少上下文，先补证据回读，而非继续找第 N 个搜索 API；若模型判断不当，先改提示词、证据呈现或 Eval，而不是立即换 Corpus。

选型分两步：
1. **调查前**列出一条用户任务与不可妥协的业务证据（如文献名、卷则、原文片段、可回读位置）；此时不冻结供应商依赖。
2. **真实样本验证后**，才确定最小内部 Schema、Adapter 和 Provider 归属。允许一个来源主用、另一个补充、第三个仅作离线评测；不强制同类资源排名。

## 5. 优先级与停止线

**当前仅作初始候选，不是已经通过比较的实施排序**：

- **先完成已实现链路的可用性与证据核查**：[#180](https://github.com/montricwang/poeticus/issues/180) Retrieval 环境验收、[#174](https://github.com/montricwang/poeticus/issues/174) 候选上下文与来源忠实度。
- **然后补真实高频缺口**：[#24](https://github.com/montricwang/poeticus/issues/24) 字词义项/典故证据，或 [#133](https://github.com/montricwang/poeticus/issues/133) 历代评论；以用户 Case 与实际错误选择其一，不因最近听说某 API 就插队。
- **多个证据域已同时出现时再优化路由**：[#154](https://github.com/montricwang/poeticus/issues/154)。先用 Tool description、Prompt、有限预算和回归评测，不预设独立 Planner 或多 Agent。

首次 Map 核查建议控制在**半天至一天**，完成覆盖、现状、缺口和下一步最多 2–3 项建议即可关闭 [#202](https://github.com/montricwang/poeticus/issues/202)。之后每个具体缺口先给半天至一天的限时 Spike，遇到以下任一情况即收口：现有方案已满足最低要求；新资源已明确补足缺口；授权/接口不满足；缺乏真实 Case；预算用尽而证据仍不足（标记“暂缓/待验证”）。

**不做**：穷尽所有数字人文资源、每发现 API 就增加 Tool、提前自建通用古籍平台/Neo4j、把本页改成供应商清单，或在此文档保存大量实验日志。

## 6. 文档分工与更新条件

- **本页**：用户需要什么、现状如何、缺什么、职责归属与选型原则。
- [数字人文资源地图](../digital-humanities-resources.md) / [#184](https://github.com/montricwang/poeticus/issues/184)：供应商、资源、许可及样本验证。
- 具体 Feature / Research Issue：某个能力怎么实验、具体失败与验收。
- [LangGraph 架构](langgraph.md)、[Text Retrieval 架构](text-retrieval.md)：已实现的技术数据流；稳定的重要取舍有必要时另写 ADR。

只有**真实用户任务变化、上线能力变化或有代表性的 Eval 发现**，才修改本页对应行；每次更新写明依据与对应 PR / Issue。避免把尚未验证的候选资源写成既成能力。
