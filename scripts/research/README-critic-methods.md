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

2026-10-20 首次导出核验结果：1505 条，20 条 `pilot_v1`、1485 条 `article_v2`；合计 7927 个方法/动作记录、23834 条证据索引（**不是不同引文的去重数**）。合并视图约 9.24 MB、SHA-256：`1ea608c640d9a63699201658072264d31dbf128a8a8fbdc4ba6995bd5879aee2`。

这里的“通过”仅证明篇号/Schema/记录结构与已有研究池的保存结果完整，**不等于 1505 篇文学判断已经独立人工复核**。早期 EPUB 分篇扫描还有 7 个结构异常候选，不在 1505 条已解析研究卡范围内，应另行审校。

跨篇方法提炼、作者分层、质量抽查与迁移评测的后续设计见 GitHub Issue #354 与明日研究 Issue #372。
