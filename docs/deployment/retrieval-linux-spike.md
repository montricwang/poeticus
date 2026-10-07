# Retrieval Linux Deployment Spike

> 这是 Issue #160 的临时验证手册，不代表正式生产供应商或长期部署规范。

目标不是立即上线，而是在一台可随时删除的 16 GiB Linux VPS 上复现 Retrieval Serving 的资源与延迟数据。

## 1. 第一候选

当前第一候选：

```text
DigitalOcean
Region: SFO3
Plan: Basic Droplet
RAM: 16 GiB
vCPU: 8 shared
Disk: 320 GiB SSD
```

选择它只用于 Spike。生产供应商仍未锁定。

## 2. 为什么先测这台

当前本机 Retrieval Serving：

```text
steady RSS       ≈ 5.27 GiB
serving artifacts ≈ 8.02 GiB
CPU only
single worker
```

因此 16 GiB / 320 GiB 足够验证：

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

建议：

- Ubuntu 24.04 LTS；
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

## 9. 暂时不要做的事

第一轮数据出来前：

- 不增加 worker；
- 不上 GPU；
- 不开 swap 来“修”内存问题；
- 不调 FAISS 参数；
- 不改 Query Plan；
- 不部署 PostgreSQL；
- 不开放 8787 到公网；
- 不把 Spike 机器直接当 production。

## 10. 验收后再决定

数据出来后只回答：

```text
16 GiB RAM 是否宽裕？
shared CPU 是否足够？
单 worker 是否足够？
SFO3 是否值得成为生产节点？
```

如果 shared CPU 抖动明显，再比较 dedicated CPU 或其他供应商；不要在没有 Linux 数据前继续猜规格。
