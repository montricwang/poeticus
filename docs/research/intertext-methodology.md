# INTERTEXT 方法论归纳（全量迭代研究）

关联 Poeticus Issue #354、#372、草稿 PR #388。目标是从已完成的 1505 篇研究卡中，**跨文章提炼批评家的实际论证方法**，不再重新处理 1505 篇赏析原文。

## 当前路线

- **材料来源**：`critic_methods_reviewed_v2_1505.jsonl` 中 `methods[].code == "INTERTEXT"` 且具有 `argument_path` 的 **949 条**方法实例。
- **研究单位**：一条 `argument_path` 及其引文、篇章语境；同一篇文章可能贡献多条实例。
- **方法**：大模型在对话中分批阅读**全部 949 条**，比较、归纳、修订；分批仅控制上下文和断点，不是抽样推断，也不调用本地 4B 重新阅读原文。
- **14 个大类只是既有工作分类**：允许发现 `INTERTEXT` 中的误归类、交叉归属、多种连续论证动作。子方法既不预先限定个数，也不必最终构成单一树。
- **证据约束**：任何操作都要有原记录 ID、具体论证过程、引用下标和限制；先写暂定分类，不冒称已经建立成熟文学批评理论。
- **理论比较**：完成第一轮方法归纳后，再对读已有批评理论。原文 EPUB 只用于审核有疑问或具有代表性的例子。

## 私有成果（三份）

目录：`~/projects/poeticus-data/critic-methods/results/intertext_methodology_2026-10-21/`。

| 文件 | 责任 | 状态 |
| --- | --- | --- |
| `intertext-source.jsonl` | 不可变的 949 条材料快照，保留原始论证、证据和出处 | 已导出 |
| `intertext-coding.jsonl` | 每条已审读方法的动作类型、材料→操作→推论→边界、归类理由、疑点 | 随阅读增长 |
| `intertext-taxonomy.json` | 对已编码数据的暂定子方法分组、出现次数和可追溯实例 | 自动派生，非定稿 |

`source-manifest.json` 是附属校验信息，记录输入快照 SHA-256。三份成果均在**公开仓库外**，避免公开原文短引和私人研究成果。代码与用法文档可以提交 Git。

## 运行命令

在 Poeticus 分支工作树根目录：

```bash
python3 -m scripts.research.intertext_methodology export \
  --input ../poeticus-data/critic-methods/results/critic_methods_reviewed_v2_1505.jsonl \
  --output-dir ../poeticus-data/critic-methods/results/intertext_methodology_2026-10-21

python3 -m scripts.research.intertext_methodology next \
  --output-dir ../poeticus-data/critic-methods/results/intertext_methodology_2026-10-21 \
  --limit 30

python3 -m scripts.research.intertext_methodology status \
  --output-dir ../poeticus-data/critic-methods/results/intertext_methodology_2026-10-21
```

审读者给出 JSON 决策数组后，先保存到私有路径，如 `decisions-batch-001.json`，再执行：

```bash
python3 -m scripts.research.intertext_methodology add \
  --output-dir ../poeticus-data/critic-methods/results/intertext_methodology_2026-10-21 \
  --decisions-file ../poeticus-data/critic-methods/results/intertext_methodology_2026-10-21/decisions-batch-001.json
```

本对话已直接把第一批判断写入研究集，不需要额外创建批次草稿文件；`add` 支持 `--decisions-json` 传入数组。重复提交同一 `record_id` 默认报错，确认修订时使用 `--revise`。数据文件采用原子替换，分类目录可以用 `rebuild` 从已存判断重新生成。

## 逐条编码契约

```json
{
  "record_id": "0003:m2",
  "actions": [{
    "key": "paired-text-contrast",
    "name": "对应文本逐项比较",
    "input": "需要比较的两篇文本或两个情境",
    "operation": "评论者具体做了怎样的对照",
    "inference": "由此得出了什么判断",
    "boundary": "哪一步不能当作确证",
    "evidence_refs": [0]
  }],
  "rationale": "为什么属于这种操作，而不是因为题材接近",
  "uncertainty": "短引不足、分类边界争议或原标签疑点"
}
```

`evidence_refs` 是在**本条导出记录的 `evidence` 数组内从零开始**的下标，脚本检查范围；无法证明的步骤应直接在 `uncertainty` 说明，不编造引文。多个动作可以并列，不强迫互斥。

子方法 `key` 暂时只是分组标识，允许之后合并、拆分；`taxonomy` 中 `definition / inclusion_criteria / exclusion_criteria` 需要在积累足够案例并比对反例后人工修订，空值不表示已经完成手册。

## 研究进度及停机条件

- 2026-10-21：949 条完整快照已导出，首批 12 条手工归纳已落盘，形成 7 个**暂定**动作类别；不是 7 个已确立的子方法。
- 对疑似误归 `INTERTEXT`、由旁证推断人物本事、将审美比较当历史证明的记录，明确保存边界。
- **不得继续默认运行**旧 `offline_critic_actions.py --all` 去重写昨天的研究记录：三篇试验出现重复表述和证据外推，信息增益不足。
- 剩余记录按 `next` 提取；完成全部 949 条后，重点查重名异义、同义异名、边界案例与未覆盖实例，再写方法手册。
