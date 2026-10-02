# EPUB 作品抽取：数据取舍与维护地图

适用范围：本项目的商业 EPUB《历代名家词集精华录》**15 个作者词集**。**输入来自私人持有的 EPUB；带原文的抽取结果、图字映射与现代注评不得提交公开仓库。**本文是后续修改/数据库建设的快速入口；证据与具体样式规则详见 [epub-extraction-audit.md](epub-extraction-audit.md)、[epub-classifier-design.md](epub-classifier-design.md)，执行命令详见 [epub-import-sop.md](epub-import-sop.md)。

> 当前已知真实本地导出验收（2026-10-02）：15 册、3491 首；用户核对 3491 个唯一 ID，0 首空正文。此结果说明数量检查通过，**不等于文学分类逐首正确，也不代表整个 EPUB 无损保存**。所有作品仍是 `imported_unreviewed` 性质的候选数据；中间 JSON 不是阅读前端/数据库 Schema。

## 1. 数据从哪里来到哪里去

```text
本地 EPUB（原始证据；不修改）
  → epub/reader.py：解析目录和 XHTML 来源
  → extractor/blocks.py：按 h1/h2/h4/p 枚举源段落、行内结构和位置
  → extractor/rules.py：小范围来源特定的分类规则
  → extractor/extractor.py：按作品分组；正文、题序、注释、评论、告警
    └ extractor/inline_notes.py：标注 font1 附注候选和来源位置
  → extractor/schema.py：中间 Poem 数据契约
  → pipeline/normalize.py：按 glyph map 替换图片字占位符并重算附注偏移
  → batch_import.py / import_poems.py：15 册预检、阻断、输出私有 JSON
  → data/output/all_normalized.json：合并**中间作品数据**
  → [未来：独立的 curated/export 层 → 阅读器 Schema / 数据库]
```

旁路诊断：`analyze/audit_extraction.py`、`analyze/coverage.py` 与 `analyze/inspect_*.py` 用于扫描结构覆盖、定位分类反例、复核原 XHTML。人工辨字工具是 `review_glyphs.py` / `import_glyph_backup.py` / `glyph_contexts.py` / `pipeline/glyph_mapping.py`；这些**不是每次运行的主导入逻辑**。

## 2. 当前中间数据实际包含什么

| 源文献内容 | 中间 JSON 去向 | 当前边界 |
| --- | --- | --- |
| 词牌、词题、署名 | 顶层 `tune`、`title`、`author` | 「又」只在作者及区域内继承；不能可靠识别时发 warning。原始组合标题不单独保存。 |
| 词文、显式 `br`、显式空分隔段 | `content.text: list[str]` | 不自动纠正文句，**一个列表元素不必然是一阕**。 |
| 题前小序（包括确认为附作题序的纳兰三段） | `content.prefaces` | 不因为文字提及作词缘由就按标点切为词题。不能仅凭排版判定历史作者身份。 |
| `◎` 独立注释 | `content.annotations` | 可能包含现代整理注释，版权与作者出处需进一步追踪。 |
| `◆` 评论及依据具体块号复核的续段 | `content.commentaries` | 周邦彦两处续段是**定点**分类，不扩大为「所有 ◆ 后的普通 p 都是评论」。 |
| `span.font1` 行内说明 | 原句留在 `text`，另存 `inline_notes` 和部分 warnings | 只是可追溯候选范围；仅少数来源获作者自注判断。引文跨 span、标点在 span 外的情况**尚不能安全净化正文**。 |
| `（以下缺）` | 原样留在正文，并有 `inline_editorial_gap` warning | 编者校勘标记，不自动补字或删字。 |
| 图片字 | 已核实 `display_form` 或 `source_form` 写入规范化文本；warning 记来源 `src` | IDS-only 如 `⿰缶吾`保留 IDS 字符序列、`ids_transcription` 状态；**不等于得到 Unicode 单字，也未完成图像渲染**。 |
| 存疑、补遗、辑佚的分组信息 | 抽取时用于作者/区域判断；存疑场景发 `doubtful_attribution` warning | 尚无全作品统一的 `textual_status / zone` 独立字段。 |

## 3. 不导出或只在处理时保留的东西

| 信息 | 当前处置 | 将来的提醒 |
| --- | --- | --- |
| `h1` 卷次/作者区域标题、TOC 卷层级 | 仅用作作品来源定位、作者切换和存疑/补遗区域判断；不保存卷次字段 | 日后按卷阅读、还原原书排序要重新取回层级与源坐标。 |
| 单独的编年段落 | `is_chronology` 识别并暂存 `section['chronology']`，`convert_to_poem` 不写入 Poem | 此项具有文献研究价值；建议保留**原文和来源**，勿先推断为精确创作年月。 |
| 导读、总评、版权/出版说明、书名页等、非词作品 | TOC 过滤或非作品标题/区域跳过 | 本工具只针对作者词集；过滤不等于整本 EPUB 已数字化。 |
| 版心/页码、空分页符、仅排版用块、图片说明文字 | 不作为词文写入（明确分片空段除外） | 这不是“无损电子书复刻”；需要文献版面还原时应返回 EPUB。 |
| 贺铸调名的「亦名」等别称 | 当前选择主要词牌/题目，没有正式的别名集合 | 单独交给词牌词谱数据建设，避免猜一套全集别名关系。 |
| 源位置、源块编号、作品开始锚点 | `extract_sections` 有 `html/ordinal/anchor`，Poem 仅有固定的书名 `source`；仅部分 warnings/inline_notes 留源坐标 | **高优先级待改进**：应为每首作品保存精确来源坐标，未来校订、复导、DB 迁移可稳定追踪。 |

注意：`coverage.source_block_coverage` 的“已处理”包含分类证据、布局或有意排除的段落，不等于这些文字**已进入**作品 JSON。结构覆盖为 0 漏块不能当作文学准确率，也不能据此称全 EPUB 无损。

## 4. 今天才逐步发现的风险及决定

1. **一个 XHTML 内含多个作者；合刊 TOC 与正文作者边界并存。** 取作者分组、`h1` 和附作署名交叉校验，不直接继承整卷默认作者。
2. **「又」不是固定词牌。** 仅在同作者和同文本区域继承上首已知词牌；不能解析时留空并 warning。
3. **单独段落的语义不能只看字体。** 柳永有独立词题，纳兰附作有题序+右对齐作者，周邦彦注评引用与正文同级；分类前先看位置、来源块号和上下文。
4. **`font1`/ `kaiti` 不是注释标签。** 某些 `kaiti` 是分页正文，某些 `font1` 是行内说明；截取 span 就删除会留下引文/标点残渣。
5. **生僻字是版本、文字学、Unicode 三个问题。** 将原字与规范显示分开；不把异体、文本异文、专名别称伪装成同一种替换关系；没有通行字的 IDS 不强行造映射。
6. **无法分类的正文或评论续段不能静默丢失。** `NON_EXPORTABLE_WARNING_TYPES` 在写 JSON 前阻断；特别规则必须有来源/源块依据及合成测试。
7. **单册测试通过 ≠ 十五册实际 EPUB 通过。** 人工报告、真实预检、字形映射、数量验收和合成 CI 各证明不同事情，不能互相替代。

## 5. 将来改动时应该去哪一个文件

| 需求 / 错误现象 | 优先修改 | 回归重点 |
| --- | --- | --- |
| EPUB 读错 XHTML、丢格式 | `epub/reader.py`、`extractor/extractor.py::raw_xhtml` | UTF-8、目录范围、正确使用原始 XHTML |
| 新词集标题和词题结构 | `extractor/rules.py::interpret_heading` 和 `extractor/extractor.py::extract_sections` | 词牌、词题、空段、别名、混合标题 |
| 卷次、作者切换、附词归属 | `extractor/extractor.py::toc_file_contexts / extract_collection` | 温韦、二晏、南唐、纳兰附作、存疑作品 |
| 年代、原文来源坐标要保存 | `extractor/schema.py`、`extractor/extractor.py::convert_to_poem` | 从 source XHTML 到 Poem，再经 normalize/batch 导出的字段完整性 |
| 题序、注评分类 | `extractor/rules.py::is_preface` + `extractor/extractor.py::extract_sections` | 周邦彦的确认评论段落、纳兰题序 |
| 纯净阅读词文与自注拆分 | `extractor/inline_notes.py` + **新增独立 curated 转换层** | 引文跨 span、残留句号、原文可逆、字符区间 |
| glyph 异体/IDS 的显示 | `pipeline/normalize.py`、`pipeline/glyph_mapping.py` | 原字/显示字独立、IDS 字符序列、inline note offset |
| 新增数据库表或前端 JSON | **新增下游 adapter/exporter，不要直接改 DOM 解析规则** | 不丢源位置/编年/文献类别；避免二次复制受版权保护的注评 |
| 分册预检、全书校验、输出目录 | `batch_import.py`、`import_poems.py` | 15 册计数、ID 唯一、0 空正文、阻断策略 |
| 新异常的定位 | `analyze/audit_extraction.py`、`analyze/inspect_source.py` | 只在本地生成含原文报告；测试使用合成文字 |

## 6. 简并原则与下一阶段建议

- **不做为了减少文件数的大重构。** 当前 `reader → extractor → normalize → batch` 分层有意义，外围调查脚本不是生产依赖，不必合并成巨型文件。
- 需要简化的是**操作入口和文档索引**：业务以 `import_poems --all --check` / `--all` 为主；`review_glyphs` 只在有待识别图片字时用；其他 `analyze/inspect_*` 归为按需诊断。新增复杂规则前先扩展回归测试，而不是不断追加个人记忆里的例外。
- 下一个导出结构改动之前，优先补齐 **作品 source XHTML + anchor/block、编年原文（及证据/不确定性）**；这两个在临时结构里已经有迹象，越晚补，越容易失去精确关联。
- 进入数据库前，**单独定义真正的阅读作品 Schema**，再决定是否包含现代注评、行内作者自注如何独立呈现、版权材料能否公开；当前 `all_normalized.json` 不要直接当成线上可发布的作品库。
- 这次抽取器针对的是一个**确定版本**的特定 EPUB；如果原书版本或 XHTML 结构改变，应先重新跑源块审计，不要假定硬编码的块位置仍适用。

**停止线**：如 15 册导出已有稳定数量、来源可追溯的主要结构和已知异常记录，当前 PR 可以验收合并。编年持久化、来源坐标、行内自注阅读拆分、数据库适配属于下一阶段独立 Issue；除非发现当前 JSON 丢失了必须立刻修复的正文，否则不为了“完美”阻塞本轮。
