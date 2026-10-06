# Poeticus AI Eval

这里先保存 Poeticus 的小型离线评测集。当前目标不是搭建完整评测平台，而是固定一把可以重复使用的尺子，用来比较不同版本的 AI 应用行为。

## 第一阶段测什么

第一批 Seed Eval 主要做端到端评测（End-to-End Evaluation）：把 Prompt、模型、Agent、Tool / Evidence 看成一个完整系统，观察它是否完成用户任务。

后续可以另外做组件评测（Component-level Evaluation），例如 Tool Selection、Retrieval、Reranking，但不在第一阶段展开。

## Case 与 Run 分离

- Dataset / Case：描述输入、预期行为和判定约束，是仓库中的 source of truth。
- Run / Experiment：描述某次系统配置、输出、工具调用和分数，不写回 Case。

以后保存 Run 时，至少应记录 git SHA、模型、Prompt 版本、启用的工具以及 RAG / Retrieval 版本。

## Seed Set 的维护

- 第一批只保留少量有诊断价值的问题，不追求覆盖全部宋词。
- 稳定 Case 使用固定 ID。
- 发现真实失败后，可以补充 Regression Case。
- 需要探索上限的问题可以进入 Challenge Set。
- 如果旧 Case 本身有错或无法稳定评分，应标记 deprecated 并记录原因，不静默删除。
- 不同 Dataset 版本之间做历史比较时，优先比较共同子集（common subset）。

## 当前状态

`seed_cases.json` 目前是 **draft**。诗词文本和预期约束需要先由人工复核，再晋升为 active baseline。

第一批同时保留三类问题：

1. 不需要外部资料，模型应直接阅读原文；
2. 需要典故 / 出处等外部证据；
3. 当前能力不足时应克制回答，而不是编造确定事实。

暂不引入 LLM-as-a-Judge、RAGAS、复杂自动评分或全量消融实验。只有当某个组件是否值得保留成为真实工程决策时，再做小范围 controlled experiment。
