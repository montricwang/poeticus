# Poeticus 首次公网部署（Railway）

> 状态：**部署方案草稿，尚未创建或验证真实 Railway 服务**。关联 [#76](https://github.com/montricwang/poeticus/issues/76)、[#77](https://github.com/montricwang/poeticus/issues/77)。不能在完成 API 费用保护和公网验收之前宣布公开上线。

## 目标与服务边界

首版优先使用一个常驻 FastAPI Web Service 同时提供 **Vite 构建产物与后端 API**，搭配 Railway 托管 PostgreSQL；无需分别运营两套 Web 服务或引入 Nginx/Caddy、Docker Compose。普通读者只访问单一 HTTPS 域名，不安装环境、不提供个人模型密钥。

```text
浏览器 HTTPS → Railway Web Service (FastAPI + Vite dist)
                     ├─ / → 前端静态文件
                     ├─ /api/poems* → 只读 PostgreSQL 查询
                     ├─ /api/chat* → Agent + SSE → LLM / 查证工具
                     ├─ /api/analyze → 整首赏析
                     └─ /health → 存活检查
                                  ↘ Railway PostgreSQL
```

**端点命名兼容**：`/api/chat`、`/api/chat/stream`、`/api/analyze` 为公网同源入口；旧 `/chat`、`/chat/stream`、`/analyze` 仍在，以兼容本地开发代理与测试。`/api/poems` 保持不变。前端继续使用相对路径，无需把 API Key 或后端域名写入浏览器文件。

## Railway 设置方案（实际创建前需确认）

Railway 2026 年已弃用新项目使用的 `railway.json` / `railway.toml` **Config as Code**，因此首版**不向仓库添加这种旧配置文件**。先在服务 Dashboard 设置构建、启动和 Healthcheck；若将来需要 IaC，再研究新版 `.railway/railway.ts`。

推荐设置（**尚待真实 Railpack 构建验证**）：

| 设置 | 建议值 | 说明 |
| --- | --- | --- |
| Service Source | GitHub `montricwang/poeticus` 已验收的分支 | 首次试运行可以先以 Draft 分支部署，验收后再改为 `main`；注意每次推送触发构建 |
| Root Directory | 仓库根目录 `/` | 根目录有 Python `requirements.txt`、`api.py` |
| Builder | Railpack | 自动检测 Python；额外安装 Node 以构建 Vite |
| `RAILPACK_PACKAGES` | `node@22` | 让 Python 构建环境也能使用 Node/npm；若检测不支持，以实际日志为准 |
| Build Command | `cd frontend && npm ci && npm run build` | 构建到 `frontend/dist`；Python 依赖由 Railpack 安装 |
| Start Command | `uvicorn api:app --host 0.0.0.0 --port $PORT` | Railway 分配端口，不能用 `--reload` |
| Healthcheck Path | `/health` | 不访问数据库或模型，检查 Web 进程 |
| `POETICUS_SERVE_FRONTEND` | `true` | FastAPI 启用生产前端静态文件；若 `frontend/dist` 不存在则拒绝启动 |
| `POETICUS_VERSION` | `0.1.0-rc`（试运行） | 发布验收后统一为实际版本 |
| `LANGSMITH_TRACING` | `false`（首版默认） | 未完成隐私审核前不上传访问者对话 Trace |

敏感变量只在 Railway 的变量管理中配置，不写在 README、仓库或公开 PR：

- `LLM_API_KEY`：调用模型；后端默认 `LLM_BASE_URL=https://api.deepseek.com`。
- `POETICUS_DATABASE_URL`：数据库 DSN；从 Railway PostgreSQL 内网连接信息引用或安全配置。**不要将内网 DSN 写在浏览器变量、公共文档或日志**。
- 实际使用查证工具所需的私密配置：以代码的配置读取项和部署日志为准，不猜测不存在的 Key 名称。

## 数据准备与隐私边界

- 首版采用 PostgreSQL 云库，执行版本化 SQL migration；生产导入文件通过受控的**本地私有通道**传输，不能上传商业 EPUB、原始抽取 JSON、作者的私人来源证据到公开 GitHub。
- 正式 API 只暴露 `poems` 中阅读需要的字段。检查 `prefaces` 是否全是古代原作小序，避免意外混入现代编者注评。
- 在导入真实作品前先使用**人工合成数据**验证数据库 schema、连接和作品 API；不能把“成功连接空数据库”当作作品库已可用。
- 数据库账号遵循最小权限；Web 进程以只读方式查询。记录备份/恢复路径，避免重建服务后作品 UUID 无故变更。

## 上线前拦截条件（#77）

不要只依据 `/health: 200` 便开放模型：

- 服务端统一限制请求大小、问题和历史长度；
- 匿名用户限流与同时生成上限，校验真实客户端 IP 的信任边界；
- 模型最大输出、工具调用和费用总预算；日志不泄漏 Key/DSN 或私人问题；
- SSE 断流、429/503、数据库断开和安全错误提示的用户体验；
- 用外部网络验证真实流式响应；前端构建与后端启动都成功不代表 Agent 调用成功。

**文档状态**：Railway 部署步骤未在真实账户中执行，命令和环境变量应以当次构建日志核验。没有 Railway URL、域名或生产权限的情况下，不声称已部署。


## 临时只读预览（#76 测试阶段，非正式发布）

为实际用浏览器验证 React → FastAPI → PostgreSQL，同时避免尚未完成 #77 限流时有人调用 LLM，本阶段设置：

- `POETICUS_PREVIEW_PASSWORD`：只存在 Railway 服务端变量中的一次性预览口令，**不写进仓库**；启用后全站除 `/health` 外都会要求 HTTP Basic Auth，用户名默认为 `preview`。
- 通过口令后仅允许 `GET` / `HEAD`，任何 AI 问答、赏析 POST 都返回 503，不执行模型调用。浏览器会弹出标准用户名/密码输入窗口。
- 公开 URL 是可以被互联网访问的，但内容受临时口令保护；这不是公网正式安全方案。不要将预览口令复用于 API Key、GitHub 或其他账号。
- 合成作品来自 `scripts/corpus/cloud_smoke_seed.py`，不包含商业 EPUB、私人来源证据或真实已校勘语料。
- 验收完成后应更换/停用口令，并在 #77 的限流、成本熔断和错误隔离通过后，才撤掉只读门禁。正式版本要移除云端临时 `preDeployCommand` 和 `POETICUS_ENABLE_DEMO_SEED`，改为经过审核的真实数据发布方式。

验证项目最小路径：匿名请求主页应返回 401（提示登录）；正确凭证访问主页和 `GET /api/poems` 获得页面与 3 首标有「测试」的作品；`GET /api/poems/{UUID}` 返回片段；任意 `POST /api/chat/stream` 返回 503；`GET /health` 不需要登录返回 200。请勿把这里的合成测试截图当作正式作品库。
