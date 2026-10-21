# 《唐宋词鉴赏辞典》批评方法研究：私有卡片导出

本工具只负责从**仓库外**的私有研究记录生成可重建的 JSONL 快照，不提供原始书籍内容，也不自动导入线上 Poeticus。

## 数据边界

- 唯一已提交记录：`~/projects/poeticus-data/critic-methods/results/records/`，一篇一份 JSON；对应阅读卡见同级 `cards/`。
- 临时 worker 文件与历史草稿：`results/archive/2026-10-20-worker-inbox/`。原 `inbox/` 已清空，归档不参与读取，不允许拿过期 token 再次提交。
- 私有合并视图：`results/critic_methods_1505.jsonl`。每行一篇，按 `essay_no` 排序；额外 `_record_schema` 仅用于区分 `pilot_v1`（前 20 条）和 `article_v2`（其余 1485 条），其余字段按源记录保留。
- `critic_pool.sqlite3` 保留为原任务分配与核验历史，不因导出而重新写库。
- EPUB 原文及现代赏析、单篇 JSON 和 JSONL **不得直接上传 GitHub**；本仓库只有通用导出程序、合成测试和元数据说明。

## 生成与核验

从仓库根目录运行（无需额外第三方包）：

```bash
python -m scripts.research.export_critic_methods \
  --records ../poeticus-data/critic-methods/results/records \
  --output ../poeticus-data/critic-methods/results/critic_methods_1505.jsonl \
  --expected-count 1505
python -m unittest tests.test_export_critic_methods -v
```

会检查记录数量、文件名中的四位篇号、JSON 内的 `essay_no`、`essay_id` 唯一性和已知的两种结构；任何失败都不会替换旧的合并结果。新输出使用临时文件完成后原子替换；打印 SHA-256、条数、两类 Schema 数量及证据索引数量，便于比对。

2026-10-20 首次导出核验结果：1505 条，20 条 `pilot_v1`、1485 条 `article_v2`；合计 7927 个方法/动作记录。首次脚本显示的 **23834 条证据索引少计了旧 20 篇的 64 条 `exact_quote`**，现已修复，实际是 **23898 条**（不是不同引文去重数）。原始合并视图约 9.24 MB、SHA-256：`1ea608c640d9a63699201658072264d31dbf128a8a8fbdc4ba6995bd5879aee2`，内容未改。

这里的“通过”仅证明篇号/Schema/记录结构与已有研究池的保存结果完整，**不等于 1505 篇文学判断已经独立人工复核**。

## 2026-10-21：统一 Schema 与首轮抽审

**统一入口（私有，不加入 Git）**：`results/critic_methods_uniform_v2_1505.jsonl`。由现有 JSONL 做无损结构投影，一篇一行、按篇号排序；原始 `records/`、`cards/` 和原 JSONL 均保留，暂不移动或删除零散文件。

| 原始 20 篇（`pilot_v1`） | 统一视图（`article_v2` 字段） |
| --- | --- |
| `moves[].method_code / analysis / exact_quote` | `methods[].code / argument_path / evidence[].quote`（段落、字位及哈希一并搬迁） |
| `research_question` | `analysis_target` |
| `interpretive_limitations` | `limitations` |
| 无相应人工标注的字段 | `core_argument`、`special_observation`、`transferable`、`author_vs_ai` 留空，写入 `_missing_fields` |
| 其他旧版专有信息 | 原样留在 `_pilot_original`，绝不推断补写 |

其余 1485 篇保留 `methods` 内容；其中 26 条缺少非必填 `analysis_source`，统一视图以空值及 `_missing_fields` 显式标记。输出还携带 `_origin_schema`，以便追溯两批记录生成历史。

```bash
python -m scripts.research.normalize_critic_methods \
  --input ../poeticus-data/critic-methods/results/critic_methods_1505.jsonl \
  --output ../poeticus-data/critic-methods/results/critic_methods_uniform_v2_1505.jsonl \
  --expected-count 1505
python -m unittest tests.test_export_critic_methods tests.test_normalize_critic_methods -v
```

2026-10-21 已生成私有快照：1505 条，7927 条方法，**23898 条引文索引**；SHA-256：`1bede0eb8c4a6ab31d77ecf568047518b645d104c1474fe5fbf0097c00109400`。

EPUB 全量短引及哈希比对完成：1505/1505 无定位错误。7 处旧分篇异常经人工定位实际构成 **9 份独立补遗**（#879、#1030 均各含额外独立篇）；9/9 引文及哈希复验通过，仍与主池隔离，待独立 ID 与质量验收后再决定入库，不直接改 1505 编号。

程序抽取 36 篇分层样本（旧/新结构、评论者产量、篇幅、潜在寓托和稀有方法），人工逐条核对方法与引文上下文：24 篇有依据且保留限制、3 篇方法标签明显错配、3 篇分类需厘清、6 篇原评论推断偏强但当前卡片已说明风险。**这个有意分层的样本不用于估算全库准确率。**

审计报告位于仓库外私有目录 `results/audit_2026-10-21/`：`quality_audit.md`、`stratified_sample.csv`、`semantic_review_36.md`、`semantic_decisions_36.json`。重新核验：

```bash
.venv/bin/python -m scripts.research.audit_critic_methods \
  --uniform ../poeticus-data/critic-methods/results/critic_methods_uniform_v2_1505.jsonl \
  --manifest ../poeticus-data/critic-methods/results/manifest.jsonl \
  --epub ../poeticus-data/critic-methods/raw/唐宋词鉴赏辞典.epub \
  --private-runner ../poeticus-data/critic-methods/results/critic_runner.py \
  --exception-specs ../poeticus-data/critic-methods/results/manual_exception_specs.json \
  --exceptions-dir ../poeticus-data/critic-methods/results/manual_exceptions \
  --output-dir ../poeticus-data/critic-methods/results/audit_2026-10-21 \
  --manual-reviews ../poeticus-data/critic-methods/results/audit_2026-10-21/semantic_decisions_36.json
```

后续再细化方法标签定义，进行按评论者分组比较并构造 Agent 迁移评测；属于 Issue #372 的后续工作，不能仅凭 227 个评论者署名字符串或初标频次认定方法“独特”。
