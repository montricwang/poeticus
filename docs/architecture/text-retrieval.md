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

第一版倾向于让诗句都可以进入 Retrieval，而不是先用分类器判断“值不值得查”。诗词本身较短，预过滤带来的计算节省有限，却可能在 Retriever 之前造成不可恢复的 Recall 损失。

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
- **deterministic multi-query** 作为下一步：优先比较完整 passage、sentence、clause，而不是先让 LLM 自由改写 Query。

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
