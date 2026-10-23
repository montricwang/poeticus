# Poeticus 开发者指南

本文记录当前本地开发、数据库准备和自动化测试方式。面向读者的项目介绍见 [README](../README.md)。

## 环境要求

- Python 3.12（CI 版本）与 pip
- Node.js 22（CI 版本）与 npm
- PostgreSQL
- 开发者自己的模型 API Key
- 自行准备且有权使用的作品数据

项目代码边界：

```text
backend/    FastAPI、LLM、LangGraph、作品查询、Evidence
frontend/   React / TypeScript / Vite
scripts/    语料导入、数据库迁移与发布工具
tests/      Python 回归测试
db/         PostgreSQL migrations
prompts/    LLM Prompt 资源
```

Python 运行时统一从 `backend.*` 导入；根目录不再提供旧兼容模块。

## 1. 安装依赖

在仓库根目录：

```powershell
python -m pip install -r requirements-dev.txt
cd frontend
npm ci
cd ..
```

## 2. 本地配置

在根目录创建私有 `.env`：

```dotenv
LLM_API_KEY=替换为个人密钥
POETICUS_DATABASE_URL=postgresql://用户名:密码@localhost:5432/poeticus
LANGSMITH_TRACING=false
POETICUS_AGENT_MAX_TOOL_CALLS=2
```

`POETICUS_AGENT_MAX_TOOL_CALLS` 控制每个用户请求可执行的真实工具调用次数，默认值为 `2`，仅接受 `1–10` 的整数；非法值会使后端启动时报错。省略该项即使用默认值。模型服务地址可由 `LLM_BASE_URL` 覆盖；模型名可通过 `POETICUS_LLM_MODEL` 覆盖，输出预算可通过 `POETICUS_LLM_MAX_OUTPUT_TOKENS` 调整。

Railway 部署在 Web 服务的 **Variables** 中设置同名变量，保存后按 Railway 提示重新部署；新实例启动时读取新值。评测脚本的 `--max-tool-calls N` 只覆盖该评测进程，不会修改本地 `.env` 或 Railway 服务变量。

不要把密钥、数据库 URL 或私人语料放入前端 `VITE_*` 变量、源码或提交记录。

### 密钥及本地模型的唯一放置约定

| 类型 | 规定存放位置 | 使用边界 |
| --- | --- | --- |
| 本地 Web/Agent 的 `LLM_API_KEY`、`POETICUS_DATABASE_URL`、`LANGSMITH_API_KEY`（若启用） | 仓库根目录 `poeticus/.env`（已被 Git 忽略） | 只供本地后端读取；不写入源码、日志、前端或文档 |
| WSL Poem Retrieval 的 `POETICUS_RETRIEVAL_TOKEN` | `~/.config/poeticus/retrieval.env`（仓库外） | 仅供 Retrieval Serving 显式 `source`；详情见 [部署文档](deployment.md#4-retrieval-节点及运行条件) |
| Railway 线上运行所需的密钥 | Railway 对应服务的 Variables/Secrets | 只在托管平台管理，不从本机 `.env` 自动上传 |
| Cloudflare Tunnel 连接器 Token | Windows `%LOCALAPPDATA%\Poeticus\secrets\cloudflare-tunnel.token`（仓库外） | 只给 `cloudflared --token-file` 读取；不等于 Retrieval Bearer Token，不进入 Railway 或项目 `.env` |
| 公开 GGUF 模型本地推理 | **不需要 API Key** | 不要为了本地模型新造密钥文件；下载公开模型也不要求 HF Token |
| 本地模型权重、Tokenizer/Embedding 资产 | 仓库外同级 `poeticus-data/models/` | 具体型号、GGUF 校验值及实验目录见 [私人数据工作区](data-management.md#本地模型目录与核验2026-10-19) |

本机已检查 `poeticus/.env` 与 `~/.config/poeticus/retrieval.env` 都存在，文件权限均为 `600`；仅确认文件和变量**名称**，不记录或输出任何真实值。未来增加 API 时，优先使用已有对应运行边界的配置文件或平台密钥管理，不为了某个模型另建一套全局 Secret Store。模型的下载 URL、SHA-256 和版本可以公开记录，**Token、数据库密码、连接器命令中的凭据不能进入 Git 历史**。

2026-10-19 已在隔离环境完成 Qwen3.5-4B、DeepSeek 8B、Bonsai 27B 的 CPU / Windows Intel Iris Xe Vulkan 最小推理测试；Bonsai PTQ1_0 依赖 Prism ML 定制版 llama.cpp。Qwen3-Reranker-0.6B 也已通过本地 CPU 与 Windows `/v1/rerank` 实验，但其 HTTP 服务尚未接入 Poeticus，`POETICUS_DOCUMENT_RERANK_ENABLED` 保持默认关闭。模型加载和短输出**不证明**长文分析质量、推理稳定性或生产可用性；后续用固定词话证据单独比较输出质量、速度和内存。不要因此修改生产 `LLM_BASE_URL` 或 `POETICUS_LLM_MODEL`。



## 3. 数据库

先创建本地 PostgreSQL 数据库，再运行：

```powershell
python -m scripts.corpus.db_import --check
python -m scripts.corpus.db_import --migrate
python -m scripts.corpus.db_import --import
```

默认私有导入检查点是仓库相邻的 `poeticus-data/reading-corpus/normalized/all_normalized.json`；源 EPUB、glyph maps 与中间快照均不进入公开仓库。默认数据目录根据仓库位置计算，与当前工作目录无关；特殊部署可通过绝对路径环境变量 `POETICUS_DATA_ROOT` 覆盖。目录布局、迁移说明与恢复方法见 [本地数据管理](data-management.md) 和 [作品数据库架构](architecture/corpus-database.md)。

词话等独立文献的本地导入走另一条可复现流程，不会修改原作品表：

```bash
.venv/bin/python -m scripts.corpus.document_db --check
.venv/bin/python -m scripts.corpus.document_db --migrate
.venv/bin/python -m scripts.corpus.document_db --import
```

详见 [Document Corpus 文献数据库](architecture/document-corpus.md)。向量表需 PostgreSQL 服务端支持 pgvector，使用单独的 `--migrate-vectors` / `--import-vectors`，不可仅凭 Python 安装 pgvector 包当作已就绪。

另有**独立于 Document Corpus 和诗词数据库的私人历史语汇工具**：张相《詩詞曲語辭匯釋》的 `.venv/bin/python -m scripts.corpus.local_lexicon lookup 怎生`。源修订、索引存放于仓库同级 `poeticus-data/lexicon/`；使用与恢复方法见[词典采集和查询说明](../scripts/corpus/README-local-lexicon.md)。暂不向网页或 Agent 公开词典全文。

本地词话检索工具接入 Agent 时，需要安装可选的 Qwen3 Embedding 推理依赖（`.venv/bin/python -m pip install -r requirements-retrieval.txt`），并在私人 `.env` 中增加 `POETICUS_DOCUMENT_RAG_ENABLED=true`，然后重启后端。它按需加载本机 Qwen3-Embedding-0.6B，首次检索可能较慢；本地 PostgreSQL 须预先导入文献和向量。未配置/未启用时不会向 Agent 注册 `search_documents`，不会阻止普通 Web 服务启动。可选 `POETICUS_DOCUMENT_RERANK_ENABLED=true` 仅在本机有 Qwen3-Reranker 模型且手动启用时尝试精排；默认关闭，异常回退到原 Hybrid。当前 16 题的 Recall/延迟结果不支持默认开启；详情见 [实验报告](../scripts/experiments/README-document-rag.md)。这两个开关目前**只用于本地实验**，线上部署须先核对词话版本版权、再分发权限与模型资源预算。

### CNKGraph 新研究工具（仅本地、默认关闭）

CNKGraph 官方公开 API 限非商业研究学习（[开放资源条款](https://cnkgraph.com/Home/OpenResources)），目前尚未取得公开 Web 服务/商业用途许可。**不要在 Railway、外网 Tunnel 或公众可访问的后端开启此实验开关。**

在隔离的个人本地非商业研究环境，可在私有 `.env` 手动开启：

```dotenv
POETICUS_CNKGRAPH_RESEARCH_TOOLS_ENABLED=true
# 可选，默认值为 https://open.cnkgraph.com
# CNKGRAPH_RESEARCH_BASE_URL=https://open.cnkgraph.com
```

重启本地后端后，现有 ReAct Agent 会额外看到五个只读研究工具（先接入第一批中较实用的能力；未做全接口接入）：

- `analyze_ci_meter`：按词牌与当前作品正文（或明确指定的短文本）调用 `POST /api/Tool/AnalyzeCi`，返回钦谱/龙谱匹配体式和错韵摘要。只判断后世词谱的形式校验，不证明宋代实际合乐。
- `search_classical_books`：在古籍库检索短关键词，使用已实测的区分大小写路由 `POST /Api/Book/Find`；只返回最多五条带书卷 ID 的短命中片段，不抓全卷。
- `lookup_ci_tune`：以词牌名或别名检索，唯一匹配时查询词谱详情，返回正体、变格、谱式与简短例词；多义时只返回词牌候选。
- `lookup_rhyme`：按韵书查询韵部目录，传入韵部 ID 后获取该部字表概要，也可以在已知韵部内判断指定单字是否收录。由于原厂的单字综合接口可能返回数 MB，目前**不支持仅凭一个字直接判定完整韵书中的唯一韵部**；需先定位韵部。
- `resolve_entities`：对当前选区或短诗文做候选实体标注，返回人物、地点、词汇等的类型、外部 ID、原文位置和少量属性；外部标注不直接写回主库。

五者仅在开关打开时向模型注册；开关关闭时即使模型构造工具调用也会拒绝。 Agent 在执行模型提出的工具调用前，还会检查**本轮真实注册的工具名**；即使提示词、旧对话或模型自行输出了未开放的名称，也不会进入网络适配器。原有典故、出处、作品检索和词话 RAG 不受影响。古籍 `/Api/Book/Find` 仅在 404 JSON **恰为** `{"Message":"没找到"}` 时按成功零命中处理，其他 HTTP 404 仍为错误。单次请求 12 秒超时、每次响应最多读取 96 KiB；模型与资料来源仍需核验结果。**不支持批量导出与长期缓存**。

入口：`backend/ai/tools.py` 工具声明；`backend/ai/graph.py` 参数校验及回传；`backend/evidence/providers/cnkgraph_research.py` 外部 HTTP。离线回归：`.venv/bin/python -m pytest -q tests/test_cnkgraph_research_tools.py tests/test_agent.py`。2026-10-20 真实模型针对 reader_016、057、077、084 的小规模回归：016/057 改用已开放的 `lookup_reference`；077/084 的明确无命中不再是 404 错误。研究型回答 Prompt 增加「本次检得证据」与「已有知识／待核推断」区分；这只能降低误引风险，不能代替真实答案核查。[PR #358](https://github.com/montricwang/poeticus/pull/358) 提供 100 题题库与校验；真实工具调用和首批 20 题对照见已合并的 [PR #370](https://github.com/montricwang/poeticus/pull/370)，不能把题集当作完整 Tool Trace。具体模型自主工具选择需要统一进行本地真实对话验收。[CNKGraph 普查 PR #353](https://github.com/montricwang/poeticus/pull/353) **已关闭但未合并 main**；其全域探测与离线报告仍是独立研究资产，由 [#346](https://github.com/montricwang/poeticus/issues/346) 跟进。已合并的五项工具接入见 [PR #356](https://github.com/montricwang/poeticus/pull/356)，效果验收归 [#355](https://github.com/montricwang/poeticus/issues/355)。

### DeepSeek Search / Fetch 联网研究（独立付费 API，默认关闭）

Poeticus 仍由当前 `deepseek-flash` 聊天模型自主选择 LangGraph 工具；这里接入的是 **DeepSeek 独立的 Search/Fetch HTTP API**，不是假定 Flash 聊天接口会自动联网。官方说明：[Search & Fetch](https://api-docs.deepseek.com/zh-cn/guides/search/)。2026-10-20 参考价格两项均为每千次有效请求约 **5 元**；按 DeepSeek 的实际账单为准。

使用个人私有 `.env` / **隔离的本地环境**手动开启，公开服务暂保持关闭，避免匿名用户消耗付费配额：

```dotenv
POETICUS_DEEPSEEK_WEB_TOOLS_ENABLED=true
# 可选；不填时复用 LLM_API_KEY（仅当它本身是 DeepSeek API Key）
# DEEPSEEK_WEB_API_KEY=...
```

本轮增加两个工具：

- `web_search`：调用 `POST https://api.deepseek.com/v1/tools/search`，限制关键词 100 字（加站点域名筛选）、请求仅返回最多 5 条公开结果，`need_content=false`；返回标题、URL、时间、摘要和来源等级。不把搜索摘要当成已经查阅过的原典。
- `web_fetch`：调用 `POST https://api.deepseek.com/v1/tools/fetch`，**URL 必须精确匹配同一用户请求中此前成功 `web_search` 返回的 URL**；不接受本地/内网主机、IP 字面量、特殊端口、带账号密码的 URL，不允许任意跳转。只返回最多 3,500 字的 Markdown 节选，正文是**不可信数据**，不能按里面的指令执行任何操作。

模型和联网服务返回的内容受到响应大小与超时限制，失败与正常零命中分开。Search/Fetch 属于独立计费的只读请求，不在服务器中长期缓存网页内容，也不对私人文献批量抓取。识典古籍官方服务协议（https://www.shidianguji.com/protocol ）限制未经书面许可的自动抓取，因此 Search 可以提供其公开结果链接供读者人工打开，但 `web_fetch` 明确不抓取 `shidianguji.com` 及其子域名，获得正式许可前不接内部接口。一次 Search + Fetch 会用完当前单题 **2 次工具调用预算**。原有典故、词学 RAG 和 CNKGraph 功能不变。

实现入口 `backend/research/deepseek_web.py`、`backend/ai/tools.py`、`backend/ai/graph.py`；离线测试 `.venv/bin/python -m pytest -q tests/test_deepseek_web_tools.py`。本地 Search/Fetch 接入 [PR #365](https://github.com/montricwang/poeticus/pull/365) **已合并 main**，实施任务 [#364](https://github.com/montricwang/poeticus/issues/364) 已收口；工具仍默认关闭，真实回答增量、路由与预算评估见 [#153](https://github.com/montricwang/poeticus/issues/153)、[#154](https://github.com/montricwang/poeticus/issues/154)、[#155](https://github.com/montricwang/poeticus/issues/155)。

### 经典字词与公开文献来源（2026-10-20 试验）

利用已存在的 ReAct Tool Calling，新增按需只读、**默认关闭**的三项专用工具。开启个人本地实验环境后，Agent 可自主选用：

```dotenv
POETICUS_CLASSIC_REFERENCE_TOOLS_ENABLED=true
# 站点专项搜索还须配置：
POETICUS_DEEPSEEK_WEB_TOOLS_ENABLED=true
```

- `lookup_moedict`：萌典公开 JSON API，按词检索台湾教育部《重编国语辞典修订本》的读音、词条义项和少量古籍书证，带来源链接；保留原文标记与原有字形，遵守辞典内容 **CC BY-ND 3.0 TW**（平台代码是 CC0，不代表数据也属于 CC0）。仅是候选释义，未替读者选择具体上下文的义项。
- `search_wikisource`：中文维基文库官方 MediaWiki Action API，5 条以内文献页面搜索结果，带 pageid、标题和来源链接。
- `read_wikisource_page`：只允许按**当前这轮**已搜索出的 pageid，通过官方 Action API 读取最多 3500 字 wikitext 与 revision ID/永久链接；不把 wikitext 模板当成内容指令或已校定底本，不自动抓整部古籍。

原有 DeepSeek `web_search` 可选 `source`：`all`（默认）、`zdic`（汉典）、`shidian`（识典，仅搜索与人工跳转）、`ctext`（中国哲学书电子化计划）、`souyun`（搜韵）、`wikimedia`（中文维基文库等 Wikisource）。内部使用 `site:` 限定并再次按实际域名过滤，避免混入假装该网站的搜索结果。因没有可靠的汉典官方 JSON API，本轮**不逆向其内部接口**；该来源的词条通过 Search/Fetch 查找，仍受第三方资料授权约束。识典网页抓取继续由 DeepSeek Web Client 屏蔽，站内内部 API 没有接入。

注意网络调用可能超时、404/403/429，Wikisource 搜索命中不等于历史权威底本，萌典现代辞典不自动给出词中的最佳古义。**真实小样本连通性（10 月 20 日）**：萌典 `將息` 1 次 API 成功、`綢繆` 出现超时；维基文库 Action API 之前已成功检索《人間詞話》并读到带 revision 的页面，本轮 Agent 两次检索均网络超时；DeepSeek 定站搜索已成功返回汉典、CTP、识典的真实域名候选。Agent 实际使用 `lookup_moedict`（首次超时后重试成功）、`web_search`（汉典站内搜索成功），`search_wikisource` 连续两次超时后明确承认未检得结果。维基文库失败时可尝试改用 `web_search(source=wikimedia)`，但这不是官方 API 成功的替代证据。**目前不可声称维基文库链路稳定或新增工具普遍提高回答正确率。**

所有工具有响应字节上限、不保存整站内容、不修改私有语料库。Chat SSE / 正常 Graph 共用相同工具声明；继续沿用单题 **2 次**预算，长链查证仍待专门测量。

实现：`backend/research/classic_references.py`、`backend/research/deepseek_web.py`、`backend/ai/tools.py` 与 `backend/ai/graph.py`。来源调查和异文问题见 #234（汉典）/ #237（识典、CTP、维基文库），最新增量另以 PR 单独记录。自动测试：`pytest -q tests/test_classic_reference_tools.py`。

只有 schema、没有作品数据时，目录为空是正常现象。

前端排版与样式施工前，请先读 [前端视觉与排版规范](design/frontend-visual-conventions.md)：该文件区分行为契约、编辑设计、光学校正，并标明参数的权威入口。

## 4. 启动本地开发环境

后端：

```powershell
uvicorn backend.app:app --reload
```

前端：

```powershell
cd frontend
npm run dev
```

Vite 开发代理将前端的 `/api/*` 请求转发到本地 FastAPI。生产环境不使用 Vite dev server，而由 FastAPI 同源提供构建后的 `frontend/dist`。

主要公开接口：

- `GET /health`
- `GET /api/info`
- `GET /api/capabilities`
- `GET /api/poems`
- `GET /api/poems/{UUID}`
- `GET /api/poems/{UUID}/neighbors`
- `GET /api/poems/daily`
- `POST /api/chat`
- `POST /api/chat/stream`
- `POST /api/analyze`

## 5. 自动化测试

```powershell
python -m pytest -q
cd frontend
npm run lint
npm run build
node --experimental-strip-types --test tests/*.test.mjs
```

前端质量检查分为 ESLint、Prettier 和 TypeScript：`npm run lint` 检查潜在代码问题，`npm run format:check` 只核对格式，`npm run typecheck` 使用 `tsc -b` 检查类型。原有 `npm run build` 已包含 TypeScript 类型检查，CI 不再重复执行一次。

```bash
cd frontend
npm run lint
npm run format:check
npm run build
# 本地需要整理格式时才执行（CI 不自动改文件）
npm run format
```

Python 静态类型检查（开发依赖固定 BasedPyright 1.40.2，与 CI 共用根目录 `pyrightconfig.json`）：

```powershell
basedpyright
basedpyright --outputjson > basedpyright-report.json
```

`recommended` 模式包含 Warning；BasedPyright 已作为 PR 门禁通过，并在 Actions 中生成短期 JSON 诊断报告。发现类型问题时按共同根因修复，不以 `Any`、`cast()` 或大面积忽略规则换取绿灯。

CI 使用合成数据和替身依赖，不代表私人 EPUB 或真实生产环境已经被完整验收。涉及部署、SSE、数据库迁移或真实浏览器行为的改动仍需做对应环境检查。

### 错误修复与复发预防（默认执行，不需逐次提醒）

每次测试、Lint、类型检查或 Code Review 发现问题后，先定位是代码缺陷、旧测试失效还是环境限制，**修复根因并复测**；范围扩大时记录到已有或新的 Issue，不为消除红灯盲目改业务行为或调低检查要求。优先用相关自动化检查和能复现故障的回归测试防止重犯。

修复后主动浏览 [代码问题复盘](coding-lessons.md)：若本次有**已证实、易复发且可跨开发轮次复用**的教训，就新增或更新同类条目；否则不记录。每条只写「现象与原因 / 预防方法 / 验证方式」，禁止堆积日志、临时环境故障、未经验证的猜想和重复规则。开始修改相关模块前顺手查阅对应条目；文档不取代测试，不强制每次追加。

## 6. 开发与发布

`main` 是稳定主线。功能和重构通过短期分支、PR、CI 后合并。

当前生产运行在 Railway Web / PostgreSQL，网站使用 `https://poeticus.app`；自建 Poem Retrieval 运行在开发机 WSL，通过 Windows `cloudflared` 命名 Tunnel 向 Railway 提供按需访问。是否可用取决于本地两个进程的状态；运行条件与待验收项见 [deployment.md](deployment.md)。后续计划进入 GitHub Issues 或 [roadmap.md](roadmap.md)。

### Git 协作文字语言（Poeticus）

- **Issue 标题／正文：中文**。
- **PR 标题／说明：中文**，技术标识、代码、路径等可保留原文。
- **Git Commit message：英文**，包括 subject、正文与 Squash and Merge 时 GitHub 提议的最终提交信息；建议遵守已有 Conventional Commit 约定，如 `docs: document hybrid deployment`。
- PR 标题与最终 Squash Commit 标题是不同字段：**不要直接把中文 PR 标题作为合并提交标题**。`.github/workflows/english-commit-subjects.yml` 同时检查 PR 内的提交标题及推送到 `main` 的提交标题（ASCII）；但 `push` 检查发生在提交进入 `main` **之后**，只能发现问题，不能阻止合并。要在写入前阻止违反规则的 Commit，还需要仓库规则（commit-message ruleset／分支保护），或在每次 Squash 合并时手动核对英文标题；PR 标题仍允许中文。

### Commitlint 与本地提交检查

Git Commit 统一采用英文 **Conventional Commits**：`type: subject` 或 `type(scope): subject`（允许 breaking change 的 `!` 标记）。`type` 和 `subject` 必填，**`scope` 可选**；仅在能清楚标识模块时填写，无需为 `docs`、`ci`、`chore` 等类型硬加作用域。例：`ci: update GitHub workflows`、`feat(retrieval): add poem search filters`、`fix(backend): handle missing retrieval token`。允许的类型为 `build`、`chore`、`ci`、`docs`、`feat`、`fix`、`perf`、`refactor`、`revert`、`style`、`test`；标题必须为 ASCII，最长 100 字符，正文及 Footer（如有）也要求 ASCII 英文。PR 标题及说明必须使用中文，允许夹带技术标识；`.github/workflows/pr-language.yml` 在创建、编辑或更新 PR 后检查正文中是否包含中文表述（汉字判定不能严格识别自然语言）。

仓库根目录的 `commitlint.config.mjs` 是唯一规则配置；`.github/workflows/commitlint.yml` 在**所有分支的 Push** 及 PR 创建／更新时执行 Commitlint。现有 `english-commit-subjects.yml` 暂时保留，独立检查标题 ASCII。Push 检查属于**事后审计**：发现不合规 Commit 会报告失败，但不会撤销已经推送的 Commit。要强制禁止不合格 PR 合并，仓库管理员还需在 GitHub 的 **Settings → Rules → Rulesets** 对 `main` 配置 `Require status checks to pass` 并将 `commitlint` 设为必需检查（检查名称以 Actions 页面实际 Job 为准）；若要阻止绕过 PR 直接写入 `main`，还需要启用 `Require a pull request before merging`。这些管理员设置不能仅通过提交仓库文件实现；在 GitHub 上真正创建并启用规则前，不能视为合并门禁已生效。还应将 `pr-language` 设为必需检查。

需要在本地提交时立即拦截，可在仓库根目录执行一次：

```bash
git config --local core.hooksPath .githooks
```

之后每次 `git commit` 会通过 `.githooks/commit-msg` 调用 Commitlint（Node.js / npm 必需；首次运行 `npx` 可能下载依赖）。此设置只作用于当前本地仓库，不会自动影响其他克隆。需要关闭时执行 `git config --local --unset core.hooksPath`。本地 Hook 不能代替 GitHub PR 检查；Squash Merge 时仍需确保最终 Commit message 为英文格式。

**Squash 合并须显式设置英文 `type: subject` 或 `type(scope): subject`**，不能让 GitHub 自动把中文 PR 标题变成合并提交信息。例如：`gh pr merge <PR编号> --squash --subject "feat(retrieval): improve poem search" --body "Improve search scoring and tests."`。AI 调用 GitHub API 合并时也必须显式传入英文 `commit_title` 和 `commit_message`。只有 GitHub Ruleset 的 commit metadata 限制能在合并前约束最终提交标题；仅凭 PR 检查不能保证 Squash 时不会填错。

这项约定的跨项目来源是 [《教学与开发协作手册》Git 协作章节](https://github.com/montricwang/chatgpt-vault/blob/main/GPT%20%E7%BA%A6%E6%9D%9F/%E6%95%99%E5%AD%A6%E4%B8%8E%E5%BC%80%E5%8F%91%E5%8D%8F%E4%BD%9C%E6%89%8B%E5%86%8C.md)，项目执行入口以本节为准；无需让其他项目继承 Poeticus 的特例。

## 7. 工程决策的记录边界

重要、长期影响系统边界或数据语义的技术取舍记录到 [ADR](adr/README.md)，包括 Context、Alternatives、Evidence、Origin、Confidence、Consequences 与 Revisit when。普通参数的当前值以代码和相关架构说明为准，尚未确认的工作进入 GitHub Issues。

不要再并行维护 Decision Register；2026-10-07/08 的旧决策快照已在 Git 历史保存，长期结论已迁移到 ADR。完整职责见 [文档导航](README.md)。

## 8. Poem Retrieval 开发环境

完整本地 Serving Artifact 的默认位置为 `../poeticus-data/retrieval/`，模型在 `../poeticus-data/models/`；仅用于构建的 Work/Chunk JSONL 在 `retrieval/corpus/`，不需要复制到生产 Serving Bundle。

需要运行 Retrieval 工具时，再安装额外依赖：

```powershell
python -m pip install -r requirements-retrieval.txt
```

本地 Retrieval Serving 包含：

- Qwen query encoder；
- sentence / clause FAISS；
- sentence character 2-3 gram BM25；
- compact SQLite metadata；
- deterministic Query Plan；
- Work-level RRF；
- Candidate Eligibility；
- **可选 Work Composition Filter**：通过已验证的 Werneror 合集↔独立诗篇关系表压制重复命中；只有指定 `--composition-db` 才启用。

完整架构见 [Poem Retrieval 架构](architecture/text-retrieval.md)。

### 本地 Serving 资产定位与工具边界

本地的三个命令使用相同的路径契约，但工作职责不同：

- `python -m scripts.retrieval.inspect_serving_bundle`：只检查现有 Serving Bundle 的路径和大小，不启动 HTTP 进程；
- `python -m scripts.retrieval.run_serving`：加载现有模型、FAISS、BM25 和 Metadata，启动本地 HTTP 服务；
- `python -m scripts.retrieval.benchmark_serving`：按评测 Case 检查常驻 Runtime 的资源和检索延迟。

这些入口**共同导入** `backend/retrieval/poem/serving_paths.py::default_paths`，由该函数从 sentence Embedding Manifest 的模型指纹推导 Serving 资产位置。`backend/data_paths.py` 只定义整个私有数据工作区的根目录；`serving_paths.py` 则定义本套 Retrieval 运行资产的具体布局。检查或评测工具不依赖 `run_serving.py`，以免把启动 Uvicorn 的入口误当公共底座。

Manifest 中记录的 Work/Chunk 文件 SHA256 由 `backend/retrieval/poem/artifact_files.py` 统一计算。**路径定位是「去哪里找」，指纹校验是「找到的东西是不是同一套」**；两者不可混为一谈，也不可因为只是重构而删除指纹校验。轻量合成回归可以运行：

```powershell
python -m pytest tests/retrieval/test_serving_paths.py tests/retrieval/test_metadata_store.py -q
```

这不代替已有全量 Artifact、真实 FAISS 模型及 Agent Canary 验收。

本地只做 Web / Agent 开发时，可以不配置 Retrieval URL；此时 `search_predecessor_texts` 不注册给 Agent。

## 9. Retrieval 部署与本地验证

原腾讯云 Retrieval 节点已销毁，旧 IP 与 SSH 私钥不再作为有效生产部署入口。历史 `scripts/retrieval/deploy_vps.sh` 仅保留作参考，不应再对旧服务器执行。

本地 WSL 使用现存 `poeticus-data/` 资产，检查并启动：

```bash
python -m scripts.retrieval.inspect_serving_bundle
python -m scripts.retrieval.run_serving --device cpu \
  --composition-db ../poeticus-data/retrieval/relationships/v3/work_compositions.sqlite3
```

`--composition-db` 对应的只读 SQLite 快照及 manifest 属于**私人运行资产**，与 `serving/` 的 Metadata SQLite 是两份不同数据；不会自动创建 PostgreSQL 表。遗漏该参数时服务可正常启动，但组诗去重不会启用。2026-10-14 已在带该参数的真实 WSL Runtime 与正式 `poeticus.app` Agent 页面验收陆游→杜甫检索；操作和退化检查见 [部署文档](deployment.md)。

服务默认监听 WSL 内 `127.0.0.1:8787`。本地开发 Web／Agent 只需要前端和后端，`POETICUS_RETRIEVAL_URL` 留空则不注册自建检索工具；在本地独立调试 Retrieval 时，只需启动 WSL Serving，不必开启公网 Tunnel。

当需要让**线上 Railway Agent** 使用本地 Retrieval 时，另须保持 WSL Serving 和 Windows `cloudflared` 命名 Tunnel 连接器同时运行；无需额外启动本地前端、Web 后端，也不需要把 LangSmith 当成本地服务。Tunnel Token 只供 `cloudflared` 使用，独立于 WSL／Railway 一致设置的 Retrieval Bearer Token。不要把任一 Token 提交到仓库。

| 场景 | 需要启动的本地进程 |
| --- | --- |
| 本地 UI／API 开发 | Vite 前端、FastAPI 后端（及所需的本地数据库） |
| 单独调试 Retrieval | WSL Retrieval Serving |
| 公网演示使用本地检索 | WSL Retrieval Serving、Windows cloudflared |

当前公网域名及启动／恢复、在线验证方式见 [生产部署](deployment.md) 和 [#180](https://github.com/montricwang/poeticus/issues/180)。

## 10. 文档落盘规则

完成一个明显工程阶段后，按 [文档导航](README.md) 更新唯一权威位置：

- `docs/devlog/`：当天发生了什么；
- `docs/architecture/`：系统当前结构；
- `docs/adr/`：长期技术决策的背景、证据、Origin、代价和复审条件；
- GitHub Issues：仍需继续处理的任务；
- `docs/releases/`：版本对外说明；
- `docs/data-management.md`：`poeticus-data/` 私有资产布局和恢复规则。

### GitHub Issue 的生命周期与层级

- **先查再建**：遇到新想法，先搜索开放／已关闭的 Issue、PR 和现行设计。目标与验收相同就修改旧 Issue；旧任务被新方案替代时，提取有用约束、写明去向，再关闭旧单。不要因一次讨论或一个新术语就机械新建 Issue。
- **分清三种关系**：父 Issue 负责较大目标；原生 **Sub-issue** 负责可以独立实施、Review 或验收的任务；正文 `- [ ]` Checklist 只记录本任务内部的检查步骤。仅在确有执行先后阻塞时添加 Dependency，不把普通「相关」误标为「依赖」。子 Issue 的完成进度由 GitHub 状态计算，Markdown 链接不能冒充原生父子关系。
- **开放 Issue 保持可执行**：标题和正文开头说明**当前目标、最小下一步、验收标准**，过时的设计与实验过程可作为历史保留。长期架构事实进入代码、ADR 或架构文档，不靠永不关闭的巨型讨论 Issue 维持。
- **合并与关闭前再核对**：有 PR 的任务引用 PR、测试或真实交互验收证据。关闭前逐项处理尚未打勾的 Checklist：已做的据证据勾选；取消的写明 `out of scope`／`not planned`；仍需做的迁移到合适的开放 Issue 并留链接。**不能因为 CI 通过就假定真实 UI 已验收，也不能因为已关闭就把所有历史 `[ ]` 改成 `[x]`。**
- **父任务不是永久目录**：Roadmap/文档持续保存「阅读、语料、Critic」等长期领域；父 Issue 只承担可结束的阶段目标。收尾时先把稳定结论迁移到现有权威文档，再清理 Issue 的过时方案；已完成的子任务立即打钩/关闭，验收完成就检查是否连父任务一同关闭。不要让历史研究提案靠长期 Open 状态充当知识库。
- **结束后的清理**：对过期部署、重复提案和已被实施的旧实验选择合适关闭原因，正文保留简短结论及新入口；无明确近期实施条件的灵感可以折叠进相关 Issue 的「未来复查」而非永远保持开放。清理不是追求最低 Issue 数量：真正独立的缺陷和实验应继续单独跟踪。

AI 协作、教学节奏和阶段复盘方式统一维护在 [Vault《教学与开发协作手册》](https://github.com/montricwang/chatgpt-vault/blob/main/GPT%20%E7%BA%A6%E6%9D%9F/%E6%95%99%E5%AD%A6%E4%B8%8E%E5%BC%80%E5%8F%91%E5%8D%8F%E4%BD%9C%E6%89%8B%E5%86%8C.md)。

## Clerk 邮箱登录与用户身份（#349，首轮）

本阶段以 Clerk React 登录入口和 FastAPI 会话令牌校验建立可信身份，再用本地 PostgreSQL 的 `app_users` 表保存稳定的 Poeticus 内部 UUID。不迁移浏览器历史，也不修改匿名阅读与聊天接口。

### 1. 开发环境密钥

在 Clerk Dashboard 的 **API Keys** 找到当前**开发实例**的 Publishable Key 和 Secret Key。

前端工作树 `frontend/.env.local`（git 已忽略）：

```dotenv
VITE_CLERK_PUBLISHABLE_KEY=pk_test_从控制台复制
```

Poeticus 后端工作树的 `.env`（git 已忽略）：

```dotenv
CLERK_SECRET_KEY=sk_test_从控制台复制
CLERK_AUTHORIZED_PARTIES=http://localhost:5174,http://127.0.0.1:5174
```

`CLERK_AUTHORIZED_PARTIES` 必须写**真实访问前端的完整 Origin**（协议、主机、端口），局域网 IP 或另一个 Vite 端口要相应补充，正式部署只允许实际线上 Origin。不配置该白名单时后端拒绝验证，不会自动信任任意客户端。不要把 `sk_test_`、`sk_live_` 放到 `VITE_*`，也不要发送给聊天助手。

可选 `CLERK_JWT_KEY` 为 Clerk API Keys 页面展示的 PEM 公钥，将多行转换为转义 `\\n` 后写入后端 `.env`，可实现无需联网获取 JWKS 的签名检查；开发初期省略即可，由官方 SDK 获取并缓存公钥。

请按 Clerk Dashboard 中已选择的邮箱验证码或邮箱密码方式完成注册；客户端直接使用 Clerk 表单，不实现密码保存或验证码发送逻辑。

### 2. 安装与运行

```bash
# 独立工作树试运行，不停止原本运行在 8000/5173 的服务
cd ~/projects/poeticus-auth
~/projects/poeticus/.venv/bin/python -m pip install -r requirements-auth.txt
cd frontend && npm ci && cd ..

# 首次创建 app_users 需执行迁移；同一命令重复执行会跳过已应用版本。
# 若本地迁移尚停留在 0003，将同时补上既有 0004/0005 额度表。
~/projects/poeticus/.venv/bin/python -m scripts.corpus.db_import --migrate

# 终端 A：后端使用现有虚拟环境
~/projects/poeticus/.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8011

# 终端 B：在工作树 frontend/ 下运行前端
cd ~/projects/poeticus-auth/frontend
POETICUS_API_PROXY_TARGET=http://127.0.0.1:8011 npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

浏览器访问 `http://localhost:5174`，点击右上角「登录」或「注册」，完成邮箱注册或登录，成功后出现 Clerk 头像，点击头像可以退出。浏览器从 Clerk SDK 获取 session token，放入 `Authorization: Bearer` 请求。

- `GET /api/auth/me`：只验证令牌并返回 `{"clerk_user_id":"user_..."}`，不写数据库。
- `POST /api/auth/session`：前端登录后自动调用，验证同一个令牌，再将 Clerk ID 登记到 `app_users`。返回 `{"clerk_user_id":"user_...","user_id":"UUID"}`。重复调用保留同一个 `user_id`，未知/无效令牌不得触发创建。
- 未配置后端密钥或数据库返回 503，未登录/令牌无效返回 401，页面会显示「身份未验证」。此前启动的 8011 进程没有 `--reload`，改代码后须先停止该进程并重新启动，再刷新浏览器。

`app_users` 仅保存本地 UUID、Clerk 账号 ID 与创建时间；没有保存邮箱、密码或令牌。本地数据库已于 2026-10-23 应用 `0004`—`0006` 迁移，真实 SQL 交易内验证了账号重复登记的稳定性与隔离性（测试写入已回滚）。其他数据库环境（如 Railway）必须单独迁移，不能认为本地建表等于线上建表。

只要未配置前端 Publishable Key，Clerk 控件完全不会显示，原有界面不变。后端始终不接收/信任任意 `user_id` JSON 或自定义 Header。**本轮只完成身份映射**；私人会话的拥有权查询、消息存档、Mem0 写入许可仍需各自按 #40/#45 接入。

本地 `poeticus-auth/.env` 可以做成指向 `poeticus/.env` 的符号链接（本轮已在开发机创建）；它和 `frontend/.env.local` 均受 Git 忽略。切到正式端口或公网域名时，需要相应更新 `CLERK_AUTHORIZED_PARTIES`，以及 Clerk 的生产实例凭据。
