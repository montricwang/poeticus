# Text Retrieval 架构基线

> 状态：2026-10-07，随 #119 / PR #132 / #134 演进。本文记录当前已经确定的职责、数据边界和由真实 Retrieval 实验得到的结论；尚未实施的 Vector DB / ANN 只列为待决事项。

## 1. 目标与非目标

Text Retrieval 只解决一个问题：

> **给当前诗词中的一段文本，从前代语料中找出值得让 LLM 继续比较的候选文本。**

它不是文学知识库，也不负责最终证明“这句一定化用了那句”。

```text
当前文本
↓
Text Retriever
↓
Top-K 候选前代文本
↓
DeepSeek / Agent
↓
比较、判断关系、解释证据与不确定性
```

因此，相似度高只是候选信号，不自动等于“来源已证实”。

## 2. 与现有 Evidence 的分工

当前按问题类型区分：

- `lookup_allusion`：人物、故事、典故性短语；
- `lookup_reference`：现有 reference evidence；
- Text Retrieval：当前文本与前代文本之间的候选发现；
- DeepSeek / Agent：综合候选与上下文作最终判断。

不把所有文学证据统一塞进一个万能向量库。

## 3. 离线 Corpus Pipeline

当前外部 Retrieval Corpus 使用 Werneror/Poetry：

```text
Werneror CSV
↓
Work JSONL
↓
sentence / clause Chunk JSONL
↓
Qwen document embedding
↓
Embedding Artifact
↓
未来 Vector / Lexical Index
```

### Work

第一版字段：

```text
work_id
title
author
dynasty
content
source
source_record_id
```

`work_id` 用于 Chunk 回查整首作品；`source` / `source_record_id` 保留外部来源可追溯性。

### Chunk

当前保留两种检索粒度：

**sentence**

- 在 `。！？!?` 后结束；
- 逗号、分号保留在句内；
- 4,822,054 Chunk；
- 平均 5.651 Chunk / Work；
- 最长 132 字符。

**clause**

- 在逗号、分号和句末标点处分开；
- 9,425,173 Chunk；
- 平均 11.044 Chunk / Work；
- 最长 34 字符。

两者都保留原标点、`work_id` 与 `[start, end)` Unicode code-point offset，可从 `Work.content` 精确还原。

真实 Exact Retrieval 已证明两种粒度互补：当互文只落在 sentence 的一部分时，clause 可以避免上下文稀释；但当化用压缩了同一 sentence 中两个 clause 的信息时，sentence 反而能保留必要上下文。因此当前不再把 sentence / clause 看成二选一，而把它们作为多粒度 Retrieval 的两个候选层。

## 4. Corpus Chunking 与 Query Strategy 分开

这两个问题不要求采用同一粒度。

**Corpus Chunking** 回答：前代语料以什么单位进入检索索引？  
当前保留：sentence + clause。已有真实案例表明两者互补，暂不继续增加更多粒度。

**Query Strategy** 回答：当前正在阅读的一整首诗词，哪些片段需要发起 Retrieval？

第一版不先让 LLM 改写 Query，而是确定性地产生三层候选：

```text
用户选中 / 当前片段
├─ passage：保留完整上下文
├─ sentence：按 Corpus sentence policy 切分
└─ clause：按 Corpus clause policy 切分
```

Query side 与 Corpus side 复用同一套 sentence / clause 边界规则，避免索引切分和查询切分静默漂移。完全相同的 query text 只执行一次搜索，但保留它来自 passage / sentence / clause 哪些位置的 provenance；例如只有一句且没有逗号的短句，不会因为三层策略重复搜索三次。

这一层只负责生成稳定 Query Plan；Dense / Lexical fan-out、Candidate Fusion 和 chronology filtering 仍属于后续层，不在 Query Planner 内耦合。

### Query Fan-out

Query Plan 之后增加独立执行层：

```text
Query Plan
├─ Dense sentence channel
├─ Dense clause channel
├─ Lexical sentence channel
└─ 未来可增加 Lexical clause / ANN channel
      ↓
per-query × per-channel ranked results
```

Fan-out 层只负责把同一批**去重后的 Query**交给每个已配置的 Retrieval channel，并保留：

- query text 与 passage / sentence / clause provenance；
- channel identity；
- retrieval method（Dense / Lexical）；
- corpus chunk policy（sentence / clause）；
- 各 channel 自己的 rank 与 raw score。

这里有两个刻意的边界：

1. **Query 粒度与 Corpus Chunk 粒度继续独立。** passage Query 也可以查 sentence / clause Corpus；是否有价值由后续 Eval / Fusion 判断，而不是在 fan-out 前写死路由。
2. **channel 必须提供 batch-oriented `search_many`。** 一个 channel 一次接收全部 unique query，避免未来 Dense backend 为每条 query 反复加载模型或重复建立连接。

Fan-out 层不归一化 BM25 / cosine，也不做候选去重；这些属于下一层 Candidate Fusion。当前 Exact Search 与 SQLite FTS5 仍是诊断 / baseline 实现，不在这一层反向绑定生产接口。

第一版仍倾向于让诗句都可以进入 Retrieval，而不是先用分类器判断“值不值得查”。诗词本身较短，预过滤带来的计算节省有限，却可能在 Retriever 之前造成不可恢复的 Recall 损失。

## 5. Embedding 模型

第一版默认：

```text
Qwen/Qwen3-Embedding-0.6B
```

选择它是为了先获得一个现代、中文能力强、许可清楚、支持 Matryoshka 降维的默认 Retriever，不代表已经证明它在古典诗词互文检索上优于所有模型。

当前编码约定：

- Corpus Document：直接编码文本；
- Query：未来可使用固定 Retrieval instruction；
- 两者最终进入同一个可比较向量空间；
- Query instruction 尚未冻结。

BERT-CCPoem 作为领域模型 challenger。clause-level Artifact 已完成，并与 Qwen clause 用同一批真实互文案例对照。当前两个代表性案例中，Qwen / BERT 各有小幅胜负，但差异远小于 sentence / clause 粒度变化带来的排名变化，因此暂时没有证据支持把 BERT-CCPoem 升为生产候选；它保留为实验对照即可。官方实现对正文 token 做 mean pooling（排除 [CLS] / [SEP] / padding），本项目实验实现保持这一口径。

## 6. Embedding Artifact

当前已完成的 sentence baseline：

```text
model: Qwen3-Embedding-0.6B
chunk policy: sentence
dimension: 1024
normalized: true
dtype: float16
shard size: 10,000
chunks: 4,822,054
```

当前新增对照构建：

```text
Qwen3-Embedding-0.6B + clause + 1024d
BERT-CCPoem v1.0 + clause + 512d
```

两套 clause Artifact 都从同一份 clause Chunk JSONL 生成，便于比较模型差异；sentence Artifact 保留，便于比较 Chunk 粒度差异。

Embedding 先作为独立离线构建产物保存：

```text
../poeticus-data/output/retrieval/embeddings/qwen3_0.6b_sentence_1024/
├─ manifest.json
├─ shard_00000.npy
├─ shard_00001.npy
└─ ...
```

manifest 绑定：

- 输入 Chunk 文件 SHA256；
- 模型 fingerprint；
- model id；
- dimension；
- dtype；
- normalize；
- shard size；
- expected / completed chunks；
- 每个 shard 的范围和 SHA256。

生成过程采用分片、原子写入和断点续跑；参数或输入变化时拒绝与旧结果混用。

核心原则：

> **Embedding 是昂贵但可复用的构建资产；Vector DB / ANN Index 是它的部署形式。**

以后更换 pgvector、FAISS 或重建 ANN，不应因此重新做全量模型推理。

## 7. 时间顺序

Text Retrieval 的产品问题是寻找“前代”文本，而不是任意时代的相似文本。

因此 chronology 至少需要参与最终候选约束，但第一版不建立复杂年代知识库。当前可依赖的基础 metadata 是 dynasty；同朝代的精确先后仍可能不确定，应允许 LLM 输出不确定性。

具体采用 ANN 前过滤、ANN 后过滤还是分区索引，等待真实 Vector Index 方案确定后再决定。

## 8. 语料文本不是最终权威文本

Werneror/Poetry 适合作为大规模候选发现语料，但不能把其中的正文自动当成最终可引用的权威版本。

本轮 Exact Retrieval 已遇到实际例子：王维《渭城曲》在当前语料中出现为“客舍青青杨柳春”，而我们原先用于 Eval 的常见版本是“客舍青青柳色新”。这类差异可能来自版本异文、录入来源差异或语料错误，单靠 Retrieval 本身无法判定。

因此系统边界明确为：

- Retrieval 命中 = 候选证据，不等于原文已经核定；
- 如果候选只用于继续比较，可以先进入 DeepSeek / Agent；
- 如果最终回答要把某句明确说成“某作者原文”或据此判断化用关系，且文本存在冲突、异常或来源不明，应再查可靠外部来源核对；
- 不要求每条候选都联网复核，只有候选将被当作关键证据时才增加这一步。

这也意味着后续 Retrieval 结果应保留 `source` / `source_record_id`，让模型和用户知道当前文本来自哪个语料版本，而不是把语料内容包装成无来源的事实。

## 9. Eval 策略

不为 Embedding 另造一套独立研究 Benchmark。

正式 Retrieval 建成后，优先复用已经整理的 intertext Eval，观察正确 predecessor source 是否进入可供 DeepSeek 处理的候选范围。

重点不是要求 Retriever 自己 Rank 1 下结论，而是：

> **Retriever 是否把真正值得比较的前代文本稳定带进 Top-K？**

当前两个代表性结果已经说明 Chunk 粒度是一级变量：

- “片片轻鸥落晚沙” → 杜甫“片片轻鸥下急湍”：Qwen sentence rank 445，Qwen clause rank 2；
- “蜡烛到明垂泪” → 杜牧“替人垂泪到天明”：Qwen sentence rank 1，Qwen clause rank 10。

因此下一阶段优先保留 sentence + clause 多粒度召回，而不是继续扩大 Embedding 模型比较。

只有真实失败出现后，再按类型判断：

- Corpus coverage；
- Chunk 粒度；
- Query Strategy；
- Embedding 模型；
- chronology；
- lexical / dense hybrid；
- reranker。

不在失败证据出现前同时引入这些复杂度。

## 10. 当前未决定

截至 2026-10-07，以下仍待决定：

- pgvector、FAISS 或组合式向量后端；
- Exact Search 与 ANN 的具体切换时机；
- HNSW / IVF 等索引参数；
- Query instruction；
- chronology filtering 的最终实现位置；
- Top-K 与多粒度候选融合策略；
- Lexical Retrieval 的具体实现；
- Hybrid / reranker 是否有必要。

当前 Lexical baseline 倾向采用 **character n-gram + BM25**：character n-gram 负责适配古诗近似字面复用，BM25 负责词项级排序。是否需要古汉语分词器，留给真实 Eval 决定。

这些内容只有形成真实证据或正式实现后，再更新本文为当前状态。


## Artifact 对照检索

Clause 构建完成后，Retrieval Eval 不再为不同模型维护三套搜索代码。新增 manifest-driven 搜索入口：

```text
Artifact manifest
→ 识别 model / chunk_policy / dimension
→ 选择对应 Query Encoder
→ 使用同一 chronology filter / probe / Exact Search
→ 输出同构结果
```

支持：

- Qwen3-Embedding-0.6B + sentence；
- Qwen3-Embedding-0.6B + clause；
- BERT-CCPoem v1.0 + clause。

`scripts/retrieval/compare_artifacts.py` 用同一个已知互文案例依次跑三套 Artifact，最终横向比较 `best_probe_rank` 与 `best_probe_cosine`。它是诊断工具，不是新的 Benchmark Pool；仍然复用既有真实互文案例。


## Lexical Retrieval baseline

Dense Retrieval 之外，当前增加一条独立的字面召回链：

```text
原文
→ character 2-3 gram
→ SQLite FTS5 inverted index
→ BM25 ranking
```

这里把两个层次分开：

- character n-gram 决定“文本如何变成检索词项”；
- BM25 决定“这些词项如何参与稀疏检索排序”。

第一版使用 character 2-3 gram，不先依赖古汉语分词。标点作为边界，不生成跨标点 n-gram。这样优先适配诗词中一两字改写、局部近似引用等模式，同时保留后续比较专用分词器的空间。

当前后端先用 Python 自带 SQLite FTS5：

- 直接提供 inverted index 与 BM25；
- 不新增独立搜索服务；
- 可以在完整 Werneror sentence / clause Corpus 上建立真实索引；
- 索引产物继续放在 `../poeticus-data`，不进入 Git。

这只是 lexical baseline 的部署实现，不把 SQLite 预设为最终生产搜索后端。后续重点看真实 Recall、索引大小、构建时间和查询延迟，再决定是否需要 Elasticsearch / OpenSearch 等更重的搜索基础设施。

Lexical 与 Dense 仍然是两条独立召回链，只有真实结果证明互补后才进入 Candidate Fusion。


## Lexical / Hybrid 的当前取舍

围绕 BM25 还能继续增加分词、归一化、查询扩展、字段权重、参数变体和重排等大量组件。当前不把这些可能性一次性做成“搜索引擎全家桶”，而按真实互文 Case 购买复杂度。

### 已经采用

- **character 2-3 gram + BM25**：当前 lexical 主力；已在强字面复用 Case 上证明增量；
- **标点作为 n-gram 边界**：避免跨标点生成无意义 term；
- **sentence + clause Corpus 粒度**：真实 Case 已证明互补；
- **deterministic multi-query**：先生成 passage / sentence / clause Query Plan；三层切分复用 Corpus policy，相同文本去重但保留来源位置。下一步再把 Query Plan 接入 Dense + Lexical fan-out。

### 下一阶段优先候选

**RRF（Reciprocal Rank Fusion）** 是第一版 Candidate Fusion 的优先候选。

原因是 Dense cosine、BM25 score、不同 query / chunk 粒度的分数并不在同一尺度。第一版若直接做加权分数，需要额外定义归一化和权重；RRF 只使用各路排名，能先回答“多路候选能否稳定合并”这个更基本的问题。

是否正式采用 RRF，等 deterministic multi-query 的真实结果出来后再决定。

### 有价值，但需要真实证据后再做

- **检索字段归一化**：繁简、明确异体字可以作为独立 retrieval representation；原始文本必须继续保留，不能静默改写 Corpus。先画像实际差异，再决定是否实施；
- **词级分词 + n-gram 多字段**：只有 character n-gram 的真实结果出现大量短片段噪声或系统性漏召回时，再比较古汉语分词方案；
- **位置 / 邻近信号**：若正确候选已进入 Top-K，但大量偶然共享 n-gram 的结果排在前面，可增加顺序或邻近约束；
- **专门 reranker / Cross-Encoder**：只有 Candidate Fusion 后的候选排序仍明显影响 DeepSeek 可见范围时再引入。

### 当前明确不做

- edge n-gram：主要服务前缀搜索 / autocomplete，与互文候选发现无直接证据；
- 拼音字段：当前任务不是输入法容错，同音扩展更可能扩大噪声；
- 全局同义词 / 意象词扩展：容易把“寻找前代文本来源”漂移成“寻找主题相似诗句”；
- 字级 unigram：高频单字噪声大，当前没有证据证明收益；
- fuzzy / 拼写纠错：不是当前互文召回的主要失败类型；
- BM25+ / BM25L / DFR / Query Likelihood 等 ranking 变体：现有 BM25 尚未暴露需要更换打分模型的真实失败；
- LTR / learned sparse（如 SPLADE 一类）：当前缺少足够训练标签，也没有证据支持增加模型与索引复杂度。

原则仍然是：**先把 Query Strategy、候选融合和 chronology 这些已经由真实 Case 暴露的问题解决，再优化更细的 lexical 组件。**


### Candidate Fusion：Work-level RRF

Query Fan-out 之后，各路结果不能直接比较 raw score：

- Dense 使用 cosine；
- Lexical 使用 BM25；
- 不同 Query 长度、不同 Chunk policy 的分数分布也可能不同。

第一版 Candidate Fusion 因此采用 **Reciprocal Rank Fusion（RRF）**，只使用每一路候选的 rank：

```text
contribution = 1 / (60 + rank)
```

这里的融合单位不是 `chunk_id`，而是 **Work**。

原因是 sentence / clause 是同一作品的不同观察窗口。同一来源在 sentence index 与 clause index 中天然拥有不同 `chunk_id`；若按 Chunk 融合，它们永远不能相互支持。反过来，如果直接让同一作品的多个 Chunk 在单一路榜单里全部计分，长作品又会因为 Chunk 更多而获得结构性优势。

所以当前规则是：

1. 每一个 `QueryVariant × RetrievalChannel` 视为一条独立 ranked list；
2. 同一 ranked list 内，同一 Work 只取最高 rank 的 Chunk 产生一次 RRF contribution；
3. 同一 Work 若在不同 Query、Dense / Lexical、sentence / clause 路径中出现，则 contribution 累加；
4. Fused Candidate 保留每一次 list-level support 的 Query provenance、channel、best Chunk、rank 与 raw score，供后续 DeepSeek 判断；
5. passage / sentence / clause、Dense / Lexical 第一版全部同权，不预设人工权重。

这使 RRF 回答的是：

> **哪些前代作品被多种独立检索视角反复支持？**

而不是把 BM25 与 cosine 强行变成一个统一数值。

当前 `rrf_k=60` 只是稳定的第一版常数，不把它当成需要调参的文学参数。只有真实 Eval 显示候选排序对它敏感时才重新讨论。

RRF 之后仍需独立处理 chronology、当前作品 self-hit 与明显后世候选；这些规则不塞进 Fusion score。


### Candidate Eligibility：只删除明确不可能的前代候选

RRF 得到的是“多路 Retrieval 共同支持的候选作品”，但产品语义仍要求寻找当前作品的**前代**文本。

当前只有粗粒度 dynasty metadata，因此不能把朝代标签当成作者 / 作品精确年代。第一版 Candidate Eligibility 采用保守策略：

```text
当前作品自身
→ reject: self_hit

候选朝代明显晚于当前作品朝代
→ reject: clearly_later

候选朝代明显更早
→ keep: clearly_earlier

同朝
→ keep: same_dynasty

并行 / 重叠政权、跨朝过渡标签
→ keep: overlapping

缺少或未知朝代
→ keep: unknown
```

也就是说，**只删除当前 metadata 能高置信度判定为不可能是前代的候选**。

这样刻意避免重演一个已观察到的错误：范仲淹与李清照都标为“宋”，如果直接使用严格 `before_dynasty=宋`，真正的范仲淹前代来源会在 Retrieval 阶段被整个删掉。

Candidate Eligibility 因此与当前诊断脚本中的严格朝代过滤分开：

- Exact / BM25 诊断命令继续保留原先的 strict `candidate_prior_dynasties()` 行为，便于复现实验；
- 产品候选层使用 coarse interval relation，只排除 self-hit 与 `clearly_later`；
- 同朝 / overlap / unknown 的 chronology status 保留给 Agent，允许回答“先后尚需核实”。

长期若补齐 author / work dates，再把这些 uncertain case 向更精确 chronology 收敛，而不是继续扩张 dynasty 字符串特例。

这一层当前放在 Fusion 之后定义产品语义；未来生产 Retriever 若支持 metadata pre-filter，可以把同一 eligibility predicate 下推到检索后端以提高效率和改善 eligible-rank 语义，但不能改变这层的判定规则。


### Product Service：先固定编排边界，再选择索引后端

截至 2026-10-07，Query Plan、Fan-out、Work-level RRF 与 Candidate Eligibility 已经形成稳定职责，因此增加产品侧 `TextRetrievalService`：

```text
text
→ Query Plan
→ Retrieval Channels
→ Work-level RRF
→ Candidate Eligibility
→ final candidates
```

这个 Service **不绑定存储实现**。它只依赖 `RetrievalChannel.search_many()` 契约，因此后续 Dense channel 可以由 FAISS、pgvector 或其他 ANN 实现；Lexical channel 也可以继续由 SQLite FTS5 或未来其他倒排后端实现。

Service 当前固定的产品语义：

- per-channel Top-K 先限制每一路召回池；
- RRF 对这个有界候选池做完整融合；
- Eligibility 在完整 fused pool 上过滤 self-hit / clearly-later；
- **最后**才截 final Top-K，避免 self-hit / 后世候选提前占满最终名额；
- 无候选时返回 `no_hit`，而不是伪造弱候选；
- backend / index unavailable 仍应作为错误与 `no_hit` 区分，具体 failure contract 等真实 channel 落地时定义。

#### 为什么暂不直接把现有 PostgreSQL 变成 pgvector

当前 Railway production 实际资源画像：

- `poeticus-web` 无持久 Volume；
- PostgreSQL Volume 当前约 500 MB；
- Qwen 1024d float16 sentence Artifact 约 9.2 GiB；
- Qwen 1024d float16 clause Artifact 约 18.0 GiB；
- 两套原始 Dense Artifact 合计约 27.2 GiB，尚未计算 ANN / metadata / database overhead。

因此“项目已经有 PostgreSQL，所以直接上 pgvector”不是一个零成本延伸。后端选择必须单独做部署 spike，比较真实：

- 索引磁盘体积；
- 查询延迟；
- Recall；
- metadata filtering；
- Query embedding 运行方式；
- Railway Volume / memory / service topology；
- 重建与发布流程。

在这个 spike 完成前，`TextRetrievalService` 与 Agent Tool contract 都不应反向绑定某一种 Vector DB。
