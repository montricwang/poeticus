# 《詩詞曲語辭匯釋》本地语汇库

这是独立的 Poeticus 离线查词工具，不读写生产 `poems` 表、不注册公共 Agent Tool。

## 2026-10-20 采集快照

| 项目 | 内容 |
| --- | --- |
| 来源 | https://ccddb.net/詩詞曲語辭匯釋 |
| 原著 | 张相《詩詞曲語辭匯釋》；网页转录的印刷底本版本待核实 |
| 目录 | 539 个目录项目（537 个语汇词头、敘言和跋各一），六卷 |
| 完整采集 | 906 个原始 MediaWiki 源页面（其中 1 个目录页、905 个子页面）；SQLite 收录 537 个词头 |
| 覆盖校验 | `generator=allpages` 全前缀至无 continuation；目录及递归转引的缺页数量为 0 |
| 保存信息 | 原始 Wikitext、revision ID、编辑时间、源链接、固定版本 oldid、SHA-256 |
| 当前使用限制 | 私人本地研究；尚未核实网站数字转录的对外再利用许可，不进入 Git / Railway / 公共站点 |

一些主词头页只引用下层 `（一）` `（二）` 等义项页面。采集器递归追踪并按原文顺序展开，保留真正的来源底稿。当前 SQLite 文本是**派生索引**，不是新的校勘权威文本。站点 HTML 可能受模板更新影响，因此优先保存更底层的 MediaWiki Wikitext 与固定修订号，并可按固定 oldid 访问网页。

## 数据位置

默认使用项目同级的私有数据目录，不需要 PostgreSQL：

```text
~/projects/poeticus-data/lexicon/shi-ci-qu-yu-ci-hui-shi/
├── manifest.json
├── sources/               # 906 个 JSON 原始源页面
└── lexicon.sqlite         # 可删除、可离线重建的 FTS5 索引
```

目录 `manifest.json` 记录快照的来源及采集覆盖；每个源文件按页面标题的 SHA-256 命名，保存其真实标题、revision 信息和 Wikitext 内容 SHA-256。

## 使用

从含 `scripts/corpus/local_lexicon.py` 的工作树运行。当前代码位于 `~/projects/poeticus-lexicon`，仍使用主项目的 Python 虚拟环境：

```bash
cd ~/projects/poeticus-lexicon
~/projects/poeticus/.venv/bin/python -m scripts.corpus.local_lexicon lookup 怎生
~/projects/poeticus/.venv/bin/python -m scripts.corpus.local_lexicon lookup 遮莫

# 完全离线重建检索索引
~/projects/poeticus/.venv/bin/python -m scripts.corpus.local_lexicon build

# 从 MediaWiki API 断点续采，不覆盖已经保存的源修订
~/projects/poeticus/.venv/bin/python -m scripts.corpus.local_lexicon fetch \
  --batch-size 15 --max-batches 12 --delay 0.7
```

2026-10-20 因 WSL TLS 网络连接间歇性断开，实际先使用浏览器在原站执行 MediaWiki Action API 的前缀分页读取，再经 Windows Downloads 临时中转到 WSL 私有目录。已逐一按统一的源页面结构保存，并完成完整度验证。普通 `fetch` 使用同一套源记录格式；它只补缺，**不会默默覆盖这批历史版本**。刷新内容时需设计明确的新快照及差异复核策略。

## 解释边界

- 保留繁体、原书用字、异形词、源引文与修订记录，不能把“出现一个词”解释为它在当前作品里的唯一词义。
- 词头、目录别名用于确定性查找；短词全文检索可能返回提及该词的其他条目，需查看出处。
- 网站数字化过程中可能存在字形规范化及转录错字；词典里的说明应以来源和上下文复核。
- 这是候选证据库，不在本轮批量标注 3491 首作品，也不自动注释用户界面；后续见 Issue #335。
- 可公开浏览不代表许可全量转录再发布。公开产品使用前必须另行核对原书版本、数字底稿的版权与网站条款。

## 验收

```bash
~/projects/poeticus/.venv/bin/python -m pytest tests/test_local_lexicon.py -q
```

测试覆盖词头/别名、嵌套义项及排序、原文 SHA 变化报警、脱标记纯文本和 SQLite 索引重建。
