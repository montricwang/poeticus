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

**尚未比较**：简繁归一化、Dense、RRF Hybrid、Reranker、外部 API、Prompt/LLM 回答与证据上下文构建。当前结果只刻画一种朴素词项检索表现，不足以推论 Document RAG 或某种向量模型的优劣。下一轮先用同一语料与冻结题集比较检索算法；External Retrieval 另按 #237 核查来源质量、版权及版本锚点。
