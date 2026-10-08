# ADR-0004：将私人来源语料与公开阅读数据分离

- **Status:** Accepted
- **Date:** 2026-10-08（对现有实现的决策追认）
- **Scope:** Corpus ingestion, publication and data provenance
- **Origin:** joint（根据私人商业 EPUB 的版权与质量约束形成边界）
- **Confidence:** 公私数据库、白名单发布及 3491 首公开读取链路已通过真实迁移/上线验证；逐首文学文本校勘未完成
- **Related:** #48、#60、#68、PR #52、PR #59、PR #69

## Context

Poeticus 从私人持有的商业 EPUB 导入作者词集，解析过程包含现代注释、评论、图片字、原始 XHTML 位置和人工判断。这些资料不能未经许可提交到 GitHub 或随作品 API 发布。与此同时，产品需要稳定的公开作品 UUID、目录、正文，以及可重复的源头数据修复流程。

## Decision

1. 私人 EPUB 与 `glyph_maps` 保存在仓库外的 `poeticus-data/reading-corpus/raw/`；全量规范化快照与对应 Manifest 保存在 `reading-corpus/normalized/`。人工复核备份独立保护。
2. 作品解析先形成带来源信息的**私人**规范化记录，再导入私人 PostgreSQL；公开库由私库**明确白名单字段**发布，而不是从 EPUB/JSON 直接把全部字段同步出去。
3. 公开库只包含阅读所需的批准字段和稳定作品身份；`poem_source_texts`、现代注评、原始 EPUB、字形映射、审计/校勘材料不得进入公开数据链路。
4. 当前导入作品标记 `imported_unreviewed`。结构抽取数量、程序测试通过不等于文学意义上的逐首校勘完成；不静默宣称校勘质量。
5. 工作中使用 UUID 作为作品身份，**重建空私人数据库可能改变 UUID**；已有公开数据与私库的身份关联需要可靠备份/映射，不能靠作品题名猜测同一性。

## Alternatives and consequences

- **直接公开导入后的完整 JSON/注评**：实现简单，但会暴露私有来源、现代评论和人工报告；不接受。
- **只保留公开库、丢弃来源**：运行期足够，但无法可靠复核异文、图片字或错误分类；不接受。
- **为了可追溯将所有原始版式字段纳入公开 Schema**：会增加隐私/版权风险与长期耦合；源头证据留在私有管线即可。

代价是需要维护私有与公开两段发布步骤、校验映射与独立备份。详细当前表结构、发布约束和操作命令分别见 [作品数据库架构](../architecture/corpus-database.md)、[EPUB SOP](../corpus/epub-import-sop.md) 和 [data-management](../data-management.md)。

## Revisit when

取得清晰来源授权、引入真正经过校勘的版本体系、作品身份迁移策略改变，或下游确实需要可公开的精细出处字段时，重新评估白名单及 Schema。任何变更都必须经过明确的隐私和数据正确性验证。
