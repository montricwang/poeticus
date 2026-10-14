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
```

默认模型服务地址为 DeepSeek；如需兼容服务可设置 `LLM_BASE_URL`。模型名可通过 `POETICUS_LLM_MODEL` 覆盖，输出预算可通过 `POETICUS_LLM_MAX_OUTPUT_TOKENS` 调整。

不要把密钥、数据库 URL 或私人语料放入前端 `VITE_*` 变量、源码或提交记录。

## 3. 数据库

先创建本地 PostgreSQL 数据库，再运行：

```powershell
python -m scripts.corpus.db_import --check
python -m scripts.corpus.db_import --migrate
python -m scripts.corpus.db_import --import
```

默认私有导入检查点是仓库相邻的 `poeticus-data/reading-corpus/normalized/all_normalized.json`；源 EPUB、glyph maps 与中间快照均不进入公开仓库。默认数据目录根据仓库位置计算，与当前工作目录无关；特殊部署可通过绝对路径环境变量 `POETICUS_DATA_ROOT` 覆盖。目录布局、迁移说明与恢复方法见 [本地数据管理](data-management.md) 和 [作品数据库架构](architecture/corpus-database.md)。

只有 schema、没有作品数据时，目录为空是正常现象。

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

## 6. 开发与发布

`main` 是稳定主线。功能和重构通过短期分支、PR、CI 后合并。

当前生产运行在 Railway Web / PostgreSQL，网站使用 `https://poeticus.app`；自建 Poem Retrieval 运行在开发机 WSL，通过 Windows `cloudflared` 命名 Tunnel 向 Railway 提供按需访问。是否可用取决于本地两个进程的状态；运行条件与待验收项见 [deployment.md](deployment.md)。后续计划进入 GitHub Issues 或 [roadmap.md](roadmap.md)。

### Git 协作文字语言（Poeticus）

- **Issue 标题／正文：中文**。
- **PR 标题／说明：中文**，技术标识、代码、路径等可保留原文。
- **Git Commit message：英文**，包括 subject、正文与 Squash and Merge 时 GitHub 提议的最终提交信息；建议遵守已有 Conventional Commit 约定，如 `docs: document hybrid deployment`。
- PR 标题与最终 Squash Commit 标题是不同字段：**不要直接把中文 PR 标题作为合并提交标题**。`.github/workflows/english-commit-subjects.yml` 同时检查 PR 内的提交标题及推送到 `main` 的提交标题（ASCII）；但 `push` 检查发生在提交进入 `main` **之后**，只能发现问题，不能阻止合并。要在写入前阻止违反规则的 Commit，还需要仓库规则（commit-message ruleset／分支保护），或在每次 Squash 合并时手动核对英文标题；PR 标题仍允许中文。

### Commitlint 与本地提交检查

提交标题采用 Conventional Commits 格式，如 `feat: add poem search filters`、`fix: handle missing retrieval token`。允许的类型为 `build`、`chore`、`ci`、`docs`、`feat`、`fix`、`perf`、`refactor`、`revert`、`style`、`test`；标题必须使用英文 ASCII 字符，长度最多 100 字符。Commit 正文也按约定使用英文；PR 和 Issue 仍使用中文。

仓库根目录的 `commitlint.config.mjs` 是唯一规则配置；`.github/workflows/commitlint.yml` 在 PR 和 `main` 推送后运行 Commitlint。现有 `english-commit-subjects.yml` 暂时保留，独立检查标题 ASCII。GitHub Actions 的 `main` push 检查属于事后审计；若要禁止不合格提交进入主分支，还需在 GitHub Rulesets 中将对应 PR 检查设为必需，并约束直接推送。

需要在本地提交时立即拦截，可在仓库根目录执行一次：

```bash
git config --local core.hooksPath .githooks
```

之后每次 `git commit` 会通过 `.githooks/commit-msg` 调用 Commitlint（Node.js / npm 必需；首次运行 `npx` 可能下载依赖）。此设置只作用于当前本地仓库，不会自动影响其他克隆。需要关闭时执行 `git config --local --unset core.hooksPath`。本地 Hook 不能代替 GitHub PR 检查；Squash Merge 时仍需确保最终 Commit message 为英文格式。

这项约定的跨项目来源是 [《教学与开发协作手册》Git 协作章节](https://github.com/montricwang/gpt-finishing-school/blob/main/审校与工作流/教学与开发协作手册.md)，项目执行入口以本节为准；无需让其他项目继承 Poeticus 的特例。

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
- Candidate Eligibility。

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
python -m scripts.retrieval.run_serving --device cpu
```

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

AI 协作、教学节奏和阶段复盘方式统一维护在 [GPT Finishing School《教学与开发协作手册》](https://github.com/montricwang/gpt-finishing-school/blob/main/审校与工作流/教学与开发协作手册.md)。
