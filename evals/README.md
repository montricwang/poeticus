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
