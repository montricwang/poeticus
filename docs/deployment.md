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


## 从本地 3491 首读取库迁移到 Railway（2026-10-04 方案，尚未实跑）

**边界**：本地 `poems` 已有稳定 UUID、source_order、校勘状态和正文；本地 `poem_source_texts` 仅为私人来源证据。常规 `db_import.py --import` 会同时写这两张表并生成新 UUID，**不能直接用于云端公开迁移**。新脚本 `scripts/corpus/public_corpus_transfer.py` 只查询 `poems` 中指定的 12 列（ID、来源排序、作品集、作者、词牌、标题、寓声、正文、词序、审核状态、版本等），且只插入云端 `poems`。不查询也不迁入原始 source text、source_locator、inline_notes、lacunae、modern annotations/commentary。云端现有 3 条合成数据只有全部符合已知测试标识时才会在同一个事务内删除；如果目标已有非预期数据，直接拒绝覆盖。

这套迁移**在用户本地运行**。浏览器仍会用临时口令保护，AI 端点仍关闭。无需把商业原书、全量 JSON、连接密码提交到公开 GitHub 或贴到聊天里。

### 1. 本地只读预检（不连接 Railway）

在已有 `POETICUS_DATABASE_URL` 的 Poeticus 项目根目录运行：

```powershell
git fetch origin
git switch chore/public-deployment
git pull --ff-only
python -m scripts.corpus.public_corpus_transfer --check
```

脚本默认要求作品数 **3491**、source_order 连续、UUID/source_record_id 唯一、正文非空、词序合法，报告审核状态计数、词序数、最长正文片段、可能带现代编辑用语的记录序号，以及阅读数据 SHA-256。**报告只有统计和序号，不打印或存储原文**。疑似编辑用语检测只是关键词启发式，不是许可或文学校勘结论；必须结合原始来源及使用权作出发布判断，不能靠“没有 annotations 字段”就自动证明全部文本授权无问题。

### 2. 建立短时、经 Railway 账号认证的 DB 通道

Railway Postgres 当前**无公网 TCP proxy**。用 Railway 官方 CLI 的 SSH 隧道比临时给数据库开放公网端口更合适：

```powershell
npm install --global @railway/cli
railway login
railway link
railway connect Postgres --tunnel-only -P 55432
```

最后一条在**第一个 PowerShell 窗口持续运行**，会打印本机 tunnel 地址、端口、用户、数据库与连接 URL。将这个连接 URL **只保存在第二个 PowerShell 窗口的本地环境变量中**，不要发给 AI、复制到 Issue 或写入公开 .env。Railway CLI 会自动通过 SSH 隧道连接没有 TCP 代理的数据库。关闭第一个窗口即可停止隧道。

第二个 PowerShell（仓库根目录）：

```powershell
# 在自己的终端输入 Railway CLI 刚打印出的本地隧道连接 URL：
$env:POETICUS_PUBLIC_TARGET_URL = Read-Host "Railway tunnel PostgreSQL URL（勿贴到聊天）"
# 同一个 shell 仍会从本地私有 .env 读取 POETICUS_DATABASE_URL
python -m scripts.corpus.public_corpus_transfer --apply --confirm-publish
Remove-Item Env:POETICUS_PUBLIC_TARGET_URL
```

**开跑前的配置检查**：务必先从 Railway `poeticus-web` 移除 `preDeployCommand=python -m scripts.corpus.cloud_smoke_seed --apply` 并禁用 `POETICUS_ENABLE_DEMO_SEED`，否则后续部署可能重新插入 3 首合成作品、或与原书位置冲突。该操作可以在下一轮先由 AI 调整并验证。

### 3. 验收和恢复

导入过程是**单个云端事务**：匹配已知测试行 → 删除 → 直接传输允许公开的 12 列 → 重新读取并校验所有行的 SHA-256 → 提交。不生成全文中间 JSON，也不修改本地库。若失败则回滚；第二次执行如果数据完全一致会打印 `already_identical` 而不是重复插入。如果目标有未知行或现存内容漂移，拒绝覆盖并请人工调查。

用受控 Railway 预览验证 `GET /api/poems?limit=20` 的 `total=3491`、作品搜索、UUID 详情、原文划词与短/长词显示；另检查 `poem_source_texts` 云表依然为空。已知来源字段的语义性误分层（例如原作小序误入正文）继续走 #67 等内容 Bug，不将未校勘作品标为“已校勘”。

**证据等级**：脚本单元/合成测试绿灯不能证明用户本地 3491 行预检已经通过；真实导入和公网阅读验收必须以用户电脑和 Railway 返回的统计为准。
