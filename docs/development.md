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

CI 使用合成数据和替身依赖，不代表私人 EPUB 或真实生产环境已经被完整验收。涉及部署、SSE、数据库迁移或真实浏览器行为的改动仍需做对应环境检查。

## 6. 开发与发布

`main` 是稳定主线。功能和重构通过短期分支、PR、CI 后合并。

当前生产由 Railway Web / PostgreSQL 与独立 Text Retrieval 节点共同组成；真实配置见 [deployment.md](deployment.md)。具体未来工作进入 GitHub Issues 或 [roadmap.md](roadmap.md)，不要在操作文档里保留已经结束的预览阶段说明。

## 7. 工程决策审计

重要工程取舍除了进入 Issue / PR 外，还应在 [Engineering Decision Register](decisions/README.md) 中记录其证据强度、来源和重新审视条件。

Decision Register 使用四层分类：

1. **Evidence-backed**：已有真实 Case、Benchmark、故障或外部约束支持；
2. **Reasonable but unproven**：理由充分，但还没有足够真实数据证明；
3. **Working default**：为了闭环先选的参数、阈值和实现默认；
4. **Open / unresolved**：已有多个合理方向，当前证据不足。

同时记录 `Origin`：`user-directed` / `AI-proposed` / `joint` / `inherited`。

目的不是给每个小实现写 ADR，而是防止：

- AI 在推进实现时自行补上的默认值被遗忘；
- 临时参数因为存在得够久而被误认为架构原则；
- 后续复盘只看到“最后选了什么”，看不到“当时为什么这样选”；
- 新证据出现后不知道哪些决定应该优先重新打开。

架构文档仍然负责描述**当前真相**；Decision Register 负责描述**当前真相的决策来路与可撤销条件**。


## 8. Text Retrieval 开发环境

完整本地 Serving Artifact 的默认位置为 `../poeticus-data/retrieval/`，模型在 `../poeticus-data/models/`；仅用于构建的 Work/Chunk JSONL 在 `retrieval/corpus/`，不需要复制到生产 Serving Bundle。

需要运行 Retrieval 工具时，再安装额外依赖：

```powershell
python -m pip install -r requirements-retrieval.txt
```

当前生产 Retrieval 包含：

- Qwen query encoder；
- sentence / clause FAISS；
- sentence character 2-3 gram BM25；
- compact SQLite metadata；
- deterministic Query Plan；
- Work-level RRF；
- Candidate Eligibility。

完整架构见 [Text Retrieval 架构](architecture/text-retrieval.md)。

本地只做 Web / Agent 开发时，可以不配置 Retrieval URL；此时 `search_predecessor_texts` 不注册给 Agent。

## 9. Retrieval VPS 更新

当前从开发机主动把 Retrieval 代码推到腾讯云，避免服务器直接访问 GitHub raw 的不稳定链路。

Windows Git Bash：

```bash
bash scripts/retrieval/deploy_vps.sh \
  /c/Users/you/.ssh/tencent.pem \
  ubuntu@43.143.103.147
```

脚本显式使用私钥和 SSH `BatchMode`，不会退回密码认证。它会：

- 上传 Retrieval 代码；
- compileall；
- restart systemd；
- 循环等待 localhost `/health`；
- ready 后检查公网 HTTPS health。

依赖变更仍需单独更新远端 venv。生产资源、Nginx、证书和端口规则见 [deployment.md](deployment.md)。

## 10. 文档落盘规则

完成一个明显工程阶段后，按内容性质分别更新：

- `docs/devlog/`：当天发生了什么；
- `docs/architecture/`：系统当前结构；
- `docs/adr/`：已经接受的长期架构边界；
- `docs/decisions/`：证据强度、Origin、working defaults、open questions；
- GitHub Issues：仍需继续处理的任务；
- `docs/releases/`：版本对外说明。

AI 协作、教学节奏和阶段复盘方式统一维护在 [GPT Finishing School《教学与开发协作手册》](https://github.com/montricwang/gpt-finishing-school/blob/main/审校与工作流/教学与开发协作手册.md)。
