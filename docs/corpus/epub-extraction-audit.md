# 15 册词集：规则抽取与本地审计

范围：仅《历代名家词集精华录》的 15 个作者词集分册。词话、词谱、格律文献不使用 Poem 抽取器。不要将 EPUB、画像报告、现代注评、图片映射或真实抽取 JSON 提交到公开仓库。

## 本次规则

- SourceBlock 先保存来源 XHTML、块序号、标签、class、标题内部的子片段与换行，再做语义判断。证据只保存在提取阶段，不改变当前 Poem Schema。
- 按 TOC 子词集和同 XHTML 内的 `h1` 作者边界，给温韦、二晏和南唐三词人归属作者；同一个文件被不同作者分组引用、又无明确作者证据时，作者留空并告警，不猜测。
- 纳兰集用【附】＋h4＋作者段落识别附词作者；附词缺署名时，作者留空并标记 `missing_inserted_author`，不能自动写成纳兰性德。
- 「又」仅在同一作者、同一文献区域内继承。存疑作品产生归属提醒。
- `◆/◎` 后无符号内容不直接视为词正文（包括注评发生在首段正文之前时）：仅相同直接 class/style 的连续段落先合并为候选续段，发出 `inferred_note_continuation`；否则发出 `unclassified_after_notes`，保留全文待核对。
- 正文之后出现 `p.kindle-cn-ref/ref1/ref2` 且不能确认类别时，写入待核查块并发出 `ambiguous_reference_after_verse`，不再直接并入词正文。
- 小字夹注保留原文字并发出 `inline_body_style_review`，暂不擅自删除。标题嵌套图片字保持原文先后位置；缺失图片 `src` 时保留占位符并告警。
- 李清照逐句 p 的空段保留空字符串，表示原书显式分片，但此数组不是已经清理好的前端分阕数据。

## 一条命令审计 15 册

在仓库根目录安装依赖并保留本地 EPUB 后：

```bash
python -m scripts.corpus.epub_import.analyze.audit_extraction
```

只检查一册：

```bash
python -m scripts.corpus.epub_import.analyze.audit_extraction --book "纳兰词集"
```

默认输出位于 git 忽略的本地文件：

- `data/reports/epub_extraction_audit.md`：按册汇总，优先显示高风险告警，再显示一般样式告警；对作者待定的附词，显示不含正文的前几个块的标签、class 和长度，帮助定位署名模板。
- `data/reports/epub_extraction_audit.json`：完整告警位置，可能包含受版权保护文本，严禁公开。

审计命令不执行图片字的交互式人工确认，不导出 curated Poem，不执行 normalization。先看作者待定、空正文、未解析调名、正文混入注评标记，再核查续段候选、无法分类块、行内样式，以及存疑词和附词作者。

## 复核建议

1. 每册抽查普通、稀有、异常、首尾及随机作品。
2. 检查合刊作者切换，纳兰附词的实际作者，「又」是否错误继承。
3. 检查贺铸词调与自命名顺序、柳永独立词题、姜夔编年、李清照的空段分片及注评跨段。
4. 如发现错误，提取不含商业文本的最小合成用例后修正规则。

注意：GitHub CI 只能证明合成测试通过，不能由此宣称 15 册的文学语义抽取准确。

首次真实审计（2026-10-02）的已确认发现：二晏合刊曾把同一文件末尾的 `h2`「总评」计作作品；已加入精确标题排除规则。多个分册存在每首两条的普通 `span` 样式告警，已缩小为混合样式才告警。纳兰 3 首附词作者待定仍需在本地依据结构检查，不擅自填写。

第二次真实审计（同日）：二晏候选作品数 400→398；李煜合刊 132→131；欧阳修、秦观、贺铸的大量整段字体样式告警清零。**这些是结构修复和告警口径改变的验证，不是对真实文学语义准确性的证明。**

纳兰的 3 个 `missing_inserted_author` 均符合 `h4 → 普通短 p → p.kindle-cn-para-right（三字署名）→ 两段正文`。现允许在这种窄范围内识别后一段署名，把前一段保留为 `unknown_before_author` 并发出 `unclassified_before_inserted_author`；不擅自决定前段究竟是题名、小序还是编辑说明。长篇右对齐文字不视为这种作者署名证据。周邦彦仍有 21 次 `unclassified_after_notes`，新的 Markdown 报告会列出这些待分类块及其前后块的标签、class 与长度，不含原文，以供后续判断，暂不批量自动归类。

第三次真实审计（同日，纳兰与周邦彦定点复跑）：纳兰 356 首的作者待定数从 3 降为 0，之前三处署名分别识别为严绳孙、陈维崧、严绳孙；原本在署名前的 3 个短段落仍列为 `unclassified_before_inserted_author`，不得无证据当成正文或小序。周邦彦虽然出现 21 个 `unclassified_after_notes`，但集中在两首（`zhou-bangyan-001` 19 块、`zhou-bangyan-055` 2 块）；这批段落在 `◆` 后交错使用 `kindle-cn-ref` 与普通 `p`，不能由排版 alone 判断到底是续注、引用还是其他编辑材料。

**导出安全线：** `extract_sections` 将这些未归类文字留在本地临时 evidence，`PoemContent` 不含 `unknown` 字段。为了避免 `import_poems` 静默抛弃文本，正常导入只要遇到 `unclassified_after_notes`、`unclassified_before_inserted_author` 或 `ambiguous_reference_after_verse` 就必须在写任何 JSON 前停止。用户需在私有 EPUB 中复核，再落实真实的语义规则或有依据的跳过决定；不提供默认绕过选项。审计报告按册显示受影响作品数与待分类段落数。这不等于要求这些现代注评未来全部进入面向用户的 Poem Schema。
