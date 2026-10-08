# Poeticus AI Eval

> 当前基线：v0.3.0（2026-10-08）。本目录同时包含 Seed Eval、Retrieval Increment Eval 的小规模可重复 Case；完整线上 E2E 验收记录另见 [v0.3.0 Release](../docs/releases/v0.3.0.md) 与 [开发日志](../docs/devlog/2026-10-08.md)。

Eval 用来回答**哪一类问题改善了、改善是否真的来自工具证据、哪里仍会失败**。当前不搭通用评测平台，不将小样本 Case 得分包装成全站准确率，也不默认引入 LLM-as-a-Judge / RAGAS。

## 当前评测层次

| 层次 | 对象 | 主要判断 |
| --- | --- | --- |
| 单元 / Contract 测试 | Query Plan、RRF、Eligibility、Retrieval Client/Server、HTTP 契约等 | 确定性行为与接口是否回归（见 `tests/`） |
| Seed AI Eval | `seed_cases.json`、`scripts.evals.run_seed` | 当前 Agent 使用 Tool / Evidence 的选择和回答表现 |
| Retrieval Increment Eval | `retrieval_increment_cases.json`、`scripts.evals.run_retrieval_increment` | 独立 LLM 与一次 Retrieval Tool 增强的增量、目标候选是否确实由工具提供 |
| 真实 Agent / 生产 E2E | Tool routing、必要时二次 Query、Railway → Retrieval → 最终回答 | 真实服务链能否工作；与离线 Eval 不相互替代 |

注意两种对照**不是同一个控制组**：Seed 的 `control_no_tools` 仍使用当前 Agent Prompt / Tool Schema、只禁用执行；Retrieval Increment 的 `standalone_llm` 则不注入 Poeticus Agent Prompt 或 Tool Schema，才能观察更接近模型自身参数知识的表现。

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

## Retrieval Increment Eval

固定案例在 [`retrieval_increment_cases.json`](retrieval_increment_cases.json)。当前对比：

- `standalone_llm`：不经过 Poeticus Agent Prompt，不提供工具；
- `tool_augmented_llm`：同类输入，允许一次本地 Text Retrieval 工具调用；
- Retrieval 结果本身另记录召回、排序和目标是否可见，不能仅凭最终答案正确就宣称 RAG 有增量。

关键字段包括 `target_supported_by_tool` 与 `target_rank_in_tool_candidates`：如果模型答对了，但工具根本没有返回目标文本，不能把这一成功计为 Retrieval 的贡献。经典互文经常属于模型原本就知道的知识；长尾案例（如陆游 → 杜甫）更能检验真实增量。

本地拥有 Werneror Work、FAISS / BM25 / Qwen 等 Artifact 及模型 API 配置后，运行：

```bash
python -m scripts.evals.run_retrieval_increment --output-prefix evals/results/retrieval_increment_run
```

该脚本需要本地大型构建产物，不属于无密钥、无 Corpus 的普通 CI；精确逻辑回归另由 `tests/evals/test_run_retrieval_increment.py` 等测试覆盖。完整 Agent 连续 Tool Calling、线上 Nginx / TLS 与生产服务联通仍需独立 E2E，不能由单次 Tool Eval 替代。

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

报告分别统计 annotations / commentaries 的覆盖率、每首数量、长度分布、重复项、常见文本特征和词集分布。词集表会同时给出作品数、覆盖率和每首平均元素数，避免把“收录作品多”误当成“注释更密”。

对 annotations 还会额外做一层轻量结构筛选：`headword_colon`、`quoted_source`、`cross_reference`、`long_source_note`、`other`。这只是按文本形态帮助挑候选 Case，不把它包装成可靠的“词义 / 典故 / 化用”语义分类。对冒号前的短词头，还会检查它能否在本词正文直接找到。

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
