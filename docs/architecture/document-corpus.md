# Document Corpus：本地 PostgreSQL 文献库（2026-10-19）

关联 [#133](https://github.com/montricwang/poeticus/issues/133)、[词话检索实验](../../scripts/experiments/README-document-rag.md)。

## 本轮已实现

四本维基文库 EPUB → **逐条从 XHTML 回读并和既有试验快照做完全一致性核对** → PostgreSQL `document_corpus` Schema。保留原本 JSON、EPUB、16 题 Eval、58 批 Qwen 向量，不重新计算昂贵 Embedding，不改现有 Poem Retrieval 或 `public` schema；后续在同一开发分支上新增了**本地可选的 Agent 文献检索工具**。

本地 PostgreSQL 18（Windows，`localhost:5432`）已执行 `db/document_migrations/0001_documents.sql` 并完成导入。实测：4 个 document、4 个 version、938 个 node（含 22 个卷/分组节点）、916 个 Section 对应的 Chunk；重复导入不新增行，3491 条 `public.poems` 保持不变。

**2026-10-19 更新**：初次导入时本机 PostgreSQL 18 尚无 `vector` 扩展；随后已在服务端安装 pgvector 0.8.7，并执行 `0002_pgvector.sql`，导入全部 916 条缓存向量。安装 Python 的 `pgvector` 包本身不等于 SQL 扩展已经可用；公开部署仍需独立核查数据库与模型资源。

## 表与职责

两份独立迁移文件位于 `db/document_migrations/`；版本记录在 `document_corpus.migrations`，不影响 `scripts/corpus/db_import.py` 现有诗歌迁移入口。

| 表 | 职责 |
| --- | --- |
| `documents` | 作品及常用书目字段：title / author / dynasty / genre |
| `document_versions` | 每份原始来源快照：EPUB SHA256、source URI、版别标识、授权核查状态 |
| `document_nodes` | 自引用 `parent_id` 的文献层级；卷、可选分组、Section 正文、标题及原 EPUB 定位 |
| `retrieval_chunks` | 派生索引视图：父 Section ID、字符区间、检索文本、SHA256 |
| `chunk_embeddings`（本地已启用） | 1024 维 pgvector，基于已确定模型与文献版本的 Chunk 向量 |

`metadata JSONB` 只存来源差异，`id`、`sort_order`、`parent_id`、`source_key`、`body_text` 等需校验/连接的字段是正式列。一级卷/分组不是 Chunk。节点带的 `source_locator` 保存 `epub_file`、`section_id`、`heading_id`；不会将未确认的官方段落编号冒充稳定链接。

当前词话实验以一个 Section 为一个 Chunk，格式仍是 `title + ' ' + text`，保持既有 Qwen 向量缓存可直接迁移；个别长条目可能超过模型 512-token 编码上限，后续再独立评估分片和上下文回读，不在这轮改动 Benchmark。

**Schema 是通用的，EPUB 解析器是针对当前来源格式的。** 当前 `scripts/corpus/document_db.py` 使用本地首批语料 JSON 作为**四书清单与卷组顺序基准**，逐条从原始 EPUB 重新提取标题和原文，比对完全一致后导入。它解决了这四本书可复现导入的问题；新格式或新书仍需相应解析 Adapter/结构审查，不能把它称为已经能自动适配一切 EPUB。

## 使用方式

在 `/home/montric/projects/poeticus`：

```bash
# 无数据库操作：核对全部四本 EPUB 与原文快照
.venv/bin/python -m scripts.corpus.document_db --check

# 仅首次建 Document Corpus 表（可重复执行）
.venv/bin/python -m scripts.corpus.document_db --migrate

# 幂等导入四本书；同一版本的已入库正文、标题与排序有漂移会失败回滚
.venv/bin/python -m scripts.corpus.document_db --import

# PostgreSQL 服务端已安装 vector 扩展之后，才运行：
.venv/bin/python -m scripts.corpus.document_db --migrate-vectors
.venv/bin/python -m scripts.corpus.document_db --import-vectors
```

数据库 URL 沿用私人 `.env` 的 `POETICUS_DATABASE_URL`；脚本不会输出密码。实验语料路径默认 `../poeticus-data/document-corpus/`，仍在 Git 仓库外。大体目录由 `POETICUS_DATA_ROOT` 覆盖，但当前四书向量缓存与 Eval 应使用相同版本。迁移失败时事务回滚；初次导入先运行 `--check`。

向量导入会检查缓存 `spec.json` 中的文献 SHA、模型、向量维度与顺序，使用已有 `batch_*.npy`，不会重新运行 Embedding 模型。此向量版本使用 `Qwen/Qwen3-Embedding-0.6B`、1024 维、512-token 限制。

## 真实验证与后续

- `--check` 对比 916/916 Section 的标题、锚点、正文，全部匹配。
- PostgreSQL 内 `documents=4`、`document_versions=4`、`document_nodes=938`、`retrieval_chunks=916`，两次导入后数量不变。
- 通过 SQL 从《人间词话》「有我之境与无我之境」Chunk 回读正文、父组和 EPUB 标题锚点。
- 核对了原 `public.poems` 数量 3491，现有 `public.schema_migrations` 未增新记录。
- 2026-10-19：本机 PostgreSQL 18 已安装并启用 pgvector 0.8.7；向量表建成并导入 916 条缓存 Qwen 向量，真实 SQL 向量查询 Top5 与本地 numpy 计算同序。
- 独立文献检索工具 `search_documents` 已接入 LangGraph Agent，与 `lookup_allusion`、`lookup_reference`、`search_predecessor_texts` 并列。后端从 PostgreSQL 同版条目派生 BM25，查询向量由本机 Qwen3-Embedding-0.6B 懒加载生成，pgvector 精确 Top50 + BM25 Top50 做 RRF 融合，返回 Top5 评论原文及书名、卷次、EPUB 来源锚点。LLM 可给出最多两条别称/关键词扩展查询，程序始终保留用户原始问题；尚不支持跨版本混检和独立文献阅读 UI。
- 在本地私有 `.env` 中设置 `POETICUS_DOCUMENT_RAG_ENABLED=true` 才向模型开放工具；模型目录也必须存在。未启用或未安装检索模型的 Railway 环境不加载大模型，也不会宣传此工具。重启后端进程以读取更新的环境变量。
- 可选实验开关 `POETICUS_DOCUMENT_RERANK_ENABLED=true` 在 Hybrid 后加载本机 `Qwen3-Reranker-0.6B`，每个查询扩大候选到 Top20，跨查询合并 Top16 后精排，最终仍取 Top5。默认关闭；模型不可用时不启用，推理报错时回退**原先每查询 Top5 的 Hybrid**。16 道开发题未证实精排优于旧基线；也未将 Windows llama.cpp HTTP Rerank 服务接入生产路径。
- 现有 `document_versions.rights_status` 均为 `unreviewed`；本轮限本地实验，**尚未开放文献全文公开服务或 Railway 部署**。后续上线须核对许可与模型部署方案。

四书 EPUB 自身声明 CC BY-SA 3.0 / GFDL，但数据库的 `rights_status` 统一为 `unreviewed`；这不是针对各版文本的再发布许可审查结论。原文版本亦未对照纸本校勘。对外阅读或全文公开应另核来源和再分发条件。
