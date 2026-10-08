# Retrieval Linux Deployment Spike

> **历史实验 Runbook，已完成（2026-10-08）**。以下步骤、候选规格与“待决定”均记录当时的执行顺序，**不是当前生产待办**。该 Spike 已验证腾讯云上海 2C8G，并已用于 v0.3.0 生产；现行操作请以 [生产部署](../deployment.md) 为准。

目标是从一台 2核8G Linux VPS 开始，验证 Retrieval Serving 的最低可行资源规格。

## 1. 当时的第一候选

当时第一候选：

```text
腾讯云 CVM
Region: 上海
Class: 标准型
vCPU: 2
RAM: 8 GiB
System Disk: 约 50–60 GiB
Billing: 按量计费
Public Network: 按流量计费
```

选择它用于当时的 Spike；此时生产规格尚未锁定。最终决定见第 11 节。

## 2. 为什么先测这台

当时的 Windows 本机 Retrieval Serving：

```text
steady RSS       ≈ 5.27 GiB
serving artifacts ≈ 8.02 GiB
CPU only
single worker
```

因此第一轮先故意用更紧的 8 GiB / 约 50–60 GiB 系统盘验证：

- Linux 实际 RSS；
- shared CPU 对 Qwen / FAISS / BM25 的影响；
- 单请求与 5 并发延迟；
- 是否发生 swap / OOM / page-cache 压力。

## 3. 本地先检查 Serving Bundle

在 Windows Git Bash：

```bash
cd /d/Documents/Code/poeticus
git switch main
git pull

python -m scripts.retrieval.inspect_serving_bundle
```

输出会列出服务器真正需要的 runtime artifacts。

应包含：

```text
sentence embedding manifest.json
clause embedding manifest.json
sentence FAISS
clause FAISS
sentence BM25
metadata v2 SQLite
metadata sidecar manifest
Qwen model
```

明确**不包含**：

- raw sentence embeddings；
- raw clause embeddings；
- Corpus Work / Chunk JSONL；
- Eval 报告。

Embedding 目录在服务器上仍要保留目录结构，但只需要其中的 `manifest.json`。

## 4. 创建临时 Linux 主机

腾讯云控制台建议：

- 地域：上海；
- Ubuntu 24.04 LTS；
- 2 核 8 GiB 标准型；
- 按量计费；
- 系统盘约 50–60 GiB；
- 公网按流量计费，带宽峰值约 100 Mbps；
- 只配置 SSH；
- 暂时不要开放 Retrieval HTTP 端口；
- 不部署 PostgreSQL；
- 不部署 Web；
- 不装 Docker / Kubernetes。

第一阶段 benchmark 直接在主机内部实例化 Retrieval runtime，不需要公网 HTTP 服务。

## 5. 基础环境

服务器：

```bash
apt update
apt install -y git python3 python3-venv python3-pip

mkdir -p /opt/poeticus
mkdir -p /opt/poeticus-data/output/retrieval
mkdir -p /opt/poeticus-data/models

git clone https://github.com/montricwang/poeticus.git /opt/poeticus
cd /opt/poeticus

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-retrieval.txt
```

## 6. Artifact 目标布局

服务器最终需要：

```text
/opt/poeticus-data/
├─ models/
│  └─ Qwen3-Embedding-0.6B-<fingerprint>/
└─ output/retrieval/
   ├─ embeddings/
   │  ├─ qwen3_0.6b_sentence_1024/
   │  │  └─ manifest.json
   │  └─ qwen3_0.6b_clause_1024/
   │     └─ manifest.json
   ├─ faiss/
   │  ├─ qwen3_0.6b_sentence_1024_ivfpq_nlist512_m256_b8/
   │  └─ qwen3_0.6b_clause_1024_ivfpq_nlist512_m256_b8/
   ├─ lexical/
   │  └─ bm25_sentence_2_3/
   └─ serving/
      ├─ retrieval_metadata.sqlite3
      └─ retrieval_metadata.manifest.json
```

不要把完整 `embeddings/` 分片目录整体复制上去。

## 7. 第一轮 Linux Benchmark

Artifact 到位后：

```bash
cd /opt/poeticus
source .venv/bin/activate

python -m scripts.retrieval.benchmark_serving \
  --data-root /opt/poeticus-data/output/retrieval \
  --model-root /opt/poeticus-data/models \
  --runs 5 \
  --concurrency 5
```

当前 benchmark 会记录：

- OS / Python；
- CPU 型号；
- physical / logical CPU；
- RAM；
- swap；
- disk total / free；
- 各阶段 RSS；
- startup；
- Artifact 磁盘；
- 三个真实 Case；
- 5-request concurrency。

## 8. Uncached Probe

随后：

```bash
python -m scripts.retrieval.probe_serving \
  --data-root /opt/poeticus-data/output/retrieval \
  --model-root /opt/poeticus-data/models
```

它负责区分 query-vector cache 后的 warm latency 与真实新 Query。

## 9. 当时在 Spike 阶段暂不做的事

第一轮数据出来前：

- 不增加 worker；
- 不上 GPU；
- 不开 swap 来“修”内存问题；
- 不调 FAISS 参数；
- 不改 Query Plan；
- 不部署 PostgreSQL；
- 不开放 8787 到公网；
- 不把 Spike 机器直接当 production。

## 10. 当时约定验收后决定

当时约定数据出来后只回答：

```text
8 GiB RAM 是否真的够？
2 vCPU 是否足够？
单 worker 是否足够？
腾讯云上海是否值得成为生产节点？
```

如果 8 GiB 内存够但 2 vCPU 太慢，先升级到 4核8G；只有出现 OOM、持续 swap 或明显 page-cache 压力，才升到 16 GiB。跨境调用问题另行比较腾讯云香港或海外节点。


## 11. Spike 实测结果与生产结论（已完成）

最终实际使用腾讯云上海 2C8G：

- Ubuntu 24.04；
- CPU only；
- single worker；
- 50 GiB 系统盘；
- Serving Artifact 约 8.02 GiB。

Linux benchmark：

```text
ready RSS          ≈ 4.4 GiB
post benchmark RSS ≈ 5.3 GiB
swap used          ≈ 6 MiB
startup cold       ≈ 34.9 s
5-concurrency      ≈ 1.78 req/s
```

结论：

- 8 GiB RAM 能承载当前 full Corpus single worker；
- 当前资源限制更偏向 CPU / concurrency；
- 没有理由因为“看起来更稳”直接升级 16 GiB；
- 2C8G 后来继续承担第一版生产 Retrieval。

后续部署又观察到 Linux page cache 影响：一次 systemd restart 的 startup total 约 18.25 s，明显快于首次冷启动。

Spike 完成后，服务通过 Nginx HTTPS + Bearer token 接入 Railway Agent；陆游 → 杜甫 long-tail Case 已完成真实线上 E2E。

详细生产结论见：

- [ADR-0001](../adr/0001-separate-text-retrieval-service.md)
- [2026-10-08 Decision Register](../decisions/2026-10-08-production-retrieval-and-deployment.md)
- [2026-10-08 devlog](../devlog/2026-10-08.md)
