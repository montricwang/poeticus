# EPUB 作品导入 SOP

本文件记录 Poeticus 从 EPUB 导入作品数据时的标准检查流程，以及已经发现或需要主动排查的风险。它不是某一册书的解析说明，而是处理半结构化文献数据时的操作清单。跨项目的**问题诊断与工具选型原则**归入《教学与开发协作手册》，不在本 SOP 中重复扩写。

对应实施 Issue：[#48](https://github.com/montricwang/poeticus/issues/48)；基础导入由 [PR #52](https://github.com/montricwang/poeticus/pull/52) 合并，十五册全量审计与导出由 [PR #59](https://github.com/montricwang/poeticus/pull/59) 于 2026-10-02 合并。运行与数据限制以本 SOP 的最新章节为准。

## 1. 核心原则

1. **先认识数据，再写规则。** 不根据一两个样本推断整本 EPUB 都使用同一种 XHTML 结构。
2. **提取层保持可追溯。** 不静默改字、不擅自统一异文；但产品最终 Schema 不需要保存所有原书信息。明确哪些内容有意跳过，避免错误混入作品。
3. **规范化有明确边界。** 提取过程中临时保留 DOM 标题片段，再生成中间 Poem 的 `tune`、`title`；贺铸可另有 `yusheng`。中间 Poem 不保存 `title_raw`，如需校对返回私有 EPUB；它还不是前端或数据库的最终格式。
4. **程序成功运行不等于数据正确。** 结构覆盖、合成测试、真实 CLI 与文学文本校勘需要分别验证。
5. **不确定就进入 warning / review。** 不让启发式规则把猜测伪装成确定事实。
6. **原始资料可追溯。** 规范化结果尽可能能够回到原 EPUB 中对应的文件、锚点或上下文。
7. **私有原始资料与公开代码分离。** 商业 EPUB、现代注释、派生报告、图片映射和真实抽取结果不直接提交公开仓库；测试应采用合成内容。

## 2. 标准流程

```text
Raw EPUB
  ↓
Profiling / 数据探查
  ↓
Extraction / 提取
  ↓
Extraction Validation / 提取校验
  ↓
Normalization / 规范化
  ↓
Normalization Validation / 规范化校验
  ↓
Review / 人工抽查
  ↓
Curated Output / 已决定可发布的内容
  ↓
Enrichment / 知识增强（后续）
```

每进入下一阶段以前，先完成上一阶段对应的最低检查。允许先写一个**最短可运行的读取 Demo**，但不能据此宣布规则能覆盖其他作者或整册数据。

## 3. Profiling：先认识 EPUB 与解析工具

面对新 EPUB、作者卷或明显不同的章节结构，优先回答：

- [ ] 目录、spine 与实际 XHTML 文件怎样对应？是一首作品一个 HTML，还是整卷共用 HTML + anchor？
- [ ] 标题使用哪些标签：`h1`、`h2`、`p`、`div`？是否由 `span`、`br`、`a` 等子节点区分部分？
- [ ] 正文与小序是否都在 `p` 中？`br`、`ruby`、`aside`、脚注结构是否影响实际文本边界？
- [ ] 是否引用外部 CSS？标题子节点的 class、字号、字体、缩进、位置是否承载区别性线索？**不能在提取 `get_text()` 后才寻找已丢失的证据。**
- [ ] 实际使用的库是否保留**原始 XHTML**、`<head>` 与 CSS 链接？`item.get_content()` 与原始 `item.content` 是否一致？
- [ ] 是否存在 `<img>`、自定义字体、私用区字符、实体、`□` 或编码不确定性？
- [ ] 不同册的相同 CSS class 是否真对应相同业务语义？哪些是局部特例？
- [ ] 各模板覆盖多少文件/作品？剩余无法归类的结构及其分布是什么？

**探查与解释分层：** DOM 和 CSS 说明原书如何组织、呈现文本，不能直接证明某个节点在文学上属于词题、调名还是小序。Profiling 先记录原始证据和分布，业务解释留给语义抽取规则。

不要求每次都重新分析已确认的 22 册；新来源、明显不同模板或同类规则反复失效时，重启有边界的调查。只有少量不确定样本时可先做分层抽样，不把全量调查当成仪式。

## 4. Extraction：在当前产品范围内正确取舍

提取阶段目标是将已确认的作品结构变成候选 Poem：

- 按已经确认的标题节点切分作品候选，保留正文段落的顺序与显式换行；
- 以源 DOM、样式与上下文共同判断词牌、词题、小序；按明确标记将 `◎`、`◆` 暂时分类；
- 在处理阶段临时保存原始标题、来源 XHTML、锚点等审计依据；图片字保留占位符及 warning；
- 根据已确认的分册模板有意识地跳过非作品，如独立组序、总评等；**不得将其默默归入下一首正文**；
- 不自动纠正文句、不把不确定的“又和……”冒充已解析词牌，不凭文学印象补缺字。

**分类决策：** 会使当前 Poem 误抽、漏抽、误归类的是本轮质量问题；组词关系、词牌异名史、通行词谱知识等是在当前产品契约外的增强能力，通常进入 Backlog。原书信息存在，并不意味着最终 Poem 必须为它增设字段。

## 5. Extraction Validation：检查是否悄悄出错

### 5.1 机器能够廉价完成的检查

- [ ] 记录总体和按册/模板的 XHTML 数、作品候选数、异常数；与目录、已知锚点数对照并解释差异。
- [ ] 检查空标题、空正文、明显过长的词牌、异常短/重复正文、意外的多段标题。
- [ ] 统计实际读取到的 CSS 文件数、匹配到的标题样式模板数；**若预期有样式而统计为零，先怀疑读取路径，不直接宣布不存在 CSS。**
- [ ] 检查 `◎`/`◆` 是否混入正文；是否存在首个标题前后未处理的含文字节点。
- [ ] 统计 `<img>`、图片字占位符、`□`、`�`、私用区字符和未完成 glyph 映射。
- [ ] 抽查首尾、跨 XHTML/卷边界及相同模板下的极端记录；检查“又”继承是否跨越了不该跨的组。
- [ ] 确认输出文件与输入文件对应，避免漏卷、意外去重和重复抽取。

**报告口径：** 对容易统计的检查给出数量、分母和适用范围；没有可信标注样本，不计算或宣称“准确率”。零告警只意味着**已设计的检查**没有发现问题。

### 5.2 真实运行与人工抽样

1. **合成测试：** 用没有版权材料的最小 HTML 验证标题拆分、前序、小序、正文、图片字、特殊模板与 warning。
2. **真实来源抽查：** 在私有 EPUB 上选择随机、异常/边界、每卷首尾以及不同作者模板样本；可并排核对原 EPUB 与抽取 JSON。
3. **目标环境集成：** 在用户真正使用的系统运行 CLI，核对文件路径、编码、依赖和实际输出；不要用 ZipBook 或 Mock 的成功代替真实 EbookLib 路径。
4. **有限语义审核：** 挑选代表性词作检查题名、小序、正文、分阕、来源；没有逐首精校则保持 `imported_unreviewed` 或等价标记。

对于没有完整正确答案的数据，可组合使用结构不变量、目录对照、跨来源差异、分层抽样及人工判断。词谱字数与分阕检查未来可作为**异常提示**，不能把不符合某一种词谱的版本自动判错或改写。

## 6. Normalization：统一表示，不替代校勘

只有 Extraction 基本可靠才做规范化：

- 输出中间 Poem 的 `tune`、`title`（可空）；贺铸的寓声名另外保存可选 `yusheng`，其余作品为 `null`。原书标题拆分证据保留在临时结构；
- 处理明确的全角/半角空格和格式差异；规范作者、collection、source；
- 保持同版同规则下的导出 ID 和已有来源线索；**当前 ID 按分册及作品序号生成，重排后可能变化**。导出结果不是已经校勘的 `reviewed` 数据；不在规范化阶段消除真实异文；
- 仅对确认的单独“又”做词牌继承，不确定时 warning；
- 区分原始缺字 `□`、视觉缺字和以图片表示的生僻字，已确认的 glyph 映射另行处理；
- 贺铸题头区分 `tune`（原词调）、`yusheng`（另拟的寓声名）和 `title`（独立作品题目）。「思越人，亦名鹧鸪天」只提取主要原调，不新增全局 `cipai_alias`；超出已核实版式的例外进入后续复核。

## 7. Normalization Validation

- [ ] 有疑问时能通过私有 EPUB 的来源文件和锚点复核标题语义；
- [ ] 规范化前后正文未发生未经允许的文本改动；
- [ ] 拆分失败有明确 warning，不能伪装成已核实值；
- [ ] ID 重新运行后稳定，同一作品没有意外重复；
- [ ] 审核状态能区别 `imported`、`needs_review`、`reviewed`、`disputed` 或现有等价值；
- [ ] 语义规则有来源/分册适用范围；前端 Poem JSON 与 ETL 输出的契约差异在**独立转换步骤**解决，不能默认 `p` 段落等于一阕。

## 8. 已知风险和默认处理

| 风险 | 如何发现 | 默认处理 |
| --- | --- | --- |
| 不同册 XHTML/CSS 模板差异 | 全量或分层 DOM/CSS 画像 | 分册解释，不以一套样式规则覆盖全部 |
| DOM→纯字符串丢信息 | 对比原始节点树与 `get_text()` 输出 | 语义分类前保留节点与样式证据 |
| EbookLib 读取可能丢 CSS `<link>` | 对比原始 XHTML 与 `get_content()` | 以经验证的原始 UTF-8 XHTML 读取路径为准 |
| 字节编码误判 | Windows/真实 Unicode 样本回归 | 显式 UTF-8 解码；合成与真实路径都验证 |
| `br`、`span`、`img` 与图片字 | 节点计数、正文占位符扫描 | 保留换行和占位符、warning；必要时人工确认 |
| 编年、小序、组序混入正文 | 逐模板检查前后相邻段落 | 确认的内容归类；不属于单篇者有意跳过 |
| 同一作者的特殊词牌/标题 | 第二文本片段、别名说明与相邻结构 | 在明确范围内抽取必要值；不引入未使用的百科 Schema |
| `□` 与不同版本异文 | Unicode 扫描、不同文献差异 | 源文本保留，必要时 `needs_review`，不自动补字 |
| 作品顺序与锚点 | 目录、spine、实际文档对照 | 明确适用规则并记录无法解释的差异 |
| 真实输出被误发布 | 提交前文件清单、历史和 `.gitignore` 检查 | 私有数据与报告默认不提交，测试用合成文本 |

## 9. 发现新异常时怎样停止补丁链

1. 记录能重现的最小输入及来源（私有资料只保存在本地），描述**观察到的错误**而不是先猜根因。
2. 判定是读取、数据画像、结构抽取、业务解释、规范化、校勘还是产品需求的问题。
3. 判断是否推翻了共同假设：当连续出现同类反例，不再单纯新增 `if`，先复核模板分布和工具读取能力。
4. 修复后补不包含商业文本的合成用例，并运行真实 CLI/相应抽样；报告每层验证实际证明了什么。
5. 更新本 SOP 的风险或规则，但只记录**可复用、可执行**的东西，避免每遇到一个作者特例就让文档无限增长。

## 10. Git 提交与发布前检查

- [ ] 原始 EPUB、现代注释与评论、派生 Markdown/JSON 报告、图片字映射、真实输出未出现在暂存区。
- [ ] 查看 Git diff、暂存文件、PR 文件清单及**提交历史/祖先**；`.gitignore` 不会自动移除已跟踪或曾提交文件。
- [ ] 旧 PR 曾经公开的内容不能因为文件从最新版本消失就宣布已经撤回；需单独评估历史链接和平台保留问题。
- [ ] 合成测试不引用私有 EPUB 段落；在合并前区分“测试通过、结构抽取完成、文学文本精校完成”。

> **停止线：** 现阶段完成的是作者词集的基础语义抽取。套词、组序、词牌别名体系、词谱字数验证、全量校勘等均已或应进入 Backlog，不自动成为当前 Parser 的完成条件。
## 11. 十五册批量预检与中间 JSON 导出（2026-10-02）

`scripts.corpus.epub_import.import_poems` 现在保留原有单册参数 `--toc / --author / --slug`，同时新增按已审计范围导出十五册的 `--all`。**不要把这些中间 Poem 记录误当成前端 `poem-library.ts` 的最终 JSON schema。**

首先只做预检，不触发任何逐字输入，不写含原文的 JSON：

```powershell
python -m scripts.corpus.epub_import.import_poems --all --check
```

该命令读取当前私有 EPUB 一次，按审计配置的十五册逐一完成抽取，检查阻止导出的未分类段落与未映射 glyph 图片字，并写入 `../poeticus-data/reports/epub-import/epub_import_preflight.json`。预检报告仅包含分册、数量、XHTML/块位置、图片文件名和 warning 类别，**不含书中词文、词序或注释**。若有未解决项，进程退出码为 2，不意味着工具崩溃；按报告处理后重跑。

只有预检全部通过，才执行：

```powershell
python -m scripts.corpus.epub_import.import_poems --all
```

这一步先在内存中规范化并核对所有分册，成功后写入仓库外的 `../poeticus-data/reading-corpus/normalized/`：每册的 `<slug>.json`（未规范化、保留图片字占位符和所有原始附注）、`<slug>_normalized.json`（映射生僻字后，保持正文与可逆行内附注位置），以及合并的 `all_normalized.json`、不含原文的 `all_manifest.json`。某册缺 glyph 映射或含未归类段落时，全量模式**不会写出任何新的正文文件**，避免误把部分成功当作完成。

默认每册 glyph 映射位于 `../poeticus-data/reading-corpus/raw/glyph_maps/<slug_with_underscore>.json`；全量模式可用 `--glyph-map-dir` 指定另一目录。只要输入本身仍有图片字，就必须先核对字形；全量模式**绝不调用 `input()`**。旧的单册模式仍可在交互终端中提取待核对图片并调用 `glyph_mapping.py` 保存人工映射；它现在也正确尊重 `--epub` 指定的实际文件，而不误用默认路径。

原始 EPUB、图片映射、报告和导出 JSON 都是本地私有数据，不要提交公共仓库。此处的“导出完成”指**保留约定字段和关键证据的中间数据层，而非整册 EPUB 无损转换**：并未按前端 `stanzas` / `preface` / `review_status` 格式转换，也未将所有 `font1` 行内自注从阅读正文中删除。下一阶段需要独立决定这些内容的审校状态与展示方式，不可仅凭字段存在宣称文学准确率。

### 11.1 本次真实预检后的图片字集中处理

十五册真实预检（用户本地，2026-10-02）：`total_candidate_poems=3491`、`total_unexportable_issues=0`、`total_missing_glyph_sites=54`、`ready_to_export=false`。54 是 XHTML 文件/图片的引用位置；重复图片在不同 XHTML 出现多次，按分册和图片 filename 合并后，理论上待辨认的**不同图片约 49 张**（以用户本地脚本统计结果为准）。不应在此阶段把真实图片/对应原书内容发布到 GitHub。

不建议直接用 `import_poems.py --all`：只会因为未解决图片字而停止。为避免旧版单册命令一张张询问，在代码根目录运行：

```powershell
python -m scripts.corpus.epub_import.review.review_glyphs --prepare
```

它读取已存在的 `../poeticus-data/reports/epub-import/epub_import_preflight.json` 和本地 EPUB，把去重后的图片字提取到 `../poeticus-data/reports/epub-import/glyph_review_images/`，生成可在浏览器打开的**本地字形画廊** `../poeticus-data/reports/epub-import/glyph_review.html`，及可直接在 VS Code/Excel 编辑的 `../poeticus-data/reports/epub-import/glyph_review.tsv`；两者都位于仓库外的私人目录。TSV 按编号对应图片，每行保留 `slug`、`src`、引用页面；只填写 `source_form`（原字），需要替代显示时才填 `display_form`（仅一字）。原字可填正常汉字、`U+XXXX` 或 IDS 组合字形；**IDS 若没有可信的 Unicode 单字替代，`display_form` 可以留空**，中间 JSON 会保留 IDS 字符序列及 `ids_transcription` 标记，不将其伪装为一个标准汉字。

填写后运行：

```powershell
python -m scripts.corpus.epub_import.review.review_glyphs --apply
python -m scripts.corpus.epub_import.import_poems --all --check
```

应用操作会先完整校验 TSV，禁止与已有分册映射相冲突，再调用现有 `glyph_mapping.save_map()` 写入每册 `../poeticus-data/reading-corpus/raw/glyph_maps/<slug>.json`。遇到难字可先使用 `--apply --partial` 保存已解决的映射；重新生成画廊时不会覆盖含人工填写内容的 TSV。若 EPUB 同一个 slug/src 名称对应不同图片内容，会停止并提示冲突，不能武断合并。预检报告若出现未找到的图片资源，也须按 XHTML 路径检查，不能盲目填字。

**给 AI 协作的建议**：用本地 HTML 打开后可以按屏幕区域截取少量字形图发来，先由 AI 识别可辨认的常见字，再人工确认疑难字；不要提交整本商业 EPUB 或整套私有字形资料。等 `--all --check` 报告无阻断项才执行 `--all`。

### 11.2 独立图片字不够明确时：本地生成极短上下文

对古籍的异体、俗字和同形字，不应该仅凭 80px 的孤立截图猜测 Unicode。为了避免错误填字（尤其是多张看起来相同的图片），增加仅输出每张待辨认图片字周围小片段的**私有定位报告**：

```powershell
python -m scripts.corpus.epub_import.review.review_glyph_contexts
```

脚本利用同一份 `epub_import_preflight.json` 依照字形画廊的原顺序（001—049 等），在原 EPUB 的 h1/h2/h4/p 块里寻找图片，最多展示每个目标两处引用的前后各 16 字，以 `⟦目标字⟧` 占位；其他图片字也用标记表示，不会凭空替字。默认保存 `../poeticus-data/reports/epub-import/glyph_contexts_private.md`，**包含局部版权文字，仅供私人核字，不提交仓库**。不覆盖已填写的 `glyph_review.tsv`，不需要重新生成画廊。用户与 AI 先确认字形再 `review_glyphs --apply`。

### 11.3 从原 EPUB 批量导出图片字所在的完整段落

字形画廊只展示图片和 XHTML 文件名。每个文件内的完整词句/注释其实仍然在原始本地 EPUB 中；不需要上网搜索，也不需要重新抽取整书。新增可单独运行的上下文导出命令：

```powershell
python -m scripts.corpus.epub_import.review.review_glyphs --contexts
```

输出 `../poeticus-data/reports/epub-import/glyph_contexts.html`：**49 张图片继续沿用原 `glyph_review.html`、`glyph_review.tsv` 的 001–049 编号，绝不根据字形相似程度合并**。自带离线图片预览、分册、XHTML 文件名、与 `inspect_source` 一致的源块号、最近章节标题及目标图片在整个原书段落中的真实位置；黄色标记为本卡图片，蓝色标记为同段其他图片。如果同一图片在多个文件、多个段落或者同段出现多次，会保留所有原始位置，不只展示一个例子。除 `h1/h2/h4/p` 外的来源不做无依据的猜测：预检记录对应图片但找不到源块时明确抛错。

**与只展示少量邻近文字的 `review_glyph_contexts.py` 不同**，这份 HTML 展示完整段落，适合复制原句搜索通行版本。生成步骤只读取原有 `epub_import_preflight.json` 和原 EPUB，**不改动/覆盖已有字形 TSV 或 HTML 填写页面**，也不写新的 glyph_map，用户可并排打开填写表和原文上下文。本地报告嵌有商业原书文字及图片，必须留在 gitignore 下，不提交公共仓库；讨论某个争议时只分享必要短片段。

### 11.4 直接导入字形画廊的 JSON 备份（用户已完成 49 张）

本地字形核对页导出的 `glyph_review_backup.json` 是结构化备份，不必重新誊抄到 TSV。实际人工校对备份与原始 `epub_import_preflight.json` 对照结果：49 条 `records` 均与来源图片/分册/顺序一一匹配；49 项 `values` 都有 `source_form`；14 项有人审定的 `display_form`；仅编号 020 的 `⿰缶吾` 暂时只有 IDS，没有可证实的 Unicode 单字替代。**这是已描述构形、尚未确定单字字形的情况，不是校对未完成。**

将备份文件放到 `../poeticus-data/reading-corpus/review/glyph_review_backup.json`（或使用 `--backup` 指定本地路径）。执行：

```powershell
python -m scripts.corpus.epub_import.review.review_glyphs --import-backup
python -m scripts.corpus.epub_import.import_poems --all --check
```

`--import-backup` 先严格校验 `poeticus-glyph-review-v1`、49 号与预检结果对应的 `(slug,src)`，核对原字符确为 Unicode 单字或以 IDS 操作符开头的结构；整批与已有私有 glyph map 存在任何冲突时拒绝覆盖，正确时分别合并写入 `../poeticus-data/reading-corpus/raw/glyph_maps/<slug>.json`。命令不打开 EPUB、不访问网络、不调用 OCR，也不会提交字形数据至仓库。若备份路径不同：`--backup "C:/Users/.../Downloads/glyph_review_backup(1).json"`。

没有可信替代字的 IDS（例如编号 020 `⿰缶吾`）**不强迫填入一个猜测的汉字**：规范化后的中间 JSON 用 IDS 字符序列在词文内占位，同时图片字的 `inline_image` warning 保留原始 `src`、`source_form` 和 `status=ids_transcription`，表示它**不是单个 Unicode 统一汉字，未来前端应通过原图或 IDS 专门显示**。当存在明确代用字，则规范化正文显示 `display_form`，warning 仍保存 `source_form`。已有 TSV 手工导入、单字 glyph CLI 也统一允许合法 IDS 不带 `display_form`。

如果 `--all --check` 输出 `ready_to_export=true`、`missing_glyphs=0`、`unexportable=0`，再运行：

```powershell
python -m scripts.corpus.epub_import.import_poems --all
```

这一步生成十五册原始/规范化 Poem 中间 JSON，以及 `../poeticus-data/reading-corpus/normalized/all_normalized.json`。此处完成的是**导出管线与人工确认字形的录入**，不是宣布古籍语义分类准确率达到 95%，也不是前端清商所需的纯净诗词结构；行内作者自注仍保留在原句，最终阅读层的拆分仍需后续实现。


### 11.5 备份与复现：区分“不可替代输入”和“可重建产物”

这里最容易混淆的是：**数据库导入会读取 `all_normalized.json`，但它并不是从头重跑 EPUB 所不可替代的源输入。**

完整从原书重建时，真正必须私下备份的只有：

- 准确版本的 `../poeticus-data/reading-corpus/raw/历代名家词集精华录.epub`；
- 整个 `../poeticus-data/reading-corpus/raw/glyph_maps/`，其中包含已经人工确认的图片字映射；
- 能确定当时规则版本的 Git commit / tag。

`../poeticus-data/reading-corpus/review/glyph_review_backup.json` 建议另存一份，因为它记录了人工辨字过程；但只要 `glyph_maps/` 已完整写入，它不是重跑导出所必需的运行输入。

如果只是**重建私人 PostgreSQL，而不想重新解析 EPUB**，保留一份已经验收的 `../poeticus-data/reading-corpus/normalized/all_normalized.json` 就可以直接作为 `scripts.corpus.db_import` 的输入：

```powershell
python -m scripts.corpus.db_import --check
python -m scripts.corpus.db_import --migrate
python -m scripts.corpus.db_import --import
```

`all_manifest.json`、十五册的 `<slug>.json` / `<slug>_normalized.json`、预检报告、DOM 审计、字形 HTML/图片/TSV 都是**可重建产物**；人工结论已经写入 `glyph_maps/` 后，可以删除日常工作目录中的这些文件。

如果连 `all_normalized.json` 也删除了，则从 EPUB 和 glyph maps 重新执行：

```powershell
python -m scripts.corpus.epub_import.import_poems --all --check
python -m scripts.corpus.epub_import.import_poems --all
python -m scripts.corpus.db_import --check
python -m scripts.corpus.db_import --migrate
python -m scripts.corpus.db_import --import
```

公网 Railway 作品库不是直接从 EPUB 或 JSON 灌入：先得到私人 PostgreSQL，再运行 `scripts.corpus.public_corpus_transfer`，只复制允许公开的阅读字段。

完整的“哪些要备份、哪些可以删”清单见 [私有数据管理](../data-management.md)。这些文件都应该保存在仓库外；历史目录若还有残留，运行 `git clean -fdx` 前必须先确认 EPUB 和 glyph maps 已独立备份。


## 12. 按需排查：来源定位和 DOM/CSS 画像

这些命令是**发生新模板或规则回归时**使用的诊断工具，不是每次批量导入的必要步骤。默认读取仓库相邻的 `poeticus-data/reading-corpus/raw/`；报告写入 `poeticus-data/reports/epub-import/`。

```powershell
# 源块定点查看：只查指定 XHTML，--book 才显示中间抽取角色
python -m scripts.corpus.epub_import.diagnostics.inspect_source --html text00264.html --block 2 --block 25 --book "姜夔词集"

# 按文本片段定位块号（不搜索整本 EPUB）
python -m scripts.corpus.epub_import.diagnostics.inspect_source --html text00264.html --find "1191" --book "姜夔词集"

# 检查具体块的真实 XHTML；带原书正文，不能公开
python -m scripts.corpus.epub_import.diagnostics.inspect_source --html text00241.html --block 20 --book "周邦彦词集" --show-html

# 检查标签的真实父子关系；仅输出结构证据，不自动证明文学语义
python -m scripts.corpus.epub_import.diagnostics.inspect_dom_hierarchy --html text00241.html --group 19-22

# 重新画像 EPUB DOM/CSS 结构（已识别的模板不必每次重新扫描）
python -m scripts.corpus.epub_import.diagnostics.profile_dom --book "苏轼词集"
```

`inspect_source` 默认显示目标源块前 2、后 4 块，长段截断为 300 字；`--before`、`--after`、`--full` 调整范围。选择 `--book` 仅展示抽取器的**中间角色**，不是已经审定的文学分类；`--show-html` 也不是按 CSS 渲染的排版效果，仍须用 EPUB 阅读器核对。给 AI 讨论时尽量使用结构和少量摘录，避免上传现代商业注释原文。

`profile_dom` 依据 TOC、标题 DOM 和静态 CSS（class、继承、选择器）画像，不进行浏览器像素渲染，也不把字体样式自动判成词题/序文。**重要的 EPUB 读取教训**：`EpubHtml.get_content()` 可能重新拼装 XHTML 并丢失原始 `<head><link rel="stylesheet">`；需要优先解析原始 `item.content`。早期所有 CSS=0 的「22 册」画像曾因此无效；目前明确 UTF-8 解码（兼容 BOM）并保留原 CSS 来源。如果报告再次出现全部 CSS=0，应先怀疑读取路径，而不是断言原书没有 CSS。

## 13. 数据语义与已确认的分册例外

本 SOP 的核心目标是**可复核的语料重建**，当前生效的具体来源分类规则、贺铸 `tune/yusheng/title`、纳兰 `prefaces` 与周邦彦评论续段等案例，统一见 [EPUB 维护地图](epub-pipeline-maintenance-map.md) 第 9 节。分册问题未解决时先保留原文 evidence，既不自动删除也不宣称已经完成逐首文学审校。
