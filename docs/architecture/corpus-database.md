# Poeticus 作品数据库：初始 Schema 与本地导入

本文记录 2026-10-03 的作品库决策。旧 docs/roadmap.md 仍将 PostgreSQL 放在 v0.2；用户已在本轮决定提前为 3491 首候选作品准备数据库。当前 PR 仅实现建表和私有本地导入，**没有接入前端阅读列表或 API**。

## 两张业务表

- poems：每首阅读作品一行。永久 UUID、来源中间记录 ID、原书全局顺序、作者/词牌/词题/寓声名、body_segments（阅读正文片段数组）、prefaces、inline_notes、lacunae、review_status、text_version。
- poem_source_texts：对应的本地来源证据。一行对应 poems 的一行，保留 original_segments、original_inline_notes、source_title、source_sha256，以及目前可能为空的 source_locator 和 source_edition。
- schema_migrations：技术表，仅管理已经运行过的数据库结构变更版本；不是第三张文学业务表。

原书顺序直接采用 all_normalized.json 中已有的数组顺序，导入时生成从 1 开始的 source_order。Poem UUID 首次插入时随机生成并持久化。原始 su-shi-001 一类编号与顺序有关，不是永久 UUID；source_sha256 是来源内容变化检查，也不是作品 ID。

## 转换边界

- 李清照：同一组句子直接拼接，显式空元素分隔两组；两首没有空元素的单调词合为一组。不声称所有数组元素就是上片/下片。
- 李煜和李璟：保留原片段分组，移除片段内部的 LF；原来有明确缺文的两首继续保留缺文文字（例如中文括号内的「以下缺」）。
- 其他作者：保留原数组片段。不同作者中少量三、四段结构不做文学重分片。
- 所有识别出的 inline_notes 和明确缺文标记都保留来源段落索引、原始起止位置，且重算阅读正文 segment_index / start / end / quote / text_version。未确认的行内说明不可统称作者自注。
- 位置是 Python Unicode code-point 单位。未来前端 JavaScript 的原生字符串位置是 UTF-16 单位；正式展示可点击注记之前，必须定义转换方法或统一位置编码，不能直接混用。
- 当前仅识别明确的括号式「以下缺」标记；方框缺字原样留在正文，暂不把所有方框当作同一种文献缺失。
- 原始 annotations/commentaries 不入正式库，继续仅保存在本地私人 JSON；未来另建文献表与 RAG 索引时，通过已固定的作品 UUID 关联，但跨重新抽取的来源位置持久化仍需完成 Issue #62。

## 本地首次执行（项目根目录）

1. 安装 Python 依赖。
2. 确保 PostgreSQL 正在运行，通过 pgAdmin 或 createdb 创建独立的空库 poeticus。
3. 在本地 .env 中设置 POETICUS_DATABASE_URL，例如：
   POETICUS_DATABASE_URL=postgresql://用户名:密码@localhost:5432/poeticus
4. 依次执行：

~~~powershell
python -m pip install -r requirements.txt
python -m scripts.corpus.db_import --check
python -m scripts.corpus.db_import --migrate
python -m scripts.corpus.db_import --import
~~~

--check 完全离线，不需要启动 PostgreSQL；默认输入是 data/output/all_normalized.json。--migrate 和 --import 使用本地 .env 数据库连接，不会自动创建数据库。SQL 脚本在 db/migrations/0001_corpus.sql。

--import 使用一个 PostgreSQL 事务写入两张表。再次运行相同文件会跳过已有且一致的记录。如果来源文本、书中顺序或相同来源 ID 的身份信息变化，则拒绝自动覆盖并回滚。这是有意的安全限制：来源 ID 可能因重新抽取而漂移，在 Issue #62 完成来源坐标和匹配策略前不能无条件 UPSERT。重新建空库会产生新的 UUID；如需跨重建维持身份，应备份数据库或在后续任务中导出持久身份映射。



## 只读作品 API（Issue #65）

此 API 只用于本地开发验证。在项目根目录启动已有 FastAPI：

~~~powershell
uvicorn api:app --reload
~~~

确保本地 .env 包含 POETICUS_DATABASE_URL 且 PostgreSQL 已启动。

- GET /api/poems?limit=20&offset=0：目录页，返回 items / total / limit / offset。items 只包含 UUID、原书排序、词人、词牌、词题、寓声名、正文开头不超过 60 字和校审状态，不携带全部正文。默认 20 条，最多 100 条。
- GET /api/poems?author=苏轼&tune=念奴娇：作者与词牌精确筛选；q=... 则按作者、词牌、词题、正文做不区分大小写的字面包含搜索，不要求全文索引。
- GET /api/poems/{UUID}：返回一首阅读作品的 body_segments、prefaces、review_status 和 text_version 等。未知 UUID 返回 404；无效分页或 UUID 返回 422；数据库未配置或暂时不可用返回 503。
- 访问 http://127.0.0.1:8000/docs 可以使用 FastAPI 自动生成的交互式 API 页面验证，不需要自己拼接全部 URL。

源码分工：backend/corpus/connection.py 的 get_connection() 从私有环境变量建立短期、只读事务连接；repository.py 的 list_poems()/get_poem() 执行参数化 SQL；router.py 定义 HTTP 入参和 Pydantic JSON 输出；api.py 注册路由。

API **只查询 poems**，不读取或暴露 poem_source_texts，且目前不返回 inline_notes / lacunae。它不是生产级公开作品库服务：公开部署前仍需核对商业 EPUB 衍生正文和词序的使用授权。生产部署以后可针对流量考虑连接池和搜索索引，本轮没有引入。

通过合成测试并不等于本地真库接口已验证。请在本地对照一首李清照词、南唐词，确认列表排序与单首阅读段落一致；前端静态 JSON 在此阶段保持不变。原始 SHA-256、源段落以及私有注评不能通过 API 访问。

## 验收界限

- CI 使用版权安全的合成文本验证转换规则和坐标；无法代表用户私有 3491 首已在真实 PostgreSQL 通过导入。
- 用户本地执行完后，核对 --check 的作品数、行内注记数、缺文标记数，以及数据库两张表的行数。首次期望候选作品数量为 3491，但仍是 imported_unreviewed，不能说已经逐首校勘。
- 后续另做 FastAPI 目录/查询与前端路由，不在本 PR 混改静态 reader 和聊天行为。
- 源 EPUB、完整正文 JSON、现代编者注评、私有报告和 .env 不得提交到公开仓库；部署前应另行评估来源版本和公开使用权限。
