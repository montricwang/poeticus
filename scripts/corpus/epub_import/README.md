# EPUB import tools

这个目录只服务于**私人 EPUB → 私人中间 JSON → 数据库**的语料管线，不参与 FastAPI 在线请求。

## 日常入口

- `import_poems.py`：批量预检和导出 15 册；正常工作主要使用 `--all --check` 与 `--all`。
- `batch_import.py`：全量预检、规范化和原子写出，由 `import_poems.py` 调用。
- `config.py`：当前支持的 15 个作者词集范围。正式导入不再依赖诊断模块取得这份配置。

## 核心解析

- `epub/`：读取 TOC、原始 XHTML 与 CSS。
- `extractor/`：来源块识别、字段分类、Poem 中间结构。
- `pipeline/`：glyph 映射和规范化。
- `extract_images.py`：单册交互式 glyph 处理和 review 工具共用的图片提取。

## diagnostics/

只读诊断工具。用于理解某个 EPUB 结构、定位分类反例或验证抽取覆盖；**不是数据库重建的必经步骤**。

这里保留的是有重复使用价值、且有合成测试覆盖的工具，例如全量 extraction audit、DOM/CSS profile、source lookup 和人工抽样。早期只为某个具体 XHTML/字符写的一次性探针已删除；需要考古时直接查看 Git 历史，不再让它们占据当前工具目录。

## review/

人工图片字复核工具。只有预检发现未解决 glyph 时才需要运行。

人工决定最终必须落到 `data/raw/glyph_maps/`；HTML、图片、TSV、短上下文和 backup 都只是帮助完成这一步的本地工作材料。各类产物能否删除见 [`data/README.md`](../../../data/README.md)。

## 不要再新增“临时但永久”的脚本

- 能反复用于定位 EPUB 结构问题：放进 `diagnostics/`，并补合成测试。
- 属于人工复核流程：放进 `review/`。
- 只想临时 print 某一个文件、块号或字符：放在本地 scratch，不提交；结论若值得长期保存，写入文档或测试。
