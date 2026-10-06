# Poeticus Retrieval 实验

> 当前阶段：#119 的 Retrieval Benchmark 基线。Corpus / Chunk / 指标契约已经建立；开始 Embedding 前，先固定一组公开可复核的真实 Case，并验证 Ground Truth 确实存在于所选 Corpus。这里不是生产 Agent 架构。

## 1. 为什么先拆出 Retrieval

当前 `lookup_reference` 已经能处理一部分保留明显字面锚点的前代成句，但对高度压缩、反用和大幅重组仍然不稳定。

下一阶段先回答一个更窄的问题：

> 给定一条诗句，现成 Embedding 能不能把我们已知的前代候选排到 Top-K？

在这个问题回答以前，不引入 pgvector、HNSW、Hybrid Search 或 Reranker。

## 2. Corpus Contract

外部语料先转成两层对象：

```text
CorpusWork
  └─ CorpusChunk
```

Work 保存来源身份、作者、朝代、题目和原始 paragraphs；Chunk 保存检索文本、chunk policy、父作品 ID 和正文位置。

这样可以保持旧项目里已经验证过的原则：

> chunk 用于检索，parent work 用于回查上下文。

第一版只提供 `chinese-poetry` adapter。它既可以读取一个 JSON 文件，也可以读取某目录第一层中**符合 file pattern 的 JSON**；不会递归进入 `error/` 等旁支目录。目录里常同时存在 `authors.*.json` 与作品文件，因此批量导入时不要使用无约束的 `*.json`。

外部仓库只作为本地输入，不 vendoring 到 Poeticus。

## 3. Chunk Policy

当前保留三个实验变量：

- `clause`：按 `，。！？；` 切；
- `sentence`：按 `。！？` 切；
- `clause_pair`：相邻两个 clause 的滑动窗口。

这三个策略暂时没有“正确答案”。后续让同一 Retrieval Benchmark 决定哪种粒度对化用检索更有效。

## 4. 构建本地实验 Corpus

例如已经在本地 clone 了 chinese-poetry：

```powershell
python -m scripts.retrieval.build_corpus \
  --input D:\data\chinese-poetry\全唐诗 \
  --dynasty 唐 \
  --genre poem \
  --file-pattern "poet.tang.*.json" \
  --chunk-policy clause
```

默认输出到被 Git 忽略的：

```text
data/reports/retrieval_corpus/
  works.jsonl
  chunks.clause.jsonl
  manifest.clause.json
```

当前不会下载模型，也不会生成向量。

## 5. Retrieval Benchmark Contract

`evals.retrieval` 把模型无关的 Dataset 与 Run 分开：

```text
Dataset
  query
  expected target(s)

Run
  retriever name
  ranked hits
```

指标只回答 Retrieval 问题：

- 正确目标第一次出现的 rank；
- Recall@1 / @5 / @20；
- MRR。

Expected Match 使用“核心目标文本 + 可选作者 / 标题 / source_record_id”，因此同一个 benchmark 可以公平比较 clause、sentence 和 clause_pair；只要较大的 chunk 包含目标句，也可判为召回。

公开的第一版真实 Dataset 位于：

```text
evals/retrieval_cases.json
```

人工 Ground Truth 的公共核验依据单独放在：

```text
evals/retrieval_cases.md
```

它和合成单元测试不同：合成数据只证明指标代码能工作，真实 Dataset 才是后续比较 Retriever 的考题。

### 先检查 Corpus coverage

在跑任何模型前，先确认当前实际生成的 chunk 中确实存在 Dataset 的正确目标：

```powershell
python -m scripts.retrieval.validate_dataset_coverage \
  --chunks path\to\chunks.clause.jsonl
```

如果实验 Corpus 来自多个 shard，可以重复传入 `--chunks`。

coverage 缺失说明“这把尺子的正确答案不在当前题库里”，属于 Corpus / normalization 问题；不能把它记成 Retriever miss。第一版不自动做繁简转换或异文统一，让这些差异先在 coverage 阶段显出来。

如果已经有某个 Retriever 的 Run JSON，再计算 Retrieval 指标：

```powershell
python -m scripts.retrieval.evaluate_run \
  --dataset evals\retrieval_cases.json \
  --run path\to\run.json
```

## 6. 下一步

当真实 Dataset 对选定 Corpus 的 coverage 检查通过后，才进入 Embedding Baseline：

1. 按 BERT-CCPoem 官方批量实现的 pooling 方法生成 embedding；
2. 选择一个现代通用 Embedding baseline；
3. 全部先用 Exact cosine retrieval；
4. 用同一 Dataset 比较模型与 chunk policy。

只有确认 Embedding 本身有增量后，才进入 pgvector / ANN。
