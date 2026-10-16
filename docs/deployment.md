# Poeticus｜当前生产部署

本文记录截至 2026-10-16 的生产部署、已验证的 Retrieval 接入方式和当前可执行的运维检查。原腾讯云检索节点已销毁；旧节点性能数据保留为历史基线。历史实验见 [开发日志](devlog/)、Release notes 与 [ADR-0001](adr/0001-separate-text-retrieval-service.md)。

## 1. 当前混合部署拓扑

```text
访客浏览器
    │ HTTPS: poeticus.app
    ▼
Cloudflare DNS / HTTPS 入口
    │ 自定义域名转发
    ▼
Railway poeticus-web（FastAPI 同源托管 frontend/dist）
    ├── /api/poems* ──────────────► Railway PostgreSQL
    ├── /api/chat* / Agent
    │         │ HTTPS + Bearer（按需调用检索工具）
    │         ▼
    │    retrieval.poeticus.app（Cloudflare）
    │         │ Cloudflare Tunnel：本地主动建立连接
    │         ▼
    │    Windows cloudflared
    │         │ localhost:8787
    │         ▼
    │    WSL Ubuntu / Retrieval HTTP Serving
    └── /api/analyze
```

Web、Agent 和阅读数据库运行在 Railway；独立的 Text Retrieval 仍运行在开发机 WSL。Cloudflare 同时承担主站域名入口与 Retrieval Tunnel 入口，但二者的 DNS／路由配置和故障边界不同。Tunnel **不是**运行检索模型的服务：Windows `cloudflared` 负责转发，WSL Serving 才执行模型与索引查询；两者必须各自运行。

2026-10-11 命名 Tunnel `poeticus-retrieval` 曾离线（Cloudflare 1033）后恢复，期间出现过 Retrieval 请求失败；这是**历史故障**。**2026-10-14 已重新验收**：带关系表的 WSL Retrieval 四组带鉴权 HTTP 检索成功（200、Top-8 正常），`https://retrieval.poeticus.app/health` 公网健康检查成功，正式网站 `https://poeticus.app` 上陆游《鹧鸪天》问答的 `POST /api/chat/stream` 返回 200，Agent 正确列出杜甫《小寒食舟中作》且不再把重复合集误作另一首陆游作品。该次验收未保存 Railway/Tunnel/WSL 三段关联 Trace。

2026-10-11 更早曾使用临时 Cloudflare Quick Tunnel 完成两次 Railway → WSL 检索（HTTP 200），但实验结束时一度将 Railway URL 留空。这是历史测试，不是当前命名 Tunnel 的验收证据。

架构决策见 [ADR-0001](adr/0001-separate-text-retrieval-service.md)；检索算法见 [Text Retrieval 架构](architecture/text-retrieval.md)。

## 2. Railway Web

| 项目 | 当前值 |
| --- | --- |
| Source | `montricwang/poeticus` / `main` |
| Builder | Railpack |
| Build Command | `cd frontend && npm ci && npm run build` |
| Start Command | `uvicorn backend.app:app --host 0.0.0.0 --port $PORT` |
| Pre-deploy | `python -m scripts.corpus.db_import --migrate` |
| Healthcheck | `/health` |
| Frontend | FastAPI 同源提供 `frontend/dist` |
| Region | SFO |
| Replica | 1，允许 sleep |

主要配置：

- `LLM_API_KEY`
- `POETICUS_DATABASE_URL`
- `POETICUS_RETRIEVAL_URL`
- `POETICUS_RETRIEVAL_TOKEN`
- `POETICUS_AI_IP_HASH_SECRET`
- AI 配额与并发参数
- `POETICUS_VERSION`

浏览器只通过 `/api/capabilities` 获得需要知道的非敏感契约。

## 3. Railway PostgreSQL

生产阅读库公开 3491 首词作。首页每日一词使用 `GET /api/poems/daily`，由服务端按北京时间日期计算稳定序号，查询完整词库并返回当天的作品正文。

这批作品包含宋代以外的作者，因此文档不再把整库统一称为“3491 首宋词”。生产数据库当前仍没有可靠的逐首 dynasty 字段。

私人数据链：

```text
private EPUB + glyph maps
        ↓
all_normalized.json
        ↓
private PostgreSQL
        ↓
scripts/corpus/public_corpus_transfer.py
        ↓
Railway PostgreSQL
```

公开迁移只包含阅读需要的字段，不上传私人源书证据和现代注评。

## 4. Retrieval 节点及运行条件

原腾讯云上海 Ubuntu 24.04 / 2 vCPU / 8 GiB 检索实例已销毁，旧 `/opt/poeticus`、Nginx、systemd、证书和公网 IP 均不再有效。

当前使用 WSL Ubuntu 的 `~/projects/poeticus` 与相邻 `~/projects/poeticus-data` 中的 Qwen、FAISS、BM25、SQLite Artifact，以 CPU 启动 Serving：

```bash
# 在 WSL，先进入 Poeticus 仓库并激活可用的 Python 环境
# 预先在 ~/.config/poeticus/retrieval.env 中保存与 Railway 一致的 Bearer Token
source ~/.config/poeticus/retrieval.env
python -m scripts.retrieval.run_serving --device cpu \
  --composition-db ../poeticus-data/retrieval/relationships/v3/work_compositions.sqlite3
# 另一个 WSL 终端
curl -i http://127.0.0.1:8787/health
```

组诗重复关系表是**独立于 Serving Metadata 的只读 SQLite 快照**：`../poeticus-data/retrieval/relationships/v3/work_compositions.sqlite3`，同目录的 `work_compositions_manifest.json` 记录 Corpus SHA-256 和行数。2026-10-14 的生产进程已通过 `--composition-db` 启用；该参数是**显式开关**，忘记添加也能启动，但**不会执行组诗去重**。来源指纹或行数不一致时启动失败；不要通过删除校验绕过资产版本不匹配。正式数据包含 75,333 条拼接合集、269,556 条成员关系；本地另有 PostgreSQL CSV/DDL 模板，但**没有向 Railway PostgreSQL 建表或导入**。生产阅读数据库 UUID 与检索 Work ID 不是同一身份，勿混用。详情见 [Poem Retrieval 架构](architecture/text-retrieval.md)。

实际 Token 不得写入仓库、截图或公共文档。私有 `retrieval.env` 应位于仓库外，权限设为 `600`，文件内通过 `export POETICUS_RETRIEVAL_TOKEN=...` 提供变量；`source` 只对当前终端及它启动的子进程有效。启动脚本不会自动读取工作目录的 `.env`。**缺失或空白 Token 会在加载模型和索引前拒绝启动**；`create_app()` 也会拒绝空 Token。`/health` 继续公开，`/v1/retrieval/profile` 和 `/v1/retrieval/search` 必须携带正确 Bearer Token。服务默认监听 WSL 内 `127.0.0.1:8787`，不直接暴露公网。当前 Windows 端 `cloudflared` 转发到 `http://localhost:8787`；Windows → WSL 的 localhost 转发已在该开发机验证，换设备需重新检查。

Windows 另行运行 Cloudflare **命名 Tunnel** `poeticus-retrieval` 的连接器。当前采用 Cloudflare 管理界面提供的 **Token 方式**，与依赖 `cert.pem` 的本地管理凭据方式不同；不要把 `cloudflared tunnel run poeticus-retrieval` 当成等价的恢复命令。可在 Cloudflare Zero Trust 的 Tunnel 详情中获取对应连接器的 Windows 启动方式；Token 是另一份凭据，**不同于** `POETICUS_RETRIEVAL_TOKEN`，不放进 Railway 或 Retrieval 进程。当前若在终端前台运行，关闭该终端就可能使 Tunnel 离线；尚未将自动启动列为已完成项。

依赖边界：电脑关机、WSL Serving 停止、`cloudflared` 退出或 Tunnel 离线时，主站和阅读数据库仍可用，但需要自建前代文本检索的 Agent 请求会失败或降级；当前降级体验仍见 [#180](https://github.com/montricwang/poeticus/issues/180)。

## 5. Serving Artifact

已验证的 Serving Bundle：

| Artifact | 大小 |
| --- | ---: |
| sentence FAISS | 1.189 GiB |
| clause FAISS | 2.320 GiB |
| sentence BM25 | 1.557 GiB |
| metadata v2 SQLite | 1.828 GiB |
| Qwen3-Embedding-0.6B | 1.125 GiB |
| 合计 | 约 8.02 GiB |

原始 sentence + clause float16 Embedding 约 27.17 GiB，保留为离线构建资产，不放进生产 Serving 节点。

当前 FAISS IVFPQ：

```text
nlist=512
pq_m=256
pq_bits=8
nprobe=64
```

## 6. 历史 Linux 资源基线

以下数据来自已销毁的腾讯云 2C8G CPU 节点，并非当前 WSL 或未来 VPS 的性能保证：

### Memory

```text
ready RSS          ≈ 4.4 GiB
post benchmark RSS ≈ 5.3 GiB
swap used          ≈ 6 MiB
```

没有观察到持续 swap 或 OOM。

### Startup

首轮冷启动约 34.9 s。后续系统已有文件 page cache 时，一次真实 restart 约 18.25 s。

所以启动耗时要区分：

- 模型加载；
- FAISS 文件读取；
- Linux page cache；
- Query-vector cache。

固定等待 15 秒不足以代表服务 ready。

### Concurrency

5 并发 benchmark：

```text
wall            ≈ 2.80 s
individual p50  ≈ 2.03 s
individual p95  ≈ 2.80 s
throughput      ≈ 1.78 req/s
```

旧节点在该次测试中未出现 OOM；新主机需重新测量启动耗时、内存峰值与延迟。

## 7. 域名、HTTPS 与两种 Token

- **主站**：`poeticus.app` 在 Cloudflare 管理 DNS，经 Railway 的自定义域名配置映射到 `poeticus-web`。Railway 自定义域名要求按平台给出的 CNAME 目标和 `_railway-verify` TXT 记录完成路由与所有权验证；不要把 Railway 默认公共网址直接当作其要求的 CNAME 目标。2026-10-11 使用 Railway → Cloudflare Domain Connect 授权配置，HTTPS 访问已返回 200。浏览器到 Cloudflare、Cloudflare 到 Railway 是独立的 HTTPS 连接。
- **检索入口**：`retrieval.poeticus.app` 是命名 Tunnel `poeticus-retrieval` 的公网 hostname，转发到开发机的 `http://localhost:8787`。它不是 Railway 自定义域名，也不需要把 Retrieval 模型部署到 Cloudflare。
- **Tunnel Token**：提供给 Windows `cloudflared`，用于连接器加入指定的 Cloudflare Tunnel；不要提交、复制到 Railway，或和 API Bearer Token 混用。
- **Retrieval Bearer Token**：环境变量 `POETICUS_RETRIEVAL_TOKEN`，必须在 WSL Retrieval 进程和 Railway Web 侧一致。受保护接口无认证预期为 HTTP 401；`/health` 不能代替认证验证。
- **Railway 服务地址**：`POETICUS_RETRIEVAL_URL=https://retrieval.poeticus.app`（不加接口路径），HTTP 客户端会向 `/v1/retrieval/search` 发送带 Bearer 的 POST。只有变更完成部署后，运行中的 Agent 才按新值工作。URL 若留空则不注册自建检索工具。

Cloudflare Tunnel 让本地连接器**向外主动建立连接**，不用对家庭路由器配置端口映射，也不要开放本地 `8787`。原腾讯云 Nginx／Let's Encrypt IP 证书属于历史部署，不再存在有效的证书续期任务。

**环境变量改名时的部署顺序**：先在 Railway 添加新名称的 URL、Token（保留旧变量），然后部署已读取新名称的 Web 代码；本地 WSL 只有在更新启动脚本并设置 `POETICUS_RETRIEVAL_TOKEN` 后才能安全重启 Retrieval Serving。新配置经过无 Token 返回 401、正常检索返回 200 的验证后，才删除 Railway 的旧变量。域名、HTTP API 路径和 Bearer Token 的值均无需改变。

## 8. Retrieval 代码部署

当前开发机使用 `scripts.retrieval.inspect_serving_bundle` 检查现存 Artifact，再使用 `scripts.retrieval.run_serving` 启动 WSL Serving，不重新生成离线 Embedding。

`scripts/retrieval/deploy_vps.sh` 是原腾讯云节点的 SSH 同步脚本，只同步代码，不负责配置新节点或上传模型索引。**不要再对已销毁的 `43.143.103.147` 执行此脚本。** 未来迁移到 Oracle 或其他 VPS 时应重新确认部署方式、目录、鉴权和资源基线。

## 9. Readiness 与 502

检索节点先加载 Qwen 模型、FAISS、BM25 和 SQLite metadata，HTTP 进程启动不等于模型已 ready。只有本地 `GET /health` 返回 200，才说明 Serving Runtime 准备完毕。

旧 2C8G 节点冷启动曾耗时约 35 秒，不应依赖固定 sleep。新的环境以真实健康检查为准；如果隧道已启动而后端未 ready，网关可能出现连接错误或 502。

## 10. Chronology metadata

公开阅读库当前没有可靠逐首 dynasty。

Agent 调用 Retrieval 时，如果 `current.dynasty=null`：

1. Retrieval 先查 current-work exact alias；
2. 再查 Werneror exact-author dynasty 分布；
3. 唯一最高的已知 label 作为 corpus-compatible chronology label；
4. 并列或未知时保持 unknown。

这个 label 只服务 Retrieval 内部的粗粒度 eligibility。

部署节点实际观察：

```text
温庭筠 → 唐
韦庄   → 唐
冯延巳 → 唐
李璟   → 唐
李煜   → 唐
```

因此它不能承担精细历史断代。南唐人物在 Werneror 中同样可能标成唐。

## 11. 部署后检查

### 网站与 Railway

1. Railway 最新 Deployment 为 SUCCESS，`https://poeticus.app/health` 返回 HTTP 200；
2. 首页、`/api/poems?limit=1`、`/api/poems/daily`、`/api/info` 正常；发布版本时核对 `/api/info` 与目标版本一致；
3. Railway 变量名包含 `POETICUS_RETRIEVAL_URL` 和 `POETICUS_RETRIEVAL_TOKEN`，且已部署预期值；**变量存在不代表可达或认证成功**；
4. 测试真实问答和 SSE，观察工具是否成功返回候选、Agent 是否引用候选，不能只凭首页可访问判断 Retrieval 正常。

### WSL + Tunnel

1. WSL 内按第 4 节使用 `--device cpu --composition-db ../poeticus-data/retrieval/relationships/v3/work_compositions.sqlite3` 启动（并先加载私有 Bearer Token），检查 `http://127.0.0.1:8787/health` 为 200；注意 **health=200 不证明去重表已启用**。
2. 在 Cloudflare Zero Trust 检查 `poeticus-retrieval` 为 `Healthy`，并确认 Windows `cloudflared` 进程持续运行。
3. 从 Windows 或其他网络执行 `curl.exe -i https://retrieval.poeticus.app/v1/retrieval/profile`；**无 Token 时预期 401**，并在 WSL 看到对应 GET。Cloudflare `1033` 通常表示找不到在线 Tunnel；`502` 还需核对本地 Serving。
4. 从正式域名发起一个应触发 `search_predecessor_texts` 的问题，确认 WSL 日志出现 `POST /v1/retrieval/search` 且返回 HTTP 200；Railway 不再有对应工具错误，并检查 Agent 最终回答。这才是命名 Tunnel 的端到端验收。

排障只沿已经失败的环节继续：主站 DNS/HTTPS → Railway → Retrieval 公网入口 → Tunnel → WSL Serving → Bearer/实际 POST。不要把一次性的本地 DNS、TLS 或代理波动固化成通用故障原因；日志和可复现请求优先。

## 12. 当前运维边界

2026-10-14 **已验收当前组诗去重链路**：WSL 进程命令确有 `--composition-db`；本机 8787 端口四组 Bearer 查询均返回 HTTP 200／8 条候选，陆游《鹧鸪天》两句与杜牧《赠别二首》的重复合集被排除，杜甫及晏殊独立作品保留；公网 Tunnel `/health` 返回 200。`https://poeticus.app` 已经实测打开陆游《鹧鸪天》并向 Agent 追问「片片轻鸥落晚沙」，浏览器网络请求 `POST /api/chat/stream` 返回 200，模型突出杜甫《小寒食舟中作》而没有旧的重复作品判断。**这不等于已在 Railway/WSL 日志中为同一请求建立完整关联 Trace**，也不能作为电脑关机后仍在线的保证。

回归检查应使用这一真实 Case：提供陆游完整词文和作者信息、检索「片片轻鸥落晚沙」，返回候选里不得再有 Work `werneror_poetry:宋_4.csv:51342`，但杜甫《小寒食舟中作》要保留；杜牧《赠别二首》和晏殊另一首《破阵子·春景》作为相邻对照。无 `--composition-db` 的旧启动命令会**静默恢复旧的重复候选行为**，因此排障首先核对进程命令，不要仅看健康检查。

`TEXT_RETRIEVAL_TIMEOUT_SECONDS = 15.0` 是 HTTP 客户端各阶段的超时设置，并非整个 Agent 请求的硬截止时间。连接、超时和响应错误会变成工具 `status:error`，目前没有自动熔断；断连后模型能否如实说明未检索仍需真实交互验收，见 [#180](https://github.com/montricwang/poeticus/issues/180)。

旧 2C8G 数据仅作为新实例选型参考。已销毁节点的证书续期 [#167](https://github.com/montricwang/poeticus/issues/167) 不再是当前线上维护任务；完整拼接重复 self-hit 已由 [#151](https://github.com/montricwang/poeticus/issues/151) 修复并在正式页面验收；未确认异文与题名错配仍见 [#173](https://github.com/montricwang/poeticus/issues/173)。

