# EPUB DOM/CSS 画像工具

**目的：在设计 Poem Schema 和清洗规则之前，调查整套 EPUB 的实际 HTML 层级与 CSS 差异。** 本脚本只输出可观察的结构证据，不自动判定哪段文本是词牌、词题、词序或正文，也不更改任何抽取结果。

## 使用

在仓库根目录执行：

```bash
python scripts/corpus/epub_import/profile_epub_dom.py
```

默认读取私有 `data/raw/历代名家词集精华录.epub`，输出本地：

- `data/reports/epub_dom_layout_profile.md`：22 册总览、每册标题/段落模板分布、有限样例及 CSS 来源。
- `data/reports/epub_dom_layout_profile.json`：相同信息的结构化表示，可用于后续生成规则与验证。

限定单册：

```bash
python scripts/corpus/epub_import/profile_epub_dom.py --book "苏轼词集"
```

使用环境需要 `ebooklib`、`beautifulsoup4`、`lxml`、`tinycss2`、`cssselect2`（Beautiful Soup 自带的 soupsieve 用于选择器匹配）。

## 报告会记录什么

- EPUB TOC 对应的分册、子分组和 XHTML；同一 XHTML 在同一册中去重分析。
- `h1`—`h6` 的内部文本片段、子节点的标签/class、继承或显式 CSS 排版属性、对应的样式表和选择器来源。
- 标题模板按**节点结构及静态排版特征**分组，列出频次、所在分组和实例。例如苏轼的 `span.font1` 与姜夔的 `span.kaiti` 可以作为不同的候选词题样式。
- `p` 按 class、可观察的内容开头特征、样式分组；记录相对标题的位置及内嵌标签（包括 `br`、`span`、`ruby`、`img`、脚注相关标签）。
- 不是 `p`、也不在标题内的文本节点，帮助发现当前 Parser 可能跳过的容器。
- CSS 未解析的 at-rule、选择器、失联文件和外链，避免假装已完整还原视觉结果。

## 已知边界与下一步

1. 样式是**静态近似**：处理常规样式表、内联 CSS、选择器优先级、`!important` 和主要继承属性；不计算真实像素大小、`em` 数值、字体 fallback、媒体条件，也不渲染页面。如需验证实际视觉效果，应借助浏览器或 EPUB 阅读器。
2. 同名 CSS class 可以在不同分册承担不同用途；字体差异也不自动等于语义差异。只有核验样例后，才能制定作用域明确的抽取规则。
3. Markdown/JSON 仅保留有限样例，不复制整册原文；但包含现代注释和评论，作为**本地私有报告**保管，不提交公开仓库。
4. 下一阶段先根据报告写 `docs/corpus/epub-semantics.md`，明确拆分词牌、词题、序文、正文等字段的证据和不确定性；随后再修改 Parser。

## EbookLib 原始 XHTML 的注意事项

`EpubHtml.get_content()` 会重建 HTML 文档，可能丢失 EPUB 原始 `<head>` 的 `<link rel="stylesheet">`。Profiler 优先解析 `item.content`（导入时保存的原始 XHTML）；只有没有这个属性时才回退到 `get_content()`。此前的 22 册「CSS=0」报告因此无效，需重新生成。

验收时检查总览表 CSS 一列，以及每册标题样例后的 `font-family/font-size` 与 CSS 来源。若全部显示 0 和「未声明」，应先检查输入结构，不能据此推断原书没有样式。

本 EPUB 的原始 XHTML 为 UTF-8。现在明确解码字节后再交给 Beautiful Soup，避免其在缺少 charset 声明时误判汉字编码；UTF-8 BOM 亦可正常处理。
