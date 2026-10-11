# Poeticus｜当前生产部署

本文记录截至 2026-10-11 的生产部署、已验证的 Retrieval 接入方式和当前可执行的运维检查。原腾讯云检索节点已销毁；旧节点性能数据保留为历史基线。历史实验见 [开发日志](devlog/)、Release notes 与 [ADR-0001](adr/0001-separate-text-retrieval-service.md)。

## 1. 生产拓扑

```text
Browser
   ↓ HTTPS
Railway poeticus-web
   ├─ FastAPI: backend.app:app
   ├─ frontend/dist
   ├─ /api/poems*
   ├─ /api/chat* / Agent
   └─ Railway PostgreSQL
```

生产中的 Web、Agent 和作品数据库运行在 Railway。当前 `POETICUS_TEXT_RETRIEVAL_URL` 为空，Agent 不注册 `search_predecessor_texts`；普通问答和其他 Evidence 工具不依赖自建 Retrieval 节点。

独立 Retrieval 已在开发机 WSL 恢复。2026-10-11 曾通过带 Bearer 认证的 Cloudflare Quick Tunnel，完成 Railway → 本地 Retrieval → Agent 的真实端到端测试（两次检索请求均返回 HTTP 200）。之后将 Railway URL 恢复为空并重新部署。Quick Tunnel 不是常驻生产入口。

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

当前没有持续在线的公网 Retrieval 节点。此前腾讯云上海 Ubuntu 24.04 / 2 vCPU / 8 GiB 的实例已销毁，原 `/opt/poeticus`、`/etc/poeticus-retrieval.env`、Nginx、systemd 和公网 IP 不再有效。

2026-10-11 使用现存模型、FAISS、BM25 与 SQLite Artifact，在 WSL Ubuntu 的 `~/projects/poeticus` 和相邻的 `~/projects/poeticus-data` 目录恢复 CPU Serving：

```bash
python -m scripts.retrieval.run_serving --device cpu
```

默认仅监听 `127.0.0.1:8787`。本地服务与公网隧道需要分别启动；Railway 无法直接访问开发机的 loopback 地址。重新启用公网检索前须验证 Bearer 认证、HTTPS、可达性及断连降级。

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

## 7. HTTPS 与认证

本地 Retrieval 默认监听 loopback HTTP，不对公网开放 `8787`。启动时如设置 `POETICUS_TEXT_RETRIEVAL_TOKEN`，受保护接口将验证 Bearer Token；独立启动脚本不会自动读取工作目录中的 `.env`。

2026-10-11 使用 Cloudflare Quick Tunnel 临时提供 HTTPS 公网入口，验证未携带 Token 时受保护接口返回 401、使用正确 Token 时返回 200，并完成 Agent 真实检索。临时域名与 Tunnel 可用性不保证长期稳定，测试结束后 Railway 已恢复为不依赖该地址。

原腾讯云 Nginx、Let's Encrypt IP 证书与 systemd 的配置属于历史部署，不再存在有效的证书续期任务。

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

### Railway Web

1. 最新 Deployment 为 SUCCESS，且 `GET /health` 返回 200；
2. 首页、`GET /api/poems?limit=1`、`GET /api/info` 正常；
3. 实际询问一个诗词问题，验证 SSE 与最终回答；
4. 未启用自建检索时确认 `POETICUS_TEXT_RETRIEVAL_URL` 为空，Agent 不注册 Corpus 工具。

### 本地 Retrieval（按需启动）

```bash
python -m scripts.retrieval.inspect_serving_bundle
python -m scripts.retrieval.run_serving --device cpu
# 另一个终端：
curl -i http://127.0.0.1:8787/health
```

设置 Token 后，还须验证受保护接口无认证时为 401、有正确认证时为 200，再考虑公网隧道。公网健康检查不能代替真实 Agent 工具调用验收。

## 12. 当前运维边界

已确认：本地 WSL Retrieval 能加载约 8.02 GiB Serving Bundle 并返回真实候选；Cloudflare Tunnel 曾使 Railway Agent 成功调用本地检索，两次 `POST /v1/retrieval/search` 均返回 HTTP 200；实验结束后 Railway URL 恢复为空，Web 不依赖检索节点运行。

`TEXT_RETRIEVAL_TIMEOUT_SECONDS = 15.0` 是 HTTP 客户端各阶段的超时设置，并非整个 Agent 请求的硬截止时间。连接、超时和响应错误会变成工具 `status:error`，目前没有自动熔断；断连后模型能否如实说明未检索仍需真实交互验收，见 [#180](https://github.com/montricwang/poeticus/issues/180)。

旧 2C8G 数据仅作为新实例选型参考。已销毁节点的证书续期 [#167](https://github.com/montricwang/poeticus/issues/167) 不再是当前线上维护任务；重复语料与版本 self-hit 另见 [#151](https://github.com/montricwang/poeticus/issues/151)。

