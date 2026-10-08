# Architecture Decision Records（ADR）

这里维护**仍会约束 Poeticus 架构与数据语义的技术选择**。ADR 只回答「为什么这样选、选了什么、代价是什么、何时重审」，不负责重复当前配置和运行命令。

## 何时写 ADR？

需要在多个有意义的方案间作出、且会持续影响**系统边界、数据所有权、存储语义、可靠性或架构演化成本**的决定，才写一篇 ADR。一条具体参数、一日的实验路线、尚未选定的想法通常不单独写 ADR。

每篇 ADR 保留：

- **Status / Date**：Proposed、Accepted、Superseded 等；已替代的 ADR 不抹去，只补新决策链接。
- **Context / Decision / Alternatives / Consequences**：背景、选择、替代方案和代价。
- **Evidence / Confidence**：哪些事实经过实测，哪些仍是合理推断或临时工作默认值。
- **Origin**：`user-directed`、`AI-proposed`、`joint`、`inherited`，仅说明最初由谁/哪里提出，不表示优劣。
- **Revisit when**：哪类真实变化能触发重新讨论，附 Issue、测试与 Benchmark 来源。

无需为每个章节机械填写空字段。工作参数的事实以代码和 `architecture/` 为准；下一步实验与未决事项写入 Issue / roadmap，而不是把每个可能性编为 ADR。

## 当前 ADR

| ADR | 决定 | 权威范围 |
| --- | --- | --- |
| [0001](0001-separate-text-retrieval-service.md) | 独立运行 Text Retrieval Service | 部署和进程边界 |
| [0002](0002-hybrid-text-retrieval.md) | 多粒度 Dense + BM25 + Work-level RRF | 检索构建与候选语义 |
| [0003](0003-coarse-chronology-fallback.md) | 不把外部语料朝代猜测写回阅读库 | 证据、年代和数据可信度 |
| [0004](0004-private-public-corpus-boundary.md) | 私有来源与公开阅读数据分离 | 数据发布与版权/证据边界 |

## 与其他文档的分工

| 去哪里 | 要找的答案 |
| --- | --- |
| `docs/architecture/` | **现在**的系统组件、数据模型和接口 |
| `docs/development.md` / `docs/deployment.md` | **现在**怎么安装、启动、部署和排障 |
| `docs/corpus/` | EPUB 具体规则与复核操作，不是跨系统 ADR |
| GitHub Issues / `docs/roadmap.md` | 尚未达成决定或等待条件触发的工作 |
| `docs/devlog/` | 当日实验过程和当时还未证实的想法 |
| `docs/releases/` | 当时版本对外发布了什么 |

## 已退役的 Decision Register

此前 `docs/decisions/` 记录了 2026-10-07 和 2026-10-08 两次**阶段性决策快照**，存在一批后来已解决却仍标为 `open/proposed` 的条目。**不能把快照视作今天有效的决策或配置。**

可长期影响架构的决定、证据、Origin 与复审条件已提炼到上述 ADR；当前参数和能力归架构/部署文件，未决工作归 Issue。原始快照在 Git 历史中可完整检索（归档基线 [`4e44f3e`](https://github.com/montricwang/poeticus/tree/4e44f3e96873d1bff885e83faa0f1ae8d7a73c4c/docs/decisions)），不再在当前树重复维护第二套决策真相。

原 `RET-*` / `DEP-*` 记录大致归宿：
- 独立 Serving、2C8G、CPU 单 worker、HTTPS、安全与 readiness → ADR-0001 / `deployment.md`；
- sentence/clause、BM25、FAISS、metadata v2、RRF、模型与实验取舍 → ADR-0002 / `architecture/text-retrieval.md`；
- current-work alias、self-hit、粗 chronology 与唐/南唐历史标签差异 → ADR-0003；
- 公私语料与发布边界 → ADR-0004 / `architecture/corpus-database.md`；
- `rrf_k`、`search_k`、超时、缓存、构建批大小等可调默认值 → 实际配置和当前架构；它们不因当时被 AI 建议就变成架构原则；
- curated RAG、multi-span、Tool Routing 等尚未成熟方向 → `roadmap.md` 与 GitHub Issues。

