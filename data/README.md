# 本地语料数据：哪些必须备份，哪些可以重建

`data/` 是 Poeticus 的**私人本地工作区**，不是应用运行时的公开数据目录。商业 EPUB、带原文的中间 JSON、人工辨字结果和本地诊断报告都不应提交公开仓库。

## 最重要的三层

| 路径 | 性质 | 从头重建是否必需 | 说明 |
| --- | --- | --- | --- |
| `data/raw/历代名家词集精华录.epub` | 原始输入 | **是** | 准确版本的源 EPUB；应在仓库之外另有备份 |
| `data/raw/glyph_maps/*.json` | 人工校对结果 | **是** | 已确认图片字的 source/display 映射；不能靠程序自动恢复 |
| `data/output/all_normalized.json` | 已验收中间快照 | 否 | `db_import.py` 默认直接读取它；可由前两项和对应代码版本重新生成 |

如果目标是“真正从零开始重新解析 EPUB”，前两项加对应 Git commit 就是核心。  
如果目标只是“数据库坏了，重新建私人 PostgreSQL”，保留 `all_normalized.json` 可以跳过耗时的 EPUB 抽取和人工复核阶段。

## 其他文件如何看

| 路径 | 是否可重建 | 清理建议 |
| --- | --- | --- |
| `data/output/<slug>.json` | 是 | 全量导出验收后可删 |
| `data/output/<slug>_normalized.json` | 是 | 内容已汇入 `all_normalized.json` 时可删 |
| `data/output/all_manifest.json` | 是 | 方便核对，可留；数据库导入本身不依赖 |
| `data/reports/epub_import_preflight.json` | 是 | 需要重新做 glyph review 时再生成 |
| `data/reports/glyph_review_backup.json` | 部分冗余 | **建议额外备份**；glyph maps 完整时不是运行必需输入 |
| `data/reports/glyph_review_images/`、HTML、TSV | 是 | 人工决定写入 glyph maps 后可删 |
| 其余 `data/reports/*` 审计/抽样/DOM 报告 | 是 | 排障结束后可删或私人归档 |

## 从 EPUB 重建私人数据库

```powershell
python -m scripts.corpus.epub_import.import_poems --all --check
python -m scripts.corpus.epub_import.import_poems --all
python -m scripts.corpus.db_import --check
python -m scripts.corpus.db_import --migrate
python -m scripts.corpus.db_import --import
```

如果预检提示仍有未映射图片字，才进入 `scripts.corpus.epub_import.review` 下的人工辨字工具。正常情况下，已经完整保存的 `glyph_maps/` 会让这一步直接通过。

## 从现成快照重建私人数据库

已有可信的 `data/output/all_normalized.json` 时，可以直接：

```powershell
python -m scripts.corpus.db_import --check
python -m scripts.corpus.db_import --migrate
python -m scripts.corpus.db_import --import
```

## 重建公网作品库

公网 Railway PostgreSQL 不直接读取 EPUB 或本地 JSON。先重建/确认私人 PostgreSQL，再通过：

```powershell
python -m scripts.corpus.public_corpus_transfer --check
python -m scripts.corpus.public_corpus_transfer --apply --confirm-publish
```

脚本只复制白名单阅读字段，不把 `poem_source_texts`、原始段落、私人注评或来源证据发布到公网。

> 不要把“被 .gitignore 忽略”理解成“没价值”。忽略只是表示它不应进入公共 Git。运行 `git clean -fdx`、清理磁盘或换电脑前，先确认原 EPUB 和 `glyph_maps/` 已有项目目录之外的备份。
