# Poeticus 开发者指南

本文保留本地运行、数据库准备与测试步骤。Poeticus 面向读者的介绍见 [README](../README.md)；这份指南**不是**普通读者使用在线网站的前置要求。

## 环境要求

- Python（CI 使用 3.12）及 pip。
- Node.js（CI 使用 22）和 npm。
- 本地 PostgreSQL。作品目录与正文不再从前端静态 JSON 加载。
- 开发者自己的模型 API Key，以及有权使用的作品数据。

FastAPI 的实现集中在 `backend/`，`frontend/` 为 Vite/React 项目。根目录的 `api.py` 等文件仅为旧导入路径提供兼容。开发时分别运行前端和后端；**不要将 `vite dev` 或 `uvicorn --reload` 直接暴露为公网生产服务**。

## 1. 安装依赖

在仓库根目录运行：

```powershell
python -m pip install -r requirements-dev.txt
cd frontend
npm ci
cd ..
```

## 2. 配置本地环境

在项目根目录创建私有 `.env` 文件，例如：

```dotenv
LLM_API_KEY=替换为个人密钥
POETICUS_DATABASE_URL=postgresql://用户名:密码@localhost:5432/poeticus
LANGSMITH_TRACING=false
```

默认 LLM 接入 DeepSeek；使用其他兼容地址时可另外配置 `LLM_BASE_URL`。公开仓库通过 `.gitignore` 排除 `.env`，不要将密钥写入源码、前端 `VITE_` 变量或提交记录。可用 `POETICUS_VERSION` 覆盖应用公开版本号（默认 `0.1.0-dev`）。

请先自行创建本地 PostgreSQL 数据库 `poeticus`。建表迁移与导入工具见 [作品数据库架构](architecture/corpus-database.md)。

```powershell
python -m scripts.corpus.db_import --migrate
```

**数据边界**：默认私有导入流程使用本地 `data/output/all_normalized.json`；这个文件及源 EPUB 都不在公开仓库中。`all_normalized.json` 是可重建的数据库导入检查点，不是唯一源数据；完整数据生命周期与备份边界见 [`data/README.md`](../data/README.md)。只有在你自行准备、核对且有权使用的作品数据存在时，才执行：

```powershell
python -m scripts.corpus.db_import --check
python -m scripts.corpus.db_import --import
```

只有数据库表、没有导入作品时，阅读目录会为空；这是数据缺失，不表示前端仍使用旧的静态作品库。生产数据库如何导入可公开字段，另见 [公网部署任务 #76](https://github.com/montricwang/poeticus/issues/76)。

## 3. 启动本地服务

在根目录运行 FastAPI：

```powershell
uvicorn backend.app:app --reload
```

在另一个终端启动 Vite：

```powershell
cd frontend
npm run dev
```

浏览器打开 Vite 输出的地址（通常为 `http://localhost:5173`）。Vite 本地代理把 `/api/poems` 发送给 FastAPI 同名路由，并将其他 `/api/*` 请求去掉前缀后发送给 FastAPI，因此不需要本地手动配置 CORS。**这个代理只在 Vite 开发环境中生效，不是正式部署方案。**

后端接口：

- `GET /health`：廉价的存活检查，不依赖数据库或模型。
- `GET /api/info`：公开的产品名称、版本号与仓库链接。
- `GET /api/poems`、`GET /api/poems/{UUID}`：作品目录、详情。
- `POST /chat`、`POST /chat/stream`、`POST /analyze`：普通问答、SSE 流式问答、整首赏析。
- `GET /docs`：FastAPI 自动生成的开发接口文档；是否开放给公网用户由正式部署配置决定。

## 4. 自动化测试

在根目录运行：

```powershell
python -m pytest -q
cd frontend
npm run lint
npm run build
node --experimental-strip-types --test tests/*.test.mjs
```

测试使用合成样本和替身依赖，不验证作者的私人作品库，也不会直接验证铁路平台等实际公网部署。部署前还需要真实浏览器的搜索、切诗、划词、SSE 与失败恢复验收。

## 5. 开发、合并与公开展示

`main` 是稳定代码主线；任务变更通过短期分支和 Draft PR 验收后合并。公网演示应构建自已验收的稳定代码，而非 Vite 开发服务器或仍在探索中的界面分支。

首次上线暂选 Railway 托管，部署与安全设计由 [#76](https://github.com/montricwang/poeticus/issues/76) 和 [#77](https://github.com/montricwang/poeticus/issues/77) 跟踪；Docker Compose/VPS 学习在 [#79](https://github.com/montricwang/poeticus/issues/79) 中后置安排。
