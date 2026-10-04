# Poeticus 首次公网部署（Railway）

> 状态：**已完成 Railway 临时受控预览与合成数据库验证；正式作品库迁移和对外发布尚未完成**。关联 [#76](https://github.com/montricwang/poeticus/issues/76)、[#77](https://github.com/montricwang/poeticus/issues/77)。不能在完成 API 费用保护和公网验收之前宣布公开上线。

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


## 全量迁移本地 3491 首到 Railway（2026-10-04）

**已完成证据**：用户在本地使用 `--check` 对真实 3491 首通过数量、唯一 ID、完整顺序、非空正文、词序格式验证，得到公开阅读列指纹 `fd3e10dc3916f3775a79df13839083817f560fe563da7c03cc483c7c304bce39`；关键词疑似编辑内容计数为 0（不等同逐首文学校勘或版权许可结论）。GitHub Actions 已通过合成测试。**正式云库迁移仍待用户本地执行。**

**为什么另写迁移脚本**：既有 `db_import.py --import` 会新建 UUID、并同时写入私人 `poem_source_texts` 来源证据；这两个行为不适合公开迁移。新脚本 `scripts/corpus/public_corpus_transfer.py` 只读取本地 `poems` 的 12 个明确列，原 UUID、次序、词序与审核状态保留，私人来源表及现代 annotations/commentary 不传输。

### 最短操作：两个 Git Bash 窗口

**窗口 A：** 在 Poeticus 项目目录运行以下命令，并始终保持打开：

```bash
railway connect Postgres --tunnel-only -P 55432
```

前置条件：Railway CLI 已登录并关联 `poeticus` 项目和正确环境，SSH 公钥已配置。如已有正常运行的隧道，**不要重复开启第二个**。

**窗口 B：** 在项目根目录，确认已停止之前仍在运行的逐行版导入（`Ctrl+C`；待进程退出再继续），运行：

```bash
git pull --ff-only
source .venv/Scripts/activate
unset POETICUS_PUBLIC_TARGET_URL
python -m scripts.corpus.public_corpus_transfer --apply --confirm-publish
```

Python 会自行提示粘贴**窗口 A 输出的 `127.0.0.1:55432` PostgreSQL 连接 URL**，无需设置/export Shell 环境变量。按用户操作需求，提示输入会在终端正常回显，因此**勿截图或向聊天粘贴含数据库密码的 URL**。源数据库仍由本地私人 `.env` 里的 `POETICUS_DATABASE_URL` 读取。

新版使用 PostgreSQL `COPY FROM STDIN`，一次流式批量导入 3491 行，不再发送 3491 个独立 INSERT 请求。脚本显示连接状态、每 500 首传输进度、云端 SHA-256 校验和最终事务提交结果。SSH 隧道目标仅允许 `localhost/127.0.0.1:55432`；初次连接 10 秒超时，锁等待最长 15 秒，单条 SQL/COPY 最长 180 秒。

云端迁移前已将 Railway Web 的 `preDeployCommand=[]`、`POETICUS_ENABLE_DEMO_SEED=false`，原 3 首合成作品仅在 ID、来源标记等均精确匹配时才会自动删除。每次迁移都在**同一个云端事务**中进行，校验未通过会回滚；重试时如果云端已等于源库则返回 `already_identical`，不会覆盖未知数据。导入不修改本地数据库，也不生成含古诗词全文的中间公开文件。

**成功输出**：`云端事务完成：replaced_known_demo；作品 3491 首；校验 SHA-256 一致。`（若上次已经成功提交，则可能是 `already_identical`。）

**成功以后**：验证受控在线预览 `GET /api/poems` 的 `total=3491`，抽查搜索/详情、词序/正文，再处理已经进入聊天或终端截图的旧 Railway PostgreSQL 密码的**轮换**，确保应用的内网 DSN 同步生效；在 #77 完成前不得取消只读预览门禁。不要把本地连接 URL、私有数据或完整测试正文提交到公开仓库。


## v0.1.0 匿名 AI 上线门槛（安全 Draft PR #82）

**默认安全状态**：在 Railway 生产 Web 中必须设 `POETICUS_SERVE_FRONTEND=true`，应用会自动添加 `PublicAIGuard`。未设置 `POETICUS_AI_ENABLED=true` 前，所有聊天、SSE、赏析 POST 均为 503，不调用 DeepSeek。现有 `POETICUS_PREVIEW_PASSWORD` 是更外层的只读预览门禁，不可为了测试而直接移除它。

**先迁移 Schema，再开启 AI**：部署新的 Web 代码之前，将 Web 的 Railway `preDeployCommand` 设置为 `python -m scripts.corpus.db_import --migrate`（原脚本可重复执行已有迁移，v0004 仅增加 `ai_daily_quotas` 计数表）。如果 DB 连接/表不可用，AI 请求 503，不能绕过配额直接生成。只读作品 API 不依赖此表。

**关键 Web 环境变量**（显式设置，再验证；无需添加 Redis/新账号）：

| 变量 | 首版参考值 | 作用 |
| --- | --- | --- |
| `POETICUS_AI_ENABLED` | `false`（部署先关闭） | 只有用户确认后改 `true` |
| `POETICUS_AI_PER_IP_PER_MINUTE` | `5` | 同一进程内按 ASGI socket peer 的滑动分钟窗口 |
| `POETICUS_AI_MAX_CONCURRENT` | `2` | 同一进程同时进行的收费请求数，持续占用到 SSE 完成 |
| `POETICUS_AI_DAILY_REQUESTS` | `60` | PostgreSQL 按 UTC 日的持久请求次数上限，跨进程/重启共享 |
| `POETICUS_LLM_MAX_OUTPUT_TOKENS` | `1200` | 每次模型调用的最大输出数，强制限制到 128–2048 内 |
| `LLM_API_KEY` | 服务端私密变量 | 用新的真实 DeepSeek Key 替代临时占位；**不许设置 `VITE_` 变量传前端** |

实际请求消耗一个数据库每日 slot（包含失败/断开的请求），模型最多调用三轮（两个工具调用上限）、每轮至多 1200 输出 Token。配合模型 SDK 30 秒超时和零自动重试，避免意外无限耗费；**请求次数不是人民币硬上限**，还需对 DeepSeek 账户余额/账单启用实际额度控制，特别关注供应商额外输入/缓存等计费口径。

**公网验收**：使用全新浏览器、陌生网络，先确认读作品不受 AI 开关影响；AI 默认 503；开启后按顺序验证一个短问答、引用问题、工具查询、整首赏析、SSE 断开重试、超长请求 413、超额 429/当日配额、模型不可用 502/客户端有友好错误。验收时避免把大量真实用户请求或 Key 写入日志。检查模型回答链接与 Markdown：当前前端用 `react-markdown` 的 `skipHtml`，不启用 `rehype-raw`，远程图片不显示，且外链有 `noopener noreferrer`；新发现的安全问题按 #77 记录，不能只靠静态检查断言无 XSS 风险。

**客户端 IP 的局限**：不信任用户自行提供的 `X-Forwarded-For`，因此只用 ASGI socket peer。Railway 代理环境可能使多个真实读者被识别为一个 peer；上线验收要观察 429 是否误伤，进一步评估可信代理 IP 配置。进程内限流和并发上限只适用于一个 Web 进程；若水平扩容，需改为共享存储/网关限流，不能夸称全局一致。Postgres 每日 quota 本身是跨实例原子保留的。

**凭证安全**：之前 Railway PG 完整 URL 已在对话/截图中暴露，首发前必须通过 Railway Postgres → Config → Connection → Regenerate 完整轮换，随后重新部署依赖服务；不能只改变量或只在 SQL 中 `ALTER USER`。刷新 3491 首目录成功后才能公开访问。

**发布顺序**：#80 数据/部署 → #82 安全合成 CI → Railway 0004 迁移 + 测试开关 → 真正限额的模型调用验收 → #78 README/Release。主仓库与线上运行版本必须一致；Draft PR、旧预览门禁和未通过的安全条目不作为已发布能力。
