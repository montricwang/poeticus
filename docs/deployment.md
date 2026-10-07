# Poeticus｜当前生产部署

本文描述 v0.3.0 的生产结构、资源边界和常用运维检查。历史预览环境、首次上线过程和 Retrieval Spike 过程保留在 `docs/devlog/`、Release notes 和 `docs/deployment/retrieval-linux-spike.md`。

## 1. 生产拓扑

```text
Browser
   ↓ HTTPS
Railway poeticus-web
   ├─ FastAPI: backend.app:app
   ├─ frontend/dist
   ├─ /api/poems*
   ├─ /api/chat*
   ├─ /api/analyze
   └─ Agent
        │
        ├────────────→ Railway PostgreSQL
        │
        │ HTTPS + Bearer token
        ▼
Tencent Cloud Shanghai
   Nginx :443
        ↓
   127.0.0.1:8787
   Text Retrieval Service
   ├─ Qwen3-Embedding-0.6B query encoder
   ├─ sentence FAISS
   ├─ clause FAISS
   ├─ sentence BM25
   └─ compact SQLite metadata
```

Web、作品数据库和 Text Retrieval 目前分成三个资源边界：

- Railway Web：页面、API、Agent、SSE；
- Railway PostgreSQL：公开阅读作品；
- 腾讯云 Retrieval：约 85 万首外部 Corpus 的 Hybrid Retrieval。

架构决策见 [ADR-0001](adr/0001-separate-text-retrieval-service.md)。

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
- `POETICUS_TEXT_RETRIEVAL_URL`
- `POETICUS_TEXT_RETRIEVAL_TOKEN`
- `POETICUS_AI_IP_HASH_SECRET`
- AI 配额与并发参数
- `POETICUS_VERSION`

浏览器只通过 `/api/capabilities` 获得需要知道的非敏感契约。

## 3. Railway PostgreSQL

生产阅读库公开 3491 首词作。

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

## 4. Retrieval 节点

当前主机：

```text
Tencent Cloud Shanghai
Ubuntu 24.04
2 vCPU
8 GiB RAM
CPU only
single worker
system disk ≈ 50 GiB
```

运行目录：

```text
/opt/poeticus
/opt/poeticus-data
/etc/poeticus-retrieval.env
```

systemd unit：

```text
poeticus-retrieval.service
```

Retrieval 只监听：

```text
127.0.0.1:8787
```

8787 不进入腾讯云 Security Group 的公网入站规则。

## 5. Serving Artifact

当前线上 Bundle：

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

## 6. Linux 资源基线

2C8G 首轮 benchmark：

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

当前 8 GiB RAM 足够；如果以后需要升级，先看真实 CPU / concurrency 指标。

## 7. HTTPS 与认证

公网入口由 Nginx 提供：

```text
Railway
  ↓ HTTPS + Bearer token
Nginx :443
  ↓
127.0.0.1:8787
```

当前 Security Group：

- SSH：开放给维护入口；
- TCP 80：ACME HTTP-01；
- TCP 443：HTTPS；
- TCP 8787：不开放。

Bearer token 存在：

```text
/etc/poeticus-retrieval.env
```

文件权限 `600`，root-only。

未带正确 token 的受保护 Retrieval endpoint 返回 401。

Let’s Encrypt 当前使用公网 IP 证书。Certbot 已建立自动续期任务，第一次续期与 Nginx reload 验证由 #167 跟踪。

## 8. Retrieval 代码部署

服务器访问 `raw.githubusercontent.com` 曾出现长时间无数据，因此当前维护路径从开发机主动推送。

仓库提供：

```bash
bash scripts/retrieval/deploy_vps.sh <ssh-key> <user@host> [public-url]
```

例如 Windows Git Bash：

```bash
bash scripts/retrieval/deploy_vps.sh \
  /c/Users/you/.ssh/tencent.pem \
  ubuntu@43.143.103.147
```

脚本：

1. 打包 `backend/retrieval`、`scripts/retrieval` 与 Retrieval requirements 文件；
2. 使用指定私钥和 `BatchMode=yes` 连接；
3. 解压到 `/opt/poeticus`；
4. Python compileall；
5. restart systemd；
6. 最长等待 120 秒，循环检查 localhost `/health`；
7. ready 后再检查公网 HTTPS `/health`。

脚本只同步代码。若 `requirements-retrieval.txt` 真正新增依赖，仍应显式更新远端 venv，再 restart。

## 9. Readiness 与 502

一次真实 restart 暴露了很重要的状态差异：

```text
systemd active
→ Python process 已存在

127.0.0.1:8787 LISTEN
→ Uvicorn 已开始监听

localhost /health 200
→ Retrieval runtime ready

public /health 200
→ Nginx → upstream 链路 ready
```

systemd 已 active、模型和 FAISS 仍在加载时，Nginx 可能暂时返回 502。

部署脚本因此等待 localhost health，不再依赖固定 sleep。

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

### Railway Web

1. 最新 deployment 成功；
2. `GET /health` 200；
3. 首页返回 HTML；
4. `GET /api/poems?limit=1` 可读；
5. `/api/info` 版本正确；
6. 涉及聊天时验证 SSE。

### Retrieval

```bash
sudo systemctl status poeticus-retrieval --no-pager
sudo ss -ltnp | grep 8787
curl -i http://127.0.0.1:8787/health
curl -i https://43.143.103.147/health
```

最后再做真实 Agent E2E。健康检查只能证明服务可访问，无法证明 ranking 与 Agent 判断正确。

## 12. 当前运维边界

已经确认：

- 2C8G 能承载当前 full Corpus single worker；
- Web → Retrieval HTTPS 已生产连通；
- Bearer auth 生效；
- 8787 没有公网暴露；
- 陆游 → 杜甫 long-tail E2E 已在线通过。

继续观察：

- #167：证书自动续期；
- #151：duplicate / variant self-hit；
- 跨境网络长期稳定性；
- 真实并发是否需要 4C8G；
- 是否值得建立完整 Retrieval CI/CD。

资源与服务通信的学习复盘见 #166 和 [Finishing School《教学与开发协作手册》](https://github.com/montricwang/gpt-finishing-school/blob/main/%E5%AE%A1%E6%A0%A1%E4%B8%8E%E5%B7%A5%E4%BD%9C%E6%B5%81/%E6%95%99%E5%AD%A6%E4%B8%8E%E5%BC%80%E5%8F%91%E5%8D%8F%E4%BD%9C%E6%89%8B%E5%86%8C.md)。
