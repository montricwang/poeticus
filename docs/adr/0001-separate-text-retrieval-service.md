# ADR-0001：将 Text Retrieval 作为独立生产服务部署

- **Status:** Accepted
- **Date:** 2026-10-08
- **Scope:** Production architecture
- **Related:** #145、#160、#164、PR #146、#162、#165

## Context

Poeticus 的前代文本检索已经形成完整运行期依赖：

- Qwen3-Embedding-0.6B query encoder；
- sentence FAISS；
- clause FAISS；
- sentence BM25；
- compact SQLite metadata；
- Query Plan、RRF、Candidate Eligibility。

当前 Serving Bundle 约 8.02 GiB。2C8G Linux 上：

- ready RSS 约 4.4 GiB；
- benchmark 后约 5.3 GiB；
- 5 并发约 1.78 req/s；
- 冷启动约 18–35 s。

Railway 的 `poeticus-web` 同时承担 FastAPI、Agent、静态前端和公开作品 API。把 Retrieval 全部塞入同一进程会显著增加常驻内存、启动时间和故障影响范围。

## Decision

Text Retrieval 作为独立生产服务运行在腾讯云上海 Linux VPS。

当前调用链：

```text
Browser
   ↓ HTTPS
Railway poeticus-web
   ↓ HTTPS + Bearer token
Tencent Cloud Nginx :443
   ↓ HTTP localhost
127.0.0.1:8787 Text Retrieval Service
```

Retrieval 节点：

- Ubuntu 24.04；
- 2 vCPU / 8 GiB RAM；
- CPU only；
- single worker；
- systemd 管理；
- Retrieval 只监听 localhost；
- Nginx 负责公网 HTTPS；
- Security Group 不开放 8787；
- token 保存在 root-only environment file。

Railway PostgreSQL 继续留在 Railway，不迁入 Retrieval VPS。

## Why this fits the current system

### 资源边界清楚

Web / Agent 的资源模型较轻，Retrieval 需要常驻模型与多个索引。拆开后可以独立调整 CPU、RAM、启动方式和部署节奏。

### Artifact 可以独立演进

原始 Embedding、FAISS Index、BM25 和 metadata 都有自己的构建生命周期。Retrieval 服务可以更新 Index，而 Web API contract 保持稳定。

### 故障定位更直接

当前可以逐层判断：

```text
Railway Agent
→ HTTPS
→ Nginx
→ localhost:8787
→ Retrieval runtime
→ Artifact
```

一次 502、timeout、OOM 或 ranking regression 可以先确定属于哪一层。

### 2C8G 已经有真实数据

当前节点规格来自实际 benchmark。Linux benchmark 和线上 E2E 已经证明它能承载现阶段低流量服务。

## Consequences

### Positive

- Railway Web 保持轻量；
- Retrieval 可独立扩 CPU / RAM；
- FAISS / BM25 / model 重启不会直接改变 PostgreSQL；
- Retrieval Tool 可在 URL 未配置时继续隐藏；
- 服务间 contract 已有独立 HTTP client / server integration test；
- 后续可替换 Retrieval 主机或索引实现，而不改 Agent Tool 语义。

### Costs

- 多一个生产节点；
- 多一层网络；
- 需要维护 TLS、systemd、Nginx、Security Group；
- Web 与 Retrieval 可能出现跨区域延迟；
- 代码和 Artifact 的发布需要单独运维；
- Retrieval 冷启动期间 Nginx 会短暂看到 upstream unavailable。

## Main alternatives considered

### 把 FAISS / Qwen 直接放进 Railway Web

当前约 4.4–5.3 GiB RSS 与 8.02 GiB Artifact 会明显改变 Web 服务的资源模型，也会放大每次 Web deploy 的启动成本。

### 直接把 PostgreSQL 扩成 pgvector

现有生产 PostgreSQL 主要保存公开阅读数据。Dense Artifact 的体积、query encoder、FAISS 压缩实验都说明 Retrieval 需要独立做资源评估。当前没有理由为了复用 PostgreSQL 而把向量 Serving 与阅读数据库绑定。

### 第一台就购买更大的 16 GiB / 8 vCPU 节点

Linux Spike 已证明 2C8G 能运行完整服务。容量升级继续以真实 p95、吞吐、swap 和 RSS 决定。

## Operational rule

部署成功需要同时满足：

1. systemd process active；
2. `127.0.0.1:8787` 已监听；
3. localhost `/health` 返回 200；
4. Nginx HTTPS `/health` 返回 200；
5. 真实 Agent E2E 能获得 Retrieval candidate。

固定等待秒数不能代替 readiness check。

## Revisit when

- 真实流量持续超过当前 2C8G CPU 能力；
- 跨境网络成为主要 latency / failure 来源；
- Retrieval footprint 大幅下降；
- 引入 GPU；
- 需要多实例高可用；
- 进入私网互联 / mTLS；
- PostgreSQL / Retrieval 的数据边界发生明显变化。

更细的证据等级、working defaults 与 open questions 见 [2026-10-08 Decision Register](../decisions/2026-10-08-production-retrieval-and-deployment.md)。
