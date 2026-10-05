# EPUB 原书定点查询工具

目标：在本地用一次命令定位审计报告给出的 XHTML 块号，显示前后上下文、原文、DOM 路径，以及**中间**抽取角色，供人快速判断词题、题序、年代、注评、引文。

## 用法

在仓库根目录执行（可从 GitHub 分支 `feat/epub-layout-rule-extractor` 拉取）：

```powershell
python -m scripts.corpus.epub_import.diagnostics.inspect_source --html text00264.html --block 2 --block 25 --book "姜夔词集" --output data/reports/jiang_source_local.md
```

然后在 VS Code 打开 `data/reports/jiang_source_local.md`：每个目标块前默认列出 2 块、后列出 4 块，附原文、块号、标签、class、DOM 完整路径，以及抽取器在对应分册中的角色。块号与 `audit_extraction` 完全一致（按 h1、h2、h4、p 在源文件中的顺序计数）。

想看到更多上下文时可追加 `--before 4 --after 8`。长段落默认只显示前 300 字；使用 `--full` 才显示全文。

## 其他查询方式

```powershell
# 根据原文片段在指定 XHTML 中找对应的块号；不需要先数段落
python -m scripts.corpus.epub_import.diagnostics.inspect_source --html text00264.html --find "1191" --book "姜夔词集"

# 需要辨别字体包装、图片字、换行时，显示原始 XHTML
python -m scripts.corpus.epub_import.diagnostics.inspect_source --html text00241.html --block 20 --book "周邦彦词集" --show-html --output data/reports/zhou_markup_local.md

# 使用其他 EPUB 文件
python -m scripts.corpus.epub_import.diagnostics.inspect_source --epub "D:/books/my.epub" --html text00264.html --block 2
```

注意：`--find` 只检索指定 XHTML，并不检索整本 EPUB；`--book` 必须是完整分册名，否则不显示语义分类证据。`--show-html` 显示真实源标签和属性，但不是按 CSS 渲染的书页，仍需在阅读器里核对视觉布局。`--book` 显示的是 Parser 的**中间归类**，不是文学校勘的最终结论。

## 隐私与协作方式

**快速查询报告包含商业出版物原文，只允许本地保存，禁止 commit 或整体上传。** `data/reports/*` 已在 `.gitignore` 中。需要和 AI 讨论时，优先给出结构、短片段或个人判断，不必提供整首词或大段现代注评。`inspect_dom_hierarchy` 是另一个只输出结构、不输出原文的脚本，适合安全共享 DOM 层级报告。

以后 AI 应给用户一条具体命令（XHTML 文件名 + 1～3 个块号 + 适量上下文）并提出一个确定的问题；用户只需查看本地输出/实际书页后回答；AI 再负责修改分类规则和测试。不要让用户为同一版式遍历几十处。
