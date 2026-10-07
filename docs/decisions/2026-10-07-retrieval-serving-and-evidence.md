# Retrieval Serving / Evidence 决策快照 — 2026-10-07

> 这不是架构规范，而是一次决策审计快照。当前实现请看 `docs/architecture/text-retrieval.md`、Issue #119 / #145 和对应 PR。

## A. 已有证据支撑的决定

| ID | Decision | Level | Origin | Why / Evidence | Status | Re-review trigger |
| --- | --- | --- | --- | --- | --- | --- |
| RET-001 | Retrieval 从 Web / Agent 进程中独立成服务边界 | 1 | joint | 本机 Serving 实测单进程 steady RSS 约 5.27 GiB；FAISS + Qwen 明显不适合塞入 Railway Web 进程 | active | Retrieval 资源模型根本改变，或托管平台能稳定承载同等常驻内存 |
| RET-002 | 先本地做常驻 Serving + Benchmark，再决定租服务器 | 1 | AI-proposed | #145 已实际得到启动、RSS、磁盘、单请求和 5 并发数据；避免先租后猜规格 | active | 无；已验证这种顺序有效 |
| RET-003 | FAISS row id 不再通过扫描 JSONL 回查，而使用 compact SQLite metadata store | 1 | AI-proposed | v2 全量 artifact 已验证：853,385 Works / 4,822,054 sentence / 9,425,173 clause，DB 1.828 GiB，build 73.0 s；Serving lookup 正常，陆游 canary 仍 Top-4 | active | metadata DB 体积或 lookup 成为主要瓶颈 |
| RET-004 | sentence + clause 两套 Dense Retrieval 都保留 | 1 | joint | 历史真实 Case 已证明二者互补；陆游 Case clause 明显优于 sentence，蜡烛 Case sentence 更强 | active | 更大 Eval 证明某一路长期没有增量或成本不可接受 |
| RET-005 | 当前不为了经典 transformed-use 排名难看继续调 RRF / pq_m / clause BM25 / reranker | 1 | joint | #143 显示强 LLM 已掌握大量经典互文；陆游 Case 才是更干净的 Retrieval 增量，当前瓶颈不是缺少更多参数 | active | 长尾真实失败明确指向某一组件 |
| RET-006 | `青楼梦好` 保留为 Agent-loop / multi-span bad case | 1 | joint | 单 span 首轮 Retrieval miss；模型实际尝试改 Query；全文其他线索可能共同指向杜牧 | active | multi-span / iterative Eval 得到稳定结论 |

## B. 合理但尚未充分证明的决定

| ID | Decision | Level | Origin | Why / Evidence | Status | Re-review trigger |
| --- | --- | --- | --- | --- | --- | --- |
| RET-101 | 第一台 Retrieval VPS 优先考虑 16 GiB，而不是 8 GiB | 2 | joint | 当时因为 Windows steady RSS 约 5.27 GiB，担心 8 GiB 给 OS / page cache 的余量偏紧 | superseded | 已由 RET-113 替代：先实测 2核8G 的最低可行性 |
| RET-102 | 第一版 Retrieval 节点保持单进程 / 单 worker | 2 | AI-proposed | 多 worker 大概率复制 Qwen + FAISS 常驻内存；本地 5 并发单进程约 2.37 req/s，早期流量可能足够 | proposed | 真实并发需求超过单实例能力，或验证 FAISS / 模型可安全共享内存 |
| RET-103 | 暂时不把 Railway PostgreSQL 搬到 Retrieval VPS | 2 | joint | 不希望数据库与高 CPU / 高 RAM Retrieval 争抢资源，也避免把故障域合并 | proposed | Railway DB 成本、延迟或运维问题出现明确迁移动机 |
| RET-104 | 第一版仍使用 CPU Serving，不上 GPU | 2 | AI-proposed | CPU 已能完成检索；尚无证据证明 GPU 成本能换来必要的产品收益 | proposed | 新 Query 延迟成为真实 UX 瓶颈，且 Profiling 证明主要时间在 encoder / ANN 可被 GPU 有效降低 |
| RET-105 | 未来全文多 span 优先“独立并行召回 → 文档级 evidence 聚合 → 必要时二次检索”，而不是纯串行链 | 2 | joint | 可避免第一个 hypothesis 绑架后续典故；当前 batch Query 延迟增长并非严格线性 | experiment | 《扬州慢》等 multi-span Eval 比较 A/B/C/D 方案 |
| RET-106 | 未来多个 span 应优先在一次 Retrieval 请求内 batch，而不是 Agent 连续发很多独立 HTTP 请求 | 2 | AI-proposed | 当前 Dense channel 原生 batch；1/3/4 Query 的 warm latency 显示有摊薄空间 | experiment | 实现 multi-span API 后测真实吞吐与候选质量 |
| RET-107 | 词话 / 诗话先做“小而精的 curated RAG”，开放 Web Search 负责长尾兜底 | 2 | joint | Poeticus 的评论资料不需要一开始追求全集；精选权威原典主要提供 grounding，Web Search 提供覆盖面 | proposed | 用户问题大量落在 curated corpus 之外，或 Search 质量不足 |
| RET-108 | 不建立一个混合诗词、词话、辞书的万能索引；按 Retrieval Domain / Tool 保持语义边界 | 2 | AI-proposed | 不同问题的检索目标和证据可信度不同，混在一张榜单会降低解释性和结果质量 | proposed | 真实产品表明统一索引反而更有效且能稳定路由 |
| RET-109 | 用户明确追问“借了谁哪一句 / 化用了哪段前代文本”时，若 Corpus Tool 可用，优先 `search_predecessor_texts`，不要先消耗 `lookup_reference` / `lookup_allusion` | 1 | AI-proposed | 首次 E2E 暴露错误路由；修订 Prompt / Tool description 后，同一陆游与姜夔 Case 均以 `text_retrieval` 为 first tool，routing gate 均通过；姜夔首轮弱命中后第二轮仍保持 Corpus Retrieval，并以「十年一觉扬州梦」找回杜牧《遣怀》 | active | 更大自然问题集出现系统性误路由，或未来 Tool 数量增加使 Prompt 路由不再稳定 |
| RET-110 | metadata compact schema 升级为 v2，并拒绝继续加载旧 v1 artifact | 1 | AI-proposed | 全量 v2 已完成重建并被 Serving 正常加载；DB 从约 2.313 GiB 降到 1.828 GiB（约 -21%），build 约 73 s，陆游 canary 仍 Top-4；强制版本门槛确保部署节点不会静默沿用旧 v1 | active | 未来 schema 迁移频率明显上升、全量重建成本不可接受时，再考虑向后兼容 / migration 策略 |
| RET-111 | 第一台 Linux Deployment Spike 候选使用 DigitalOcean SFO3 Basic 16 GiB / 8 shared vCPU / 320 GiB | 2 | AI-proposed | 当时过度围绕 Railway SFO 的网络位置选择海外节点，没有先把国内云作为第一候选；用户明确指出可以优先使用中国云厂商 | superseded | 已由 RET-112 替代 |
| RET-112 | 第一台 Linux Deployment Spike 改用腾讯云上海 8核16G 标准型按量实例 | 2 | joint | 从海外节点改为国内云是正确方向，但规格仍然把“肯定够”误当成“应该先测” | superseded | 已由 RET-113 替代 |
| RET-113 | 第一台 Linux Deployment Spike 从腾讯云上海 2核8G 标准型按量实例开始 | 2 | joint | Windows steady RSS 约 5.27 GiB，说明 8 GiB 有可能容纳单进程，但余量有限；2 vCPU 是否让 Qwen / FAISS 延迟不可接受未知。Spike 应先验证最低可行规格，再按“4核8G → 4核16G”逐档升级，而不是一开始购买 8核16G | experiment | 若 8 GiB OOM / 持续 swap / page-cache 压力明显则升 16 GiB；若 RAM 足够但 CPU 慢则先升 4核8G |
| RET-114 | 当前公开阅读 Corpus 统一向 Agent / Retrieval 注入 `dynasty="宋"` | 2 | joint | 生产库当前只发布 3491 首宋词；首次线上 E2E 因 `dynasty=null` 让元、明后世候选进入 Top-K，而同一陆游 canary 在 benchmark 显式传入“宋”时能看到杜甫目标 | active | 公网 Corpus 开始发布非宋作品，或数据库增加可靠的逐首 dynasty 字段 |

## C. 为了闭环而暂定的默认值

> 这些值最容易在未来被误认为“架构结论”。目前都没有充分证据证明最优。

| ID | Working default | Level | Origin | Why now | Re-review trigger |
| --- | --- | --- | --- | --- | --- |
| RET-201 | `search_k=100` | 3 | inherited / joint | 能覆盖当前 canary，且已与 final Top-K 分离 | 真实 target 系统性落在 100 以外，或 latency / memory 压力出现 |
| RET-202 | `rrf_k=60` | 3 | inherited | 标准稳定默认；当前没有 sensitivity 证据 | Eval 显示排名对该值敏感 |
| RET-203 | Tool 返回 `top_k=8` | 3 | AI-proposed | 候选量不大，足够给 LLM 比较且不会明显膨胀 Context | tool evidence recall / distractor Eval |
| RET-204 | Agent Retrieval HTTP timeout 15 s | 3 | AI-proposed | 为第一版闭环留足余量，没有来自生产 SLO 的依据 | 线上 latency 分布明确后 |
| RET-205 | query-vector cache size 256 | 3 | AI-proposed | 小型 bounded cache，避免无界增长；尚未基于真实重复率选型 | 真实 Query 重复率、RAM 或 cache hit 数据出现 |
| RET-206 | metadata builder batch size 50,000 | 3 | AI-proposed | 构建简单、当前 81 s 可接受 | metadata 重建成本成为问题 |
| RET-207 | Serving `workers=1` | 3 | AI-proposed | 在不知道多 worker 内存放大前选择安全默认 | 在目标 Linux 环境验证进程/线程/共享内存行为 |
| RET-208 | 当前 FAISS `nlist=512 / pq_m=256 / nprobe=64` | 3 | joint | spike 后的可用 serving 候选；pq64 太损失，pq512 尚无真实收益证据 | long-tail Case 被 ANN 系统性漏掉，或目标硬件 latency / RAM 要求改变 |

## D. 尚未解决的问题

| ID | Open question | Level | Origin | 当前已知 | 下一验证 |
| --- | --- | --- | --- | --- | --- |
| RET-301 | 8 GiB VPS 是否能作为单 worker Retrieval 的最低可行规格 | 4 | joint | Windows 本机 steady RSS 约 5.27 GiB；8 GiB 理论可运行，但 Linux allocator / page cache / 峰值余量未知 | 先在腾讯云上海 2核8G 跑同一套 RSS / latency / concurrency benchmark |
| RET-302 | 当前单实例的并发上限与可接受响应时间 | 4 | joint | 本地 5 并发约 2.37 req/s，individual p50 约 1.42 s；这不是生产压测 | 真实 Agent 流量模型 + Linux VPS benchmark |
| RET-303 | 新 Query 的端到端 latency 是否需要优化 | 4 | joint | supplement probe：陆游约 1.68 s、姜夔约 1.64 s、李清照 4 QueryVariants 约 3.38 s；包含 uncached Qwen 与冷 page/cache 效应 | 更多 distinct Query、分阶段 profile；不要只看重复 Query warm cache |
| RET-304 | 全文 multi-span 是否能救回 `青楼梦好`，并改善 transformed-use | 4 | user-directed | 当前单 span miss；理论上《扬州慢》多个独立线索可能形成杜牧 evidence cluster | 专门 multi-span Eval |
| RET-305 | 评论 / 词话 curated corpus 第一批到底选哪些书、需要什么 Chunk 策略 | 4 | user-directed | 当前只形成“小而精 + Search fallback”的产品方向 | 先选约 10 本高价值原典做最小试验，不先做全集工程 |
| RET-306 | Web Search 与 curated RAG 的路由 / 证据权重如何表达给 Agent | 4 | joint | 已明确两者可信度与覆盖面不同，但尚未形成 Tool policy | 等 Search Tool 接入方案确定后做 Eval |
| RET-307 | 外部 Corpus 中同一作品的异本 / 重复记录如何做 self-hit canonical identity | 4 | joint | 真实 E2E 已用完整当前作品，但仍返回另一条陆游《鹧鸪天 送叶梦锡》同句记录；exact full-content fingerprint 不足 | Issue #151 先做 duplicate profiling；不直接按“同作者”粗暴过滤 |

## 这次特别记录的 AI 决策

以下选择最初不是用户主动指定，而是在 AI 推进实现时提出，因此未来复盘应优先允许推翻：

- SQLite compact metadata store 作为第一版 row lookup；
- Retrieval Service 与 Agent 通过 HTTP 解耦；
- Retrieval URL 未配置时隐藏 Tool；
- 单 worker 默认；
- `top_k=8`；
- HTTP timeout 15 s；
- query-vector cache 256；
- metadata batch size 50,000；
- Bearer token 作为第一版服务认证；
- 先做本机 benchmark，再采购服务器；
- 未来按 Retrieval Domain 拆 Tool，而不是万能索引。

其中 SQLite metadata、独立 Retrieval Service、先 benchmark 后租服务器已经获得真实数据支持，可以从“AI 的工作假设”升级为当前工程基线；其余仍按表中的 Level 保留可撤销性。

## References

- Issue #119 — Text Retrieval 主线
- PR #143 — 独立 LLM vs 工具增强 LLM Retrieval 增量评测
- PR #144 — Agent 侧 Text Retrieval Tool / HTTP client
- Issue #145 — 本地 Retrieval Serving 与资源测量
- PR #146 — Retrieval Serving runtime / benchmark
- `retrieval_serving_20261007_1640` — 第一份 Serving Benchmark
- `retrieval_serving_probe_20261007_1651` — uncached Query + fixture self-hit supplement probe
- `agent_retrieval_e2e_20261007_1731` — 首次真实 Agent → HTTP Retrieval Service → Agent E2E（暴露 Tool Routing 问题）
- `agent_retrieval_e2e_20261007_1758` — 修订后 E2E；两条 Case 均 first-tool = text_retrieval，姜夔第二轮 query reformulation 找回杜牧
- Issue #151 — Corpus duplicate / variant self-hit profiling
- Issue #152 — clause metadata 无用 UNIQUE index；v2 全量重建后 DB 1.828 GiB，约比 v1 小 21%
