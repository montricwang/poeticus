# ADR-0002：采用多粒度 Hybrid Text Retrieval

- **Status:** Accepted
- **Date:** 2026-10-08
- **Scope:** Retrieval candidate generation
- **Origin:** joint（两种粒度与实际互文复盘）；AI-proposed（compact metadata store、若干检索实现默认）
- **Confidence:** Sentence / Clause 互补性和现有生产链路经真实案例验证；全面长尾召回率与最优参数**尚未**证明
- **Related:** #119、#143、#145、#151、#152、PR #146

## Context

Poeticus 需要在 Werneror/Poetry 约 853,385 首作品中找出前代文本候选。仅比较整句或仅做字符精确匹配都会遗漏某些互文：作品既有局部片段化用，也有跨短分句压缩线索；原文异文与编校差异也会影响检索。

早期真实 Case 表明 Sentence 与 Clause 有互补性：一例陆游化用中 Clause 明显优于 Sentence；另有线索跨越两个 Clause 时 Sentence 更稳定。只观察模型名字、单一相似度或两三个样本排名，不能证明一个架构普遍最优。

## Decision

离线数据和线上候选检索分层：

1. Werneror Work 先切出带原作 `work_id`、`[start,end)` 来源位置的 Sentence 与 Clause Chunk。
2. 分别使用 Qwen3-Embedding-0.6B 的 **1024 维、L2-normalized** 向量生成 Sentence/Clause Dense Artifact；线上使用各自的 FAISS IVFPQ 压缩索引。
3. 增加 Sentence **character 2–3 gram BM25** 作为字面相近文本的补充。不为当前版本再增加 Clause BM25。
4. Query 按可复用的语义边界构造 deterministic Query Plan，Dense 与 BM25 分路召回；以 **Work-level RRF** 合并候选，不强行归一化不相同的 BM25 和 cosine 原始分数。
5. 根据当前作品的 alias、自命中及可判定的时代先后进行 Candidate Eligibility。对于缺少可靠年代数据的情况，参见 [ADR-0003](0003-coarse-chronology-fallback.md)。
6. FAISS global row 的作品信息通过 compact SQLite metadata 批量回查，**不在在线请求中扫描全量 JSONL**；Serving 对旧 metadata schema v1 显式拒绝，而不是静默当作 v2 加载。

当前已有两套 FAISS IVFPQ（`nlist=512 / pq_m=256 / pq_bits=8 / nprobe=64`）、Sentence BM25 与 metadata v2。这些是**当前验证过可运行的配置**，不是不可改变的算法公理；运行事实与接口以 [Text Retrieval 架构](../architecture/text-retrieval.md) 为准。

## Evidence

- **互补召回**：某些 partial reuse 的句内无关上下文会稀释 Sentence；反之，将有关线索切成两个 Clause 也会丢失上下文。见 [2026-10-07 开发日志](../devlog/2026-10-07.md)、[Retrieval 架构](../architecture/text-retrieval.md)。
- **模型对照**：BERT-CCPoem Clause 512d 是实验 challenger。在已核实的有限 Case 上与 Qwen 互有胜负，没有稳定优势，**因此不升为生产模型**。这不代表 BERT 在所有数据上较差。
- **压缩成本**：Exact-neighbor Recall@20 的早期 IVFPQ Spike 在 `pq_m=64/128/256` 下，Sentence 为 `0.397/0.576/0.764`，Clause 为 `0.516/0.655/0.815`；`pq_m=256` 两套 Index 投影约 3.509 GiB。增加 nprobe 不能显著弥补 PQ 表示误差。这是 ANN 对精确向量近邻的重现，**不是文学关系召回率**。
- **metadata v2**：全量 Work/Sentence/Clause 映射数据库约从 2.313 GiB 降至 1.828 GiB，重建约 73 秒，并经 Serving 和真实 canary 读取验证。
- **产品 Eval 停止线**：经典、广为人知的化用本身可能已由 LLM 参数记忆正确回答；只有候选确实出现在 Tool 结果里，才能归因于 Retrieval 的增益。由此不继续围绕个别排名惯性调整 PQ、RRF、Reranker。

## Alternatives and trade-offs

- **只用 Sentence / 只用 Clause**：减少索引成本，但损失真实观察到的互补候选。
- **只用 Dense / 只用 BM25**：分别易受强字面变体与语义改写影响；当前混合成本可以接受。
- **单一分数加权**：BM25、cosine、不同粒度不共尺度，先使用 Rank-based RRF。
- **pgvector / 更复杂 ANN 体系**：并非不可能；当前 FAISS + SQLite 的服务体积、质量、稳定性已经满足早期需求，无充分证据要求新基础设施。
- **更大模型、Clause BM25、reranker、GPU、复杂语义 Query 扩展**：暂不引入；先等可归因的真实长尾失败。

代价是需要维护多个索引、模型和 Manifest；离线 Embedding 很大且重算昂贵，但它与线上精简的 Serving Index 各自承担不同的生命周期。

## Revisit when

- 足够多的真实 Eval Case 证明某个通道没有稳定增量；
- 明确出现全量 ANN Approximation 造成的长尾候选漏召回；
- 内存、延迟或更新成本使当前多索引方案不可接受；
- 候选虽可见但 Agent 仍持续选错证据，应优先检查 Eval 与工具语义，而不是默认再加索引。

开放的 duplicate/variant self-hit 调查由 #151 跟踪；其余新能力由 [roadmap](../roadmap.md) 和具体 Issue 决定。
