# 互文 Skill D/A/B/C 第一轮实验记录

状态：2026-10-21，题库与脚本已建，尚未完成正式盲评，不应据此决定上线版本。

## 实验资产

- `evals/intertext_skill_30_cases.json`：30 道候选题，六类各五题，其中五题标记 pilot。各题只给受测 Agent 作品及问题；`review` 信息仅供评审使用。
- `scripts/evals/run_intertext_skill_ab.py`：使用 Poeticus 现有 LangGraph；D 不注入 Skill，A/B/C 仅在首次系统提示词中注入候选内容。C 在这个阶段一次加载全部三个 reference 文件，不代表实现了动态按需加载。
- `data/reports/intertext_skill_ab_30_pilot.jsonl`：私人、Git 忽略的断点记录。可导出匿名答案和独立映射表。
- `tests/test_intertext_skill_eval.py`：契约、检查点、注入与匿名化测试。

## 如何运行

先做不计费的检查：

```bash
python -m scripts.evals.run_intertext_skill_ab --pilot
python -m pytest -q tests/test_intertext_skill_eval.py
```

确认配置、预算与公开工具符合目标后，每次执行有明确上限的真实调用；私有 .env 路径按本地配置替换：

```bash
python -m scripts.evals.run_intertext_skill_ab --pilot --execute --max-trials 1 --env-file /path/to/private.env --output data/reports/intertext_skill_ab_30_pilot.jsonl
```

同一输出路径可以继续未完成的实验；变更题库、Skill、工具集合或模型配置时必须新建结果文件。正式 30 题不与五题技术试跑的私有结果混用。

## 首次真实调用观察

- 在测试 worktree 的本地配置中，实际模型是 `deepseek-flash`，工具预算为 **2**。
- 本轮可注册的工具共四个：`lookup_allusion`、`lookup_reference`、`search_predecessor_texts`、`search_documents`。与此前拟议的五次调用及扩展工具池不同。
- 第一题 `itx_001` 的 D/A/B/C 四组调用均返回非空答案，结果分别落盘，匿名映射已经生成。此为链路冒烟测试，不是正式性能结论。
- 一些答案声称翁宏原诗“今存不全”，但维基文库《春殘》保存了完整的八句五言律诗（https://zh.wikisource.org/w/index.php?title=春殘&oldid=1993880）；故必须依据原典核对事实，不能让较长、较流畅的赏析自动获得更高分。
- 其余 29 题所涉出处、异文、作品关系及文献支持仍待逐题核实；题库暂不宣称 Gold。

## 下一步

1. 明确正式试验是使用当前两次工具预算、四工具配置，还是先让本地 Agent 恢复预期的五次预算及研究工具；所有组须完全一致。
2. 审阅题库原典，必要时修正题目歧义；评审备注不得泄露给 Agent。
3. 完成五题 pilot 的 D/A/B/C，然后再运行全部 30 题。
4. 先按匿名答案记录评分和事实证据，再解盲统计，避免因已知版本而评出预期结果。
