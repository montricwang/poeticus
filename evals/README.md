# Poeticus AI Eval

这里保留一把很小、能重复使用的尺子。2026-10-06 已完成第一轮 Seed Eval 闭环：

1. 用固定问题比较当前 Poeticus Agent 与“同 Prompt、同模型、禁止工具调用”的对照组；
2. 保存答案与 Process Trace，人工判断 Tool / Evidence 带来的真实增量；
3. 把评测中发现的 Ground Truth 错误、Agent Bug、Routing 缺陷和能力缺口分开处理；
4. 修复后用同一批 Case 回归，确认改动是否真的改善了系统。

当前仍不搭完整评测平台，也不做总分、LLM-as-a-Judge、RAGAS 或全量消融实验。尚未加入“裸基模”对照；现阶段 control 仍是**同模型 + 同 Prompt/context + 禁止 Tool**。

## Dataset

`seed_cases.json` 中每条 Case 只记录：

- 用户输入；
- Tool 是否应当使用；
- 回答至少应覆盖什么；
- 不能无依据声称什么；
- 这道题为什么值得保留。

Case 描述问题本身；某次模型输出属于 Run，不写回 Case。

第一批公开 Seed Case 仍可保持 `draft`。后续发现真实失败时直接补新的 Case；旧 Case 如果本身有问题，标记 deprecated，不静默删除。

### Ground Truth 与失败分类

评测集不是天然正确的“答案册”。出版社注释、外部数据库、AI 初标和人工标签都可能有误；当模型输出与 expected 冲突时，先允许复核评测标准本身，不默认一定是模型错。

每次明显失败优先归到下面一种：

- **Ground Truth defect**：Case / expected 本身不可靠，应先修尺子；
- **Code / Agent bug**：已经承诺的执行路径出现异常，如协议泄漏、状态累积错误；
- **Routing / Tool-use defect**：系统已有能力，但 Agent 没有调用、参数不对或没有利用证据；
- **Capability gap**：产品当前尚无这类能力，记录为 Roadmap / Feature，不要求当前版本立即跑绿；
- **Acceptable uncertainty**：证据不足时保持不确定，反而可能是正确行为。

Eval 可以领先于当前产品能力，但**不能把“尚未实现”与“实现坏了”混为一谈**。如果为了让固定 Case 全绿而不断加特例，应该停止修改并重新检查能力边界。

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

- `control_no_tools`：与当前 Agent 使用同一模型和 Prompt/context，但禁止 Tool 调用；
- `current_agent`：走当前 LangGraph Agent，允许它按现有规则调用 Tool。

Run 除了最终回答，也记录 Tool Call、参数、Tool Result 和 Evidence 摘要。这样可以区分“没查”“查错词”“Tool 无结果”“查到但没用好”等不同失败层。

这不是对所有改动做严格学术消融，只是当前阶段最便宜、最容易解释的一组对照。若以后真的需要比较“裸基模 → Poeticus Prompt → Agent + Tool”，再单独设计受控实验。

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


## 当前能力边界与下一阶段

第一轮 Seed Eval 之后，Poeticus 已确认两类 Evidence Tool：

- `lookup_allusion`：更适合人物、故事、典故性短语；
- `lookup_reference`：更适合保留明显字面锚点的前代成句、近似改写和拆取重组。

两者都不能保证解决高度压缩、反用、翻案或大幅重组。下一阶段不继续为 Seed Case 调 Prompt，而是在独立 Issue 中评估 Text Retrieval / BERT-CCPoem 等 embedding retrieval 的增量；先做 Retrieval Benchmark，再决定是否进入生产 RAG。

评测阶段形成的私人候选报告、出版物派生注释和私有 Run 继续留在本地，不提交公开仓库。
