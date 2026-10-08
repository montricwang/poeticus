# ADR-0003：阅读作品年代与检索语料年代严格分离

- **Status:** Accepted
- **Date:** 2026-10-08
- **Scope:** Corpus provenance, chronology and Retrieval eligibility
- **Origin:** joint（拒绝全库硬编码宋代、保留不确定性）；AI-proposed（利用现有 Retrieval metadata 做 fallback），经线上真实 Case 修正
- **Confidence:** 线上 E2E 证明缺失 `dynasty` 时现行回退机制可改善已知 canary；同名作者、跨朝和朝代标注失真仍未系统验证
- **Related:** #151、#164、PR #165

## Context

公开阅读库有晚唐、五代、宋代等作品，但缺少可靠**逐首创作年代或朝代**。第一轮线上 Retrieval 请求 `dynasty=null` 时，后世候选无法被有效过滤；另一方面，把全部作品简单标成「宋」又会排除真实的唐/五代作品。

Werneror 的 `dynasty` 也不是权威断代：实测中温庭筠、韦庄及冯延巳、李璟、李煜等在这个语料内都被归为「唐」，包含与历史断代不一致的南唐标签。

## Decision

1. **不把推测的年代写回私人或公开阅读库**。只接受有可靠来源证据的独立作品年代字段。
2. 检索请求缺 `dynasty` 时，先根据当前作品正文找到 Werneror exact-content alias，再按 exact author 的语料内 dynasty 分布确定**粗语料兼容标签**；分布并列或证据不足则保持 unknown。
3. 这个标签只辅助 Candidate Eligibility 判断**明确不可能的前代候选**；同朝、时间重叠或不确定者保留并让 Agent 判断。
4. Agent 不把 Werneror 粗标签作为作者生卒或历史断代事实向用户表述。来源文本、作品原始信息和不确定性必须继续可追溯。

## Evidence and alternatives

- 最初 E2E 因 `dynasty=null` 暴露时代过滤不足；修复后陆游 Case 在生产检索中再次找到杜甫候选（当时记录 rank 6），Agent 最终使用该证据。
- 「所有阅读作品都当宋代」成本最低，但已被现存晚唐/五代作品推翻。
- 在数据不足时直接替用户猜逐首年代，会将检索的方便标签污染成阅读库的历史事实。
- 完整逐首年代知识库更精确，但目前没有经权威校验的数据；引入其维护成本之前应先补数据来源与测试。

## Consequences and revisit when

优点：检索能在缺少 API 年代字段时尽量提供有意义的候选，同时不污染出版来源的历史元数据。代价：同名作者、跨 dynasty bucket 及 Werneror 自身标注错误可能造成误排或放宽过滤。

待阅读作品获得可靠逐首年代、或出现系统性错误排除时，应改由阅读库传递经过核查的 chronology，并重新评估 fallback。duplicate/variant self-hit 的进一步一致性由 #151 跟踪。当前代码结构见 [corpus-database](../architecture/corpus-database.md) 与 [text-retrieval](../architecture/text-retrieval.md)。
