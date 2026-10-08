# Poeticus：作品数据库与发布数据链

## 1. 当前状态

Poeticus 当前以 PostgreSQL 作为作品读取的唯一运行时数据源。生产库公开读取 3491 首词作，前端不再使用静态作品 JSON 作为正式阅读数据源。当前公开数据包含晚唐、五代与宋代作者，数据库尚未提供可靠的逐首 dynasty 字段。

作品数据同时存在两个边界不同的数据库环境：

```text
私人本地 PostgreSQL
  ├─ poems
  └─ poem_source_texts

Railway PostgreSQL
  └─ 仅发布阅读需要的数据
```

私人来源证据不进入公网数据库。

## 2. 主要表

### `poems`

每首阅读作品一行，包含稳定 UUID、原书顺序、作者、`cipai`、`yusheng_title`、题目、`body_segments`、`prefaces`、审核状态和文本版本等阅读字段。

### `poem_source_texts`

本地私人来源证据，保存原始片段、来源信息、source hash 等，用于重建、核对和追溯。Web API 不读取该表，公网发布也不传输该表。

### `schema_migrations`

记录已经执行的结构迁移。迁移文件位于 `db/migrations/`，已经执行的 migration 不直接改写；新结构通过新增 migration 演进。

## 3. 私人导入

标准本地路径：

```text
private EPUB + ../poeticus-data/reading-corpus/raw/glyph_maps/
        ↓
scripts/corpus/epub_import/
        ↓
../poeticus-data/reading-corpus/normalized/all_normalized.json
        ↓
scripts/corpus/adapter.py
        ↓
scripts/corpus/db_import.py
        ↓
private PostgreSQL
```

常用命令：

```powershell
python -m scripts.corpus.db_import --check
python -m scripts.corpus.db_import --migrate
python -m scripts.corpus.db_import --import
```

`--check` 可在不连接 PostgreSQL 的情况下检查中间 JSON。导入使用事务；同一来源记录发生身份或内容冲突时拒绝静默覆盖。

字段约定：

- `cipai`：词牌
- `yusheng_title`：寓声名
- `title`：作品词题

旧私人 JSON 中的 `tune` / `yusheng` 仍由 adapter 兼容，但新输出统一使用正式字段名。

## 4. 公网发布

公网数据不是从私有 EPUB 直接生成到 Railway，而是从已经核对的私人数据库发布：

```text
private PostgreSQL
        ↓
scripts/corpus/public_corpus_transfer.py
        ↓
Railway PostgreSQL
```

发布脚本只传明确白名单列，保留作品 UUID、顺序和审核状态；不传 `poem_source_texts`、现代 annotations/commentary、原始 EPUB 或私人检查报告。

因此出现问题时按最接近错误来源的一层修：

- JSON 已错 → 回到 EPUB 抽取/normalize
- JSON 正确、私人 DB 错 → adapter / db_import
- 私人 DB 正确、公网 DB 错 → public_corpus_transfer
- 只有 schema 变化 → migration，不重跑 EPUB

## 5. 运行时读取 API

代码分工：

```text
backend/corpus/connection.py   建立数据库连接
backend/corpus/repository.py   参数化 SQL 查询
backend/corpus/router.py       HTTP / Pydantic 契约
backend/app.py                 组装 FastAPI 路由
```

公开接口：

- `GET /api/poems?limit=...&offset=...`
- `GET /api/poems?author=...&cipai=...`
- `GET /api/poems?q=...`
- `GET /api/poems/{UUID}`

目录接口只返回列表需要的摘要字段；详情接口返回阅读正文等字段。API 不暴露来源 hash、源段落、私人注评或数据库凭证。

本地运行：

```powershell
uvicorn backend.app:app --reload
```

## 6. 文本与身份边界

- UUID 是运行时作品身份；重新创建空私人数据库会生成新 UUID，因此需要保留可信数据库或身份映射。
- `source_sha256` 用于判断来源内容变化，不是作品 ID。
- `body_segments` 保留抽取后的原有分组，不擅自把所有数组元素解释为上下片。
- inline note 坐标使用 Python Unicode code point；前端 UTF-16 位置需要显式转换。
- 所有批量导入作品仍可标记为 `imported_unreviewed`，进入数据库不等于逐首人工校勘。

私人 EPUB、完整抽取 JSON、现代编者注评和数据库凭证不得提交到公开仓库。


## 7. 与 Retrieval Corpus 的边界

公开阅读库和 Text Retrieval Corpus 是两套数据源：

```text
Railway PostgreSQL
→ 3491 首公开阅读词作
→ 负责目录、正文、当前作品上下文

Werneror Retrieval Corpus
→ 853,385 Works
→ sentence / clause / BM25 / FAISS
→ 负责发现前代文本候选
```

阅读库当前没有可靠逐首 dynasty。调用 Retrieval 时缺失的 chronology context 由 Retrieval Service 在 Werneror metadata 内部做 coarse inference，详见 [Text Retrieval 架构](text-retrieval.md)。

Werneror 的 dynasty label 只服务候选资格判断；它不能回写成公开阅读库的历史断代字段。实际 probe 中，冯延巳、李璟、李煜等南唐人物在 Werneror 中也标为“唐”。

未来如果公开 Corpus 增加可靠的逐首年代，应从数据库/API 直接传给 Agent，并逐步减少 corpus-side inference。
