# Text Retrieval 架构基线

> 状态：2026-10-06，随 #119 / PR #132 建立。本文只记录当前已经确定的职责和数据边界；尚未实施的 Vector DB / ANN 只列为待决事项。

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
sentence Chunk JSONL
↓
Qwen document embedding
↓
Embedding Artifact
↓
未来 Vector Index
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

当前 baseline 为 sentence：

- 在 `。！？!?` 后结束；
- 逗号、分号保留在句内；
- 保留原标点；
- 保存 `work_id`；
- 保存 `[start, end)` Unicode code-point offset，可从 `Work.content` 精确还原。

当前全量结果：

- Work：853,385；
- Chunk：4,822,054；
- 平均 5.651 Chunk / Work；
- 最长 Chunk：132 字符。

sentence 是第一版 baseline，不是永久文学定义。若真实 Retrieval 失败证明粒度过粗，可以从 Work 重新派生 clause，而不改变 Work 层。

## 4. Corpus Chunking 与 Query Strategy 分开

这两个问题不要求采用同一粒度。

**Corpus Chunking** 回答：前代语料以什么单位进入检索索引？  
当前 baseline：sentence。

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

BERT-CCPoem 保留为领域模型反例检查。只有真实 Eval 表明 Qwen baseline 存在值得追查的系统性失败时，才投入专门对照；届时可单独使用更适合它的 clause / 单行粒度，不要求所有模型强行共享一种 Chunk。

## 6. Embedding Artifact

当前全量构建参数：

```text
model: Qwen3-Embedding-0.6B
chunk policy: sentence
dimension: 512
normalized: true
dtype: float16
shard size: 10,000
expected chunks: 4,822,054
```

Embedding 先作为独立离线构建产物保存：

```text
data/output/retrieval/embeddings/qwen3_0.6b_sentence_512/
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

## 8. Eval 策略

不为 Embedding 另造一套独立研究 Benchmark。

正式 Retrieval 建成后，优先复用已经整理的 intertext Eval，观察正确 predecessor source 是否进入可供 DeepSeek 处理的候选范围。

重点不是要求 Retriever 自己 Rank 1 下结论，而是：

> **Retriever 是否把真正值得比较的前代文本稳定带进 Top-K？**

只有真实失败出现后，再按类型判断：

- Corpus coverage；
- Chunk 粒度；
- Query Strategy；
- Embedding 模型；
- chronology；
- lexical / dense hybrid；
- reranker。

不在失败证据出现前同时引入这些复杂度。

## 9. 当前未决定

截至 2026-10-06，以下仍待决定：

- pgvector、FAISS 或其他向量存储；
- Exact Search 与 ANN 的具体切换时机；
- HNSW 参数；
- Query instruction；
- dynasty filtering 的实现位置；
- Top-K；
- Qwen 512 维在真实 intertext Eval 上的质量；
- BERT-CCPoem 是否值得进入生产候选；
- Hybrid / sparse / reranker。

这些内容只有形成真实证据或正式实现后，再更新本文为当前状态。
