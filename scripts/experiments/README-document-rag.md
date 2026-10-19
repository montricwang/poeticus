# Document RAG｜首轮词项检索基线（2026-10-19）

关联 [#133](https://github.com/montricwang/poeticus/issues/133)、外部文献检索 [#237](https://github.com/montricwang/poeticus/issues/237)。

本文记录 Document Corpus 从离线检索到本地 Agent 问答的分阶段实验。独立于已上线的 Poem Retrieval；本地 `search_documents` 已接入 Agent，但尚未向公网部署，外部文献检索仍单独评估。

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

**2026-10-19 已完成**：916 条向量缓存全量 **58/58 批**，16 道开发题真实对照结果：BM25 Hit@5=9/16、Dense=10/16、Hybrid=11/16；具体逐题结果见 `document_retrieval_comparison_v0.1.json`。真实 Qwen 的编解码与测试均已运行。该成绩衡量检索 Gold 命中情况，不代表模型回答正确率。未改动生产 Agent 或 Poem Retrieval。

## 第三阶段：本地 RAG 完整问答（LLM Only / Hybrid / Agentic Hybrid）

独立入口：`scripts/experiments/document_rag_answers.py`。复用上述原始语料、Qwen 文献向量和 Hybrid，不改生产 Poeticus Agent/Tools/前端。通过现有 `.env` 中的 `LLM_API_KEY`、`POETICUS_LLM_MODEL` 与 `LLM_BASE_URL` 调用真实 LLM API（可能产生费用）。使用同一模型、`temperature=0` 和通用问答提示语；RAG 路线增加文献证据。

- **LLM Only**：直接回答，不检索。
- **Hybrid**：原始问题 → BM25 + Qwen Dense → RRF Top5 → 附带原文与出处后回答。
- **Agentic Hybrid**：同一 LLM 通过 `search_document_corpus` Tool Call 生成 1–2 条补充查询；保留原问题，多条 Hybrid 查询融合排序 → Top5 证据 → 回答。无独立 Planner 服务或别名表。

原文片段有编号、书名、卷次、标题、来源 section key。自动检查只保证**引用编号存在**，不保证被引用的原文能支持相应结论。报告保留查询、证据、回答、检索 Gold 是否命中及耗时；**答案正确性与误读仍待人工审阅**。模型不会看到 Gold 答案或 Gold 引文；仍只跑 16 道 development 题。

```bash
# 单题前台执行，实际调用模型 API
.venv/bin/python -u -m scripts.experiments.document_rag_answers --case-id BAI_06

# 全 16 道开发题：耗时较长，会有真实 API 费用
.venv/bin/python -u -m scripts.experiments.document_rag_answers --all

# 只测指定模式时必须用另一份报告，避免不同条件混合
.venv/bin/python -u -m scripts.experiments.document_rag_answers --limit 2 --modes hybrid --output ../poeticus-data/document-corpus/evals/results/hybrid_only.json
```

报告位于私有 `../poeticus-data/document-corpus/evals/results/document_rag_answers_v0.1.json`，每完成一题原子保存；下次同配置运行自动跳过已完成题。若更换模型、语料、题集或模式，改用新 `--output`。关闭终端可能中止当时尚未完成的那一道题，但此前完成的题目不丢。

**2026-10-19 真实单题 Smoke**：`BAI_06` 的三条模式均真实调用 `deepseek-flash`。LLM Only 回答包含未经证实的概括；原始问题 Hybrid 未命中 Gold，模型回答证据不足；Agentic Hybrid 主动生成“陈廷焯 周邦彦 姜夔 比较 清真 白石”等查询，命中《白雨斋词话》卷二“美成、白石，各有至處”的直接评论，并引用对应编号。这是可核对的单题观察，不代表 16 题全部结果。

**第二道真实跨书 Smoke**：`CROSS_01` 对比沈义父与陈廷焯评姜夔。普通 Hybrid Gold Recall@5=0；Agentic Hybrid 通过查询扩展找到《白雨斋词话》关于“沈伯时讥其生硬”的直接反驳，Gold Recall@5=0.5，但没有找到《乐府指迷》沈义父的原段，模型也明确说明证据不充分。故当前不能声称 Agentic 查询已解决跨书问题。
