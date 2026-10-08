# EPUB 分类器：历史调查与仍需人工核实的样式

**文档状态：复核研究记录，不作为当前解析规则的唯一权威。** 其中 2026-10-02 的阶段性假设可能已被后续真实 EPUB 复核修订；当前有效的分册规则与源码定位见 [EPUB 维护地图](epub-pipeline-maintenance-map.md)，运行与诊断命令见 [EPUB SOP](epub-import-sop.md)。本文件重点保留尚未结束的 `font1` / `kaiti` 样本复核、可逆行内注释及其证据，不按临时判断改写现行 Schema。

目标不是“全部输出、零 warning”，而是让每一项来自选中 XHTML 的文字都有可解释的去向，在不确定时不静默丢失、不伪装为已经分类正确。

## 现有基础（不另造第二套 Parser）

- `extract_sections` 已经是一个有状态的分类器：根据标题、作者、作品范围、`◎/◆`、段落 class 和前后关系，给出 `tune/title/text/prefaces/annotations/commentaries` 等结果。
- `rules.py` 包含通用判断与实测分册差异：例如贺铸标题顺序、柳永词题、纳兰附词、欧阳修编辑性栏目、周邦彦人工核实的续评。不是每册都需要单独造一套分类规则。
- 临时 `SourceBlock` 与 `section["blocks"]` 保存块号、角色及原始 DOM 供本地审计；最终 Poem Schema 不添加只用于审计的字段。
- `import_poems.py` 已拒绝在 `unknown` 文本会丢失时继续导出。

## 分类器应当回答的三个问题

1. **这属于哪一篇作品或编辑性栏目？** 先按 TOC、作者/版块 h1、作品 h2/h4 划定范围。无法划定作品的文字必须进入待复核队列，而不是忽略。
2. **这段在当前作品里是什么？** 先判断明确标识（词牌、作者、`◎/◆`）；其次判断特定分册的已验证排版（如纳兰的独立题序）；再考虑有记录的作品级例外（如周邦彦两首长考证）。证据不足保持 `unknown`。
3. **它最后去了哪里？** 对任何可处理的块记录被归入某字段、明确跳过，或待人工复核。不要把“程序没输出”当作“已排除”。

## 第一阶段已实现：源块去向检查

`audit_extraction` 现在调用 `analyze.coverage.source_block_coverage`，在每册选中的 XHTML 内逐项比对：

| 去向 | 意思 | 本轮处理 |
|---|---|---|
| `handled` | 在中间结构中有逐块证据；**不等于语义已校对** | 保留原本字段与 warning |
| `excluded_*` | 结构性 h1、明确导读/总评区域或已核实的非作品标题及其段落 | 统计排除理由，后续人工抽样 |
| `untracked` | `h1/h2/h4/p` 中有源块没有被抽取或明确跳过 | 记录文件、块号、样式、长度，优先检查 |
| `unsupported_text` | 原 XHTML 在上述标签以外存在独立文本节点（如直接写在 div/li 内） | 单独统计，避免把未知结构误判为全面覆盖 |

工具只记录这些段落的**位置和结构**，不把商业资料正文写入 Markdown。完整异常数量保留在私有 JSON 中，Markdown 只展示前 10 处作为待审样例。

覆盖统计只针对 **当前作者词集 TOC 选中的 XHTML**；其他 EPUB 文件、图片文本及文学语义正确性不由这些计数保证。某些被称作 `excluded` 的编辑性材料仍需抽样核验；暂不把新统计直接作为导入的硬性门槛，先从真实 15 册看现状。

## 第二阶段：针对差异升级规则，而不是十五套重复程序

根据第一阶段真实审计结果，将稳定规则逐步整理为：共用规则、分册配置、少数带来源证据的作品级例外。优先为**真实反复出现的差异**抽模块，不凭想象铺十五个空配置文件。每条分册例外应包含适用卷、识别证据、归类动作、失败回退及合成测试。

## 第三阶段：人工复核与终止条件

按风险顺序审：未追踪内容 / 非扫描标签文字 → `unknown` → 作者/正文边界 → 推定注评续段与行内样式 → 已成功分类的随机作品。**每次只展示小批样例，但不得隐藏总体数量。** 用户在本地核实的文字不进入公开仓库；抽取最小合成用例，修好后整套回归测试和真实 EPUB 审计一起复跑。

合格标准应同时考虑：无未经解释的丢失、异常有确定的处置、按分册和特殊版式抽样没有发现新的系统性误分类。零 `unknown` 或零 warning 单独都不证明抽取准确，不据此宣称逐字校勘完成。

## 接下来的真实验证

在包含私有 EPUB 的用户本地仓库运行：

```bash
python -m scripts.corpus.epub_import.diagnostics.audit_extraction
```

分享报告的结构性摘要即可，尤其每册的 `未追踪源块`、`其他标签文字`、`待分类段落` 与实例结构；不提交 `../poeticus-data/reports/epub-import/*.json` 或原书内容。先根据完整 15 册结果决定哪些是缺陷、哪些是有意排除，再继续拆分分册规则。


## 第一份真实全量源块审计（2026-10-02）

15 册的第一次源块审计中，14 册的 `untracked` 均为 0；姜夔词集有 5 个位置，集中在 `text00264.html` 至 `text00268.html`，均为文件开头第 2 块、`p.kindle-cn-para-no-indent1`、12～15 字。所有选中分册的 `unsupported_text_nodes` 都为 0。这些是审计器的**观测值**，不是十五册分类语义已经全部正确的证明。

代码检查发现，当前 `is_chronology()` 已识别带四位年份的 `p.kindle-cn-para-no-indent1`，将内容放进临时 `section["chronology"]`；但遇到第一首作品之前的年代标记时 `current` 为空，因此未添加逐块审计证据。更重要的是，`convert_to_poem()` 目前并不导出 `chronology`，不能将这种块视作已经完整存入最终 Poem。

新版 `source_block_coverage` 将**满足年份匹配条件**的年代块标成 `internal_chronology_not_exported`（无论是否曾登记过中间证据），单独给出块号及长度，不计入 `handled`、`excluded` 或 `untracked`。非年代文字不会仅因同一个 CSS 类而得到这种待遇。真实姜夔五块是不是全部匹配该条件，仍需用户再次运行一册审计来证实。

后续需要明确产品对编年资料的处置：要么建立可靠的外围来源元数据，要么明示有依据的省略理由；**不能只是把审计数改成零**。本轮没有贸然改动 `Poem` 业务 Schema，也没有上传书中文字。

## 分类准确性抽样第一轮（人工复核试运行）

使用 `scripts.corpus.epub_import.diagnostics.sample_classification`，从真实 EPUB 提取后的证据中生成小批量分类复核任务。不修改抽取规则，也不向商业语料写回标注。

```powershell
python -m scripts.corpus.epub_import.diagnostics.sample_classification --round 1 --limit 5
```

生成两个报告，均默认位于 gitignore 保护的 `../poeticus-data/reports/epub-import/`：

- `classification_review_plan.md`：只有书名、作品 ID、块号、角色、需要人回答的问题，**没有原文**，可以直接拿来讨论分配复核任务。
- `classification_review_private.md`：在本地展示每个目标块的前后原文、样式、DOM 路径与当前抽取角色，**含商业出版物原文**，不要提交到公开 GitHub，也不应原样整体分享。对无告警但含注评的作品，会额外显示词牌、小序、正文、注释、评论的代表位置。

第一阶段采用确定性的轮次轮换（`--round 2`、`--round 3`）和按作品去重，优先选择五种情况：推定评论续段、推定注释续段、正文中的特殊字体、无告警但含注评的复杂作品、无告警的普通作品；每批尽量来自不同分册。某类候选为空则跳过。

**注意：这只是为了高效发现分类逻辑缺陷的分层诊断，不是随机统计抽样，也不能从 5 个例子判断是否达到 95% 的字段准确率。** 每轮由用户反馈「正确 / 应归为某字段 / 仍无法判断」，由开发侧将有根据的结果转成分册规则与合成回归测试；以后需要另外建立有代表性的随机标注集才能报告准确率。

## 行内样式是否等于校勘标记？先核对再分类

第一轮人工样本 R01-03（李煜《谢新恩》，`text00045.html` 块 2）含“（以下缺）”；但原先的 `classification_review_private.md` 仅把整个 p 展开为普通文字，没有呈现 span 内部内容与 CSS，**不能据此证明“（以下缺）”用了特殊字体**。`inline_body_style_review` 只说明正文段落有独立样式的 span，而且可能是段内别的词句。原书阅读器呈现的字形差异也未被验证。

新增只读的全册结构诊断（不改正文归类）：

```powershell
python -m scripts.corpus.epub_import.diagnostics.audit_inline_styles --output ../poeticus-data/reports/epub-import/epub_inline_style_audit.md
```

它对所有正文段落同时检测两件事：是否触发 `inline_body_style_review`，以及是否出现明确形态的 `（以下缺）` 残缺标记（兼容半角括号）。分别统计残缺标记是否处在带样式 span 内、是否出现在完全没有样式告警的段落，按分册聚合样式 class/style 和块号。报告**只含结构、计数与源位置，不含商业原文**。

定位李煜原始标签可单独运行：

```powershell
python -m scripts.corpus.epub_import.diagnostics.inspect_source --html text00045.html --block 2 --before 0 --after 0 --show-html --book "李煜词集（附：李璟词集 冯延巳词集）" --output ../poeticus-data/reports/epub-import/nantang_030_markup_private.md
```

后者**包含原文，只能留在本地**；要交流时截取必要的最短 HTML 片段即可。先确认“（以下缺）”是否与 CSS span 对齐、其他 56 处样式是否同一类，再决定是否需要专门的行内校勘数据结构。无证据时不得直接删除正文中的残缺标记，也不得将所有样式 span 一律当注释。

### 行内残缺标记：真实审计结果与保守标记

用户提供的十五册结构审计（2026-10-02）显示：7,328 个正文源块，58 块发生行内样式告警（其中样式签名 `kaiti` 38 次、`font1` 20 次）；**只有李煜《谢新恩》 `text00045.html` 块 2 出现明确的「（以下缺）」字样，且整段标记位于带样式 span 内**。结构审计不证明阅读器视觉效果明显，也不能把其他 57 个样式告警归入校勘标记。

抽取器现在对正文里的明确 `（以下缺）`（兼容半角括号）生成 `inline_editorial_gap` 结构化 warning，记录 XHTML 块号、展开后的正文起止字符位置、标记、是否位于带样式 span，以及 `retained_in_body_pending_schema` 状态；**不删除、不搬移、不猜测缺字数量**，原 `PoemContent.text` 逐字保持不变。这个 warning 表示已识别的编辑性标记，不代表整个段落不能使用，也不把它误当成原作者的文学表达。多处相同标记时暂不强行把位置对应到某个 span。

`audit_inline_styles.py` 与抽取器共用同一个确切标记正则和样式判断函数。真实源文的完整标签尚未通过 `inspect_source --show-html` 逐字核对；后续如确有使用需要，再讨论是否为产品阅读页加入行内校勘片段的单独数据结构。不要为了这单一已知案例贸然改动所有正文的序列化格式。

### 行内 `font1` 与 `kaiti` 的独立取样（2026-10-02）

真实 `inspect_source --show-html` 抽查显示：

- 黄庭坚《醉落魄》 `text00214.html` 块 679：`p.font3` 正文后跟 `<span class="font1">`，内部是与前面词句相联系的石曼卿故事说明，整段目前归于 `text`。
- 辛弃疾《西江月·为范南伯寿》 `text00278.html` 块 135：正文上片结束后插入 `<span class="font1">`，内部是范南伯生子情况说明；这段也整体归于 `text`。

**修正此前错误**：第二个样本确实是 `font1`，不是 `kaiti`。两处能够证明存在行内文字类别混杂，但不能证明 20 个 `font1` 都是注释，更不能据此把 38 个 `kaiti` 自动归类。另一方面，究竟是编者加注还是词人原注，也未由 XHTML 样式直接决定。

新增 `inspect_inline_samples`，按源 `span` 的真实 class 分组；每类优先取不同分册，再从其余位置分散选择；结构计划与包含源文字/HTML 的私有报告严格分开。下一轮只需：

```powershell
python -m scripts.corpus.epub_import.diagnostics.inspect_inline_samples --style kaiti --per-style 3
```

生成 `../poeticus-data/reports/epub-import/inline_style_review_plan.md`（可分享无原文）和 `../poeticus-data/reports/epub-import/inline_style_review_private.md`（含版权正文及原始 span，只供本地人工复核）。待核实 `kaiti` 版式后，再设计明确区分**行内原文**与**行内附注/残缺标记**的结构；当前 `PoemContent.text` 一字不删，避免未经确认的规则扩大影响。

### `font1` 自注与 `kaiti` 分页：第二轮语义复核（2026-10-02）

用户进一步核对原书后指出：辛弃疾《西江月·为范南伯寿》 `text00278.html` 块 135 的行内 `font1` 是**作者自注**；黄庭坚《醉落魄》 `text00214.html` 块 679 的 `font1` **疑似作者自注**，尚待更直接的出处验证。后一处不能据“字体相同”就当作已确认作者身份。黄庭坚该首块 677 是**作者自序**（原 `prefaces` 分类正确），块 680—683 是**独立注释**（原 `annotations` 分类正确）。

最新 `kaiti` 私有 XHTML 样本验证三种截然不同的情况：李煜 `text00045.html` 块 2 的 `span.kaiti` 是明确编辑性残缺标记；纳兰 `text00304.html` 块 123 和 `text00306.html` 块 343 的 `span.kaiti` 均紧接空页码锚点 `<a id="page…">`，包住跨页后的**词正文**。因此 `kaiti` 不是“注释”的语义标志。仅当 `span.kaiti` 紧接空 `page\d+` 锚点，且后方仅剩排版用换行/空白时，现有抽取器不再报普通行内样式疑似注释，正文原样保留；不满足结构条件的样式继续接受复核。

目前采取**保守的可逆处理**：辛弃疾与黄庭坚上述位置分别新增 `inline_author_note`、`inline_author_note_candidate` 类型的来源证据，包含该 XHTML、源块、原展平文字中的位置及原始字词；均以 `retained_in_body_pending_schema` 标记，并在 `PoemContent.text` 中原样保留。这些证据暂时通过 Poem `warnings` 持续到中间导出，**不意味着已生成可供前端直接使用的纯净正文或独立自注字段**。其他 `font1` 尚未核实，不得推广为通用删注规则。

未来若产品需要纯词文与注释分别呈现，需设计 `inline_notes` 结构明确：作者自注/编者注/未证实来源、原书位置（正文段落号及字符区间）、字词内容、是否可从正文展示中移除。应避免仅删除一段 span、使注释在文本和结构化字段中重复或造成源文字丢失。题前作者自序继续使用 `prefaces`，后世独立引证注释继续使用 `annotations`。

### `font1` 十处新样本与可逆行内附注字段

用户在本地生成的 10 个真实 `font1` 样本（黄庭坚与辛弃疾）全都表现出**词句之外的解释、记事或引文说明性质**，但仅凭 XHTML 类型还不足以核定每条注释的历史作者。涉及的位置包括：黄庭坚 `text00214.html` 块 696、755；辛弃疾 `text00278.html` 块 519、520；`text00280.html` 块 87；`text00281.html` 块 754；`text00279.html` 块 12、188、243、424。用户此前已单独复核黄庭坚 679、辛弃疾 135。其余未审样式不可据此臆断。

尤其辛弃疾 `text00279.html` 块 243，`<span class="font1">` **只包住引文的引导词**，真正引用的诗句在 span 外。多处记录还有尾句号在 span 外。这证明“把所有 font1 文本截出后删除”可能造成正文残留注释，不能作为已通过的自动净化规则。

新增 `PoemContent.inline_notes`（**中间抽取 JSON 的字段，尚非前端阅读器的数据格式**），为 `p` 词正文中的每段 `span.font1` 保留：

- `source_html`、`source_block`，`paragraph_index`（正文段落数组的 **0 起始** 下标），`start/end`（以原展平段落内容为单位，前闭后开）；
- `text`、`span_class`、`origin`（仅此前用户确认的辛弃疾 `text00278.html` 块 135 为 `confirmed_author_in_reviewed_source`，其余 `unverified`）、`boundary`；
- `punctuation_outside_span`、`body_retains_note: true`，明确记下原文仍保留这些内容；
- 当注释引言以冒号结尾、接下来为书面引号文本时，`boundary: citation_continues_outside_span`，并给出 `inline_note_boundary_review` warning。无法唯一匹配 span 内容、或 span 含复杂换行/图片字时发出 `inline_note_offset_review` 而**不生成假位置**。

预处理未改变原来的 `content.text`：目前字段是**可追溯候选附注清单**，不能把 `inline_notes` 与 `text` 同时作为纯净诗词内容展示，否则会重复。`pipeline.normalize` 在字形占位符替换后对附注的字符区间重新定位，并核验 `[start:end]` 与附注文字一致；不一致则禁止导出，避免错位。用户确认为作者自注的范南伯样本保留出处判定；其他黄庭坚、辛弃疾样本**不能因为使用 font1 就自动获得“作者自注”身份**。

如果未来要导出可供前端直接阅读的纯词文，应先完成剩余少量 font1 样本与跨 span 引文的确认，并定义专门的可逆原文片段序列（例如 `verse` / `inline_note` / `editorial_gap`），同步处理句号、行分隔、位置与渲染，不能在还原信息不完整时直接从正文里删字。现有 `prefaces` 作者自序与 `annotations` 后人独立注释保持不变。

已经核查的 `font1` 位置共 12 处。若要把尚未人工看到的源段落全部补齐，不需要重复查以前的样本：

```powershell
python -m scripts.corpus.epub_import.diagnostics.inspect_inline_samples --style font1 --per-style 15 --remaining
```

`--remaining` 只按已复核源坐标跳过 12 处 `font1`，**不是宣称全部十二处的历史注释作者都已确认**。输出文件与之前同名（分别为无原文的 review plan、带原文的 private packet）；不公开上传商业语料。用户原始全量审计共 20 处 `font1`，所以在这套未变的 EPUB 版本中，预期还有约 8 处待看，实际以脚本报告为准。
