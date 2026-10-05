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
python -m scripts.corpus.epub_import.diagnostics.audit_extraction
```

只检查一册：

```bash
python -m scripts.corpus.epub_import.diagnostics.audit_extraction --book "纳兰词集"
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


第四次审计输入（2026-10-02，本地人工复核具体原文）：纳兰三个附作 `h4 → 普通 p → 署名 p` 中，普通段落实际是赠答对象、和韵关系与作词缘由，因此完整保留为 `title`，不再标为 `unknown`；如果 h4 本来已有另一词题，则仍保留待分类并阻止导出，避免静默覆盖。周邦彦两首词后的 19+2 个段落已由本地原文核实为 `◆` 评论延续中的文献引证及考辨，分别确认 `text00241.html` 的作品起始块 2（段落块 20–38）、作品起始块 504（段落块 511–512）。因此仅在这两个 **具体来源和块号范围**，且确实已进入 `commentaries` 状态、块 class 符合既定格式时并入评论；保留 `verified_commentary_continuation` 审计依据。若版本或排版变化，仍归为 unknown 并触发导入拦截。不要把这次确认扩大为“凡 `kindle-cn-ref` 都是注评”或“凡 ◆ 后所有 p 都是评论”。

以上两处调整尚需重新在本地真实 EPUB 上运行审计，以验证两个分册的待分类块归零；新增合成测试只能验证规则，不代替这一步。
## DOM 层级诊断：区分兄弟节点与真实嵌套

审计 JSON 只含单个段落的 `tag/classes/block`，不能据此宣称原 XHTML 没有评论容器。现在可以在**本地原 EPUB** 执行只读的父节点诊断，它直接沿 BeautifulSoup 节点的 `.parent` 查找完整祖先链与最近共同祖先，不读取内容判断语义，也不会导出商业文本：

```bash
python -m scripts.corpus.epub_import.diagnostics.inspect_dom_hierarchy --html text00241.html --group 19-22 --group 36-38 --group 510-512 --output data/reports/zhou_dom_hierarchy.md
python -m scripts.corpus.epub_import.diagnostics.inspect_dom_hierarchy --html text00307.html --group 211-214 --group 224-227 --group 229-232 --output data/reports/nalan_dom_hierarchy.md
```

该工具的块号与语义抽取器一致，扫描 `h1/h2/h4/p`。输出仅包含标签、class、id、兄弟元素次序、直接父节点、最近共同祖先，允许分享结构摘要；**它只能证明 DOM 结构，不能自行证明哪一层代表词题、小序、注释或评论**。即使全部 `p` 共享 `div`，该 `div` 也可能只是整页排版容器；只有定位到专用容器、结合上下文才能升级语义规则。

纳兰人工核实的三段属于交代赠答、和韵、写作情境的短题注，当前归入 `title`。`title` 与 `prefaces` 是 Poem 中不同的语义槽位：标题可以说明作词缘由；不要仅因文字提到背景就自动改入小序。若要把「时某人丁忧」从同一段中单独拆成小序，必须先定义产品上的分界并确认原书表示，不能直接按标点猜。


## 真实 DOM 与题序复核（2026-10-02）

用户在原始 EPUB 上运行 `inspect_dom_hierarchy`，确认周邦彦 `text00241.html` 的评论开头、引文和考证段落（19–22、36–38、510–512）**全部直接位于 body 之下**；它们在 DOM 中是兄弟节点，共同祖先仅为 `body`，没有可复用的 `section.commentary` 或 `blockquote` 容器。这说明前述 21 段必须依赖作品范围、`◆` 标记及人工复核来建立评论关系，不能通过父子节点归属自动解决。

用户又依据原书排版核对纳兰的三段短文字：它们不是与词牌同一标题节点的子片段，而是居中词牌下方**独立成行**、位于右对齐署名之前的题序。所以修订此前一度归入 `title` 的判断，现将整个段落保留在 `PoemContent.prefaces`；`title` 只保留 h4 自身已经标明的词题，若 h4 没有词题则允许为空。复合句不按标点拆分；签名仍由后续 `kindle-cn-para-right` 识别。这是基于原书具体排版与文本的分类，不意味着所有词集的独立 p 都应当被解释为小序。

前文关于将这三段归入 `title` 的记录属于当时的临时判断，**以本节的 `prefaces` 修订为准**。两册已知的待分类块数为零，但上述字段调整仍需用户使用最新分支再次执行真实 EPUB 审计验证。
