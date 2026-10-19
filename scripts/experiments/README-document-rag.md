# Document RAG｜首轮词项检索基线（2026-10-19）

关联 [#133](https://github.com/montricwang/poeticus/issues/133)、外部文献检索 [#237](https://github.com/montricwang/poeticus/issues/237)。

这是 **Document Corpus 离线检索实验**，不属于已经上线的 Poem Retrieval，也没有接入 Agent、外部检索或 LLM。

## 数据与输入

私有语料（不提交到公开 Git）：

```text
../poeticus-data/document-corpus/
├── raw/             四部维基文库导出的 EPUB
├── normalized/
│   └── document_sections_extracted.json
└── evals/
    └── document_rag_seed_v0.1.json
```

四书：《白雨斋词话》《人间词话》《碧鸡漫志》《乐府指迷》。原提取文件共 916 个 section，约 149,070 字。Section 的来源键为 `doc|file|section_id`，避免不同卷的 `section_id` 相撞。每道 Gold Evidence 的引文与指定 section 正文进行原文子串核对。

**证据等级**：这仅确认了本地“评测引文 → 提取后正文”对齐，不等于核对了纸本、异文、作者归属或逐字版本校勘。原 EPUB 转换为该 JSON 的解析脚本尚未纳入仓库，后续应根据原 EPUB 完成可复现导入；本轮不把现有 JSON 称为经过正式规范化的 Corpus。

## 如何运行

在 Poeticus 仓库根目录、Python 环境已安装开发依赖的情况下：

```bash
python -m pytest -q tests/test_document_rag_lexical_baseline.py
python -m scripts.experiments.document_rag_lexical_baseline
```

如果 `python` 不在 PATH，使用仓库的 `.venv/bin/python`。支持 `--corpus`、`--cases`、`--output`、`--top-k`；默认路径由 `backend.data_paths.DATA_ROOT` 决定，可用现有 `POETICUS_DATA_ROOT` 指向其他绝对路径。

报告位于私有 `document-corpus/evals/results/document_bm25_dev_v0.1.json`。保留原始文件 SHA-256、检索配置、各题完整 Top-K 顺序、Gold 命中位置及构建/查询时间；不直接写入公开仓库。

## 这次比较了什么

- BM25：纯 Python 内存实现，使用 **Unicode NFKC + 汉字字符 2/3-gram**（不做简繁转换、词人别名替换或问题改写），检索字段仅 `section.title + section.text`。
- Section 是检索单位，完整父级原文保留在私有 JSON 中；当前没有另建片段切块策略。
- 只执行 16 道 `development / in_corpus / gold_checked` 题目，保留题 `holdout` 与外部无证据题均不参与当前调参。
- 多个 Gold 章节时分别计算 `Recall@5`、任意证据 `Hit@5`、所有必要证据均出现的 `all_gold_at_k`，`MRR@5` 只取第一条相关命中，**不能用它替代跨章节问题的证据完整性**。

## 首次真实运行

| 开发题 | Hit@5 | 全部 Gold 命中@5 | Mean Recall@5 | MRR@5 |
| ---: | ---: | ---: | ---: | ---: |
| 16 | 9/16 = 0.5625 | 8/16 = 0.5000 | 0.5208 | 0.4375 |

例如 `BAI_01` 命中《白雨斋词话》目标条，排名第 2；`CROSS_01` 的跨书双证据在 Top 5 均未命中。具体候选顺序和失败题详见本地 JSON 报告，不在文档中复制 Gold 全文。

**尚未得出全量对照结果**：简繁归一化、Dense、RRF Hybrid、Reranker、外部 API、Prompt/LLM 回答与证据上下文构建。当前 BM25 结果只刻画一种朴素词项检索表现，不足以推论 Document RAG 的优劣。External Retrieval 另按 #237 核查来源质量、版权及版本锚点。

## 第二阶段：Qwen Dense + BM25/RRF Hybrid（实施中）

代码入口：`scripts/experiments/document_rag_dense_hybrid.py`，读取**相同的四书 section、16 道开发题**，使用本地 `Qwen3-Embedding-0.6B`（不联网下载模型）。

- Dense 以 `section.title + section.text` 编码，查询使用模型自带 `query` 提示；文献使用模型自带 `document` 提示；归一化向量精确计算余弦相似度，**不先构建 FAISS**。
- 第一轮 CPU 设置最大 `512 tokens`、16 条保存一批，在模型内以最多 2 条小批量推理。较长 section 会截断，后续需要单独核对这类损失；现阶段尚未 Chunk。
- Hybrid 使用 **Top 50 BM25 + Top 50 Dense → RRF(k=60) → Top 5**。三个方法返回同一来源键，按同一 Gold 计算 Hit@5、所有 Gold 命中@5、Mean Recall@5、MRR@5。
- 保留 4 道有本地 Gold 的 holdout 不参与调参；外部证据题和已提供原文题暂不计入 Retriever 比较。
- 原始 Qwen 文献向量缓存在私有 `../poeticus-data/document-corpus/embeddings/qwen3_0.6b_sections_v01/`，缓存 `spec.json` 记录原文哈希、模型快照、提示与编码配置；按 `batch_XXXX.npy` 逐批复用。实验对照报告位于私有 `document-corpus/evals/results/document_retrieval_comparison_v0.1.json`，**仅在全部向量完成后生成**。

本地命令：

```bash
# 只读单元测试（不加载 Qwen）
.venv/bin/python -m pytest -q tests/test_document_rag_lexical_baseline.py tests/test_document_rag_dense_hybrid.py

# 如 CPU 负载较高，可限制每次新增的向量批次，重复此命令继续剩余数据
.venv/bin/python -m scripts.experiments.document_rag_dense_hybrid --max-new-batches 3

# 已完成全部文献向量后可直接重新评分；未完成则会继续生成剩余向量
.venv/bin/python -m scripts.experiments.document_rag_dense_hybrid
```

**2026-10-19 的实际验证边界**：14 个回归测试通过；使用真实 Qwen、3 条合成文献与 1 题已打通编码→排序→融合→评分→报告。真实四书 916 条向量缓存完成了 **7/58 个批次**，CPU 端尚未完成全部编码，所以**没有 Dense 或 Hybrid 的四书评测分数**。已有 BM25 成绩保持不变；不能把合成 Smoke 的命中率当真实评测结果。编码期间没有停止或重启 Poem Retrieval 服务，也未修改生产接口。
