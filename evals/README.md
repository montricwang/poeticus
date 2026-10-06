# Poeticus AI Eval

这里先保留一把很小、能重复使用的尺子。第一阶段只做两件事：

1. 用固定问题比较当前 Poeticus Agent 与“同 Prompt、同模型、禁止工具调用”的对照组；
2. 保存结果，人工看哪些地方确实因为 Tool / Evidence 变好或变坏。

当前不搭完整评测平台，也不做总分、LLM-as-a-Judge、RAGAS 或全量消融实验。

## Dataset

`seed_cases.json` 中每条 Case 只记录：

- 用户输入；
- Tool 是否应当使用；
- 回答至少应覆盖什么；
- 不能无依据声称什么；
- 这道题为什么值得保留。

Case 描述问题本身；某次模型输出属于 Run，不写回 Case。

第一批数据仍是 `draft`。后续发现真实失败时直接补新的 Case；旧 Case 如果本身有问题，标记 deprecated，不静默删除。

## 运行

需要本地已有 `LLM_API_KEY` 等 Poeticus 配置。

只跑一题：

```powershell
python -m scripts.evals.run_seed --case allusion_fenglangjuxu
```

跑全部题并保存结果：

```powershell
python -m scripts.evals.run_seed --output evals/results/seed_run.json
```

每题会比较：

- `control_no_tools`：与当前 Agent 使用同一模型、Prompt 和 Tool Schema，但强制 `tool_choice=none`；
- `current_agent`：走当前 LangGraph Agent，允许它按现有规则调用 Tool。

这不是对所有改动做严格学术消融，只是当前阶段最便宜、最容易解释的一组对照。

## 从私人编者注中挑选候选 Case

当前私人 normalized JSON 仍保留 `content.annotations` 与 `content.commentaries`。先做整体画像，不把几千条文本直接塞进评测集：

```powershell
python -m scripts.evals.profile_editorial_notes
```

默认读取：

```text
data/output/all_normalized.json
```

并在本地生成：

```text
data/reports/eval_editorial_profile.json
data/reports/eval_editorial_profile.md
```

报告分别统计 annotations / commentaries 的覆盖率、每首数量、长度分布、重复项、常见文本特征和词集分布。词集表会同时给出作品数、覆盖率和每首平均元素数，避免把“收录作品多”误当成“注释更密”。\n\n对 annotations 还会额外做一层轻量结构筛选：`headword_colon`、`quoted_source`、`cross_reference`、`long_source_note`、`other`。这只是按文本形态帮助挑候选 Case，不把它包装成可靠的“词义 / 典故 / 化用”语义分类。对冒号前的短词头，还会检查它能否在本词正文直接找到。

这些报告包含商业出版物的少量截断派生文本，只用于本地分析，不能提交到公开仓库。

## 从画像进入候选抽样

完成 annotation 画像后，不继续扩大分类规则，直接从两个相对干净的结构池中抽候选：

```powershell
python -m scripts.evals.build_eval_candidates_10061450
```

默认生成：

```text
data/reports/eval_candidates_10061450.json
data/reports/eval_candidates_10061450.md
```

当前只抽两类，各 30 条：

- `headword_colon`：短词头 + 冒号，且词头能在本词正文直接找到；
- `quoted_source`：编者注末尾带明确作品来源的前人引文。

抽样会在不同词集之间轮转，避免辛弃疾、黄庭坚等大词集淹没候选池。结果只作为人工挑选 Eval Case 的候选，不自动把 `quoted_source` 判定为“化用”，也不自动把 `headword_colon` 判定为“词义解释”。

这类诊断 / 抽样脚本以后默认在文件名后附 `MMDDHHMM` 八位时间戳，避免不同轮次脚本和报告互相覆盖。

### 扩大关系候选样本（10061542）

在 30 条 `quoted_source` 试标之后，下一轮扩大到 100 条关系候选，同时保留 50 条词头候选：

```powershell
python -m scripts.evals.build_eval_candidates_10061542
```

默认生成：

```text
data/reports/eval_candidates_10061542.json
data/reports/eval_candidates_10061542.md
```

这一轮仍然只做抽样，不自动给 `quoted_source` 关系分类。先人工标约 100 条，观察 taxonomy 是否稳定，再决定是否引入 AI 辅助初标。


## Poetry Retrieval Benchmark

Text Retrieval / RAG 的第一步先把 **Retriever 的排序质量**单独测出来，不和 Embedding 模型、向量数据库、ANN 或 Agent 同时耦合。

当前文件：

- `retrieval_corpus_sample.jsonl`：一小批公开诗词片段，只用于验证数据契约；
- `retrieval_cases.json`：Query 与已知 relevant record ids；
- `retrieval_rankings_sample.json`：**人工构造的排序 fixture**，只用于验证指标计算，不代表任何真实模型表现；
- `retrieval.py`：Schema、Corpus 校验、first relevant rank、Recall@K、MRR；
- `scripts/evals/run_retrieval_benchmark.py`：对任意 Retriever 生成的 rankings 统一评分。

先运行合成排序：

```powershell
python -m scripts.evals.run_retrieval_benchmark \
  --rankings evals/retrieval_rankings_sample.json
```

以后 BERT-CCPoem、BGE-M3、Qwen3-Embedding 或 pgvector 只需要输出相同的 `case_id -> ranked_record_ids` 契约，就可以复用同一套指标。

这一层只回答：

> 正确候选有没有被召回，排在第几？

它**不回答**“相似文本是否已经证明直接化用”。Chronology、来源关系判断、Rerank 和最终生成留给后续层。
