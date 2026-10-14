# Poem Retrieval 架构基线

> **业务边界（2026-10-13）**：当前实现位于 `backend/retrieval/poem/`，是针对本地诗歌语料的 **Poem Retrieval**：以诗歌作品为候选单位，包含作品自身排除、朝代先后判断和 Work-level RRF。`Text Retrieval` 保留在既有服务类名、HTTP 接口及配置中作为历史名称；未来针对词话、古籍、现代书籍或辞书的通用本地 Text Retrieval 尚未实现，不应直接复用这些诗歌业务规则。

> **当前状态（2026-10-14）**：WSL CPU Serving 经 Cloudflare 命名 Tunnel 为 `poeticus.app` 提供检索。Werneror 拼接关系表已经在 WSL 运行进程中启用，并通过真实检索 API 与正式站点 Agent 问答验收。[PR #286](https://github.com/montricwang/poeticus/pull/286) 已合并，[#151](https://github.com/montricwang/poeticus/issues/151) 已关闭。以下 v0.3.0 性能数字仅作为历史基线；是否在线仍取决于 WSL Serving 与 Windows `cloudflared`。

## 0. v0.3.0 检索基线与当前状态

2026-10-11 在 WSL 恢复模型、索引及 HTTP Serving，并切换到命名 Tunnel。2026-10-14 使用关系表快照 v3 重启后，本地带鉴权检索、命名 Tunnel 公网健康与正式站点 Agent 问答均已验证。**一次验收成功不意味着电脑关机、Tunnel 断开后依然可用**。

### 运行期链路

```text
Agent search_predecessor_texts
        ↓ HTTPS + Bearer
Poem Retrieval Service
        ↓
deterministic Query Plan
        ↓
┌───────────────────────────────┐
│ sentence Dense / clause Dense │
│ sentence char 2-3gram BM25    │
└───────────────────────────────┘
        ↓
Work-level RRF
        ↓
Candidate Eligibility
        ↓
Work Composition Filter（显式启用，按组诗拼接关系去重）
        ↓
Top-K candidates
        ↓
Agent 判断
```

Agent 对“借了谁哪一句／化用了哪段前代文本”优先使用自建 Corpus Tool；检索候选是**可比较的文本证据**，不等于文学上的有意化用已经坐实。

### Werneror 拼接关系去重（PR #286／已完成 #151）

2026-10-14 全量扫描 853,385 条 Work：同作者、同朝代的完整逐字拼接得到 **75,327** 条合集；忽略标点、空白、全半角差异后再新增 **6** 条，共 **75,333 个合集、269,556 条合集成员关系**。另发现 231 条至少包含两首独立作品的非完整拼接候选，其中 146 条正文覆盖率至少 80%，**仅供复核，不入自动过滤表**；一两个字的异文也不凭相似度自动排除。

- 检测：`scripts/corpus/werneror_group_audit.py`、`scan_normalized_compositions.py`；`scan_partial_compositions.py` 只输出待审阅报告。
- 只读关系快照：`../poeticus-data/retrieval/relationships/v3/work_compositions.sqlite3`；同目录有 PostgreSQL 导入用的 `work_compositions.csv` 和校验清单 `work_compositions_manifest.json`。每行记录合集 Work ID、成员 Work ID、序号、原文位置及匹配类型。导出器 `scripts/corpus/export_work_compositions.py` 重新核验整篇拼接；`scripts/corpus/work_compositions_postgres.sql` 仅是**未来检索库**的建表模板，**没有向 Railway PostgreSQL 导入**，也不关联阅读库的 UUID。
- **启用方式**：在 WSL 启动时显式指定 `--composition-db ../poeticus-data/retrieval/relationships/v3/work_compositions.sqlite3`；未指定仍是旧检索行为。启动检查快照对应的 Corpus SHA-256 和关系行数，校验不通过拒绝加载。
- **筛选边界**：原 Eligibility 后，在最多 32 条候选中查询关系，再按原 RRF 顺序补足 Top-K。仅当当前 Work 身份已确认、合集本次命中片段也与当前作品正文重合，或者同次召回合集及成员且证据片段重合时，压制重复合集。**不是全库删除合集 Work，也不是仅凭标题“其一”“几首”删除**；不向 Agent 额外输出“所属组诗”字段。
- **实际验收**：当前 `127.0.0.1:8787` 的带鉴权 HTTP 四组查询全部返回 200 和完整 Top-8：陆游《鹧鸪天·其六》的两句、杜牧《赠别二首》的重复合集不再出现，杜甫《小寒食舟中作》及晏殊另一首《破阵子·春景》被保留。公网 `https://retrieval.poeticus.app/health` 可达；正式 `https://poeticus.app` 的 `POST /api/chat/stream` 返回 200，陆游「片片轻鸥落晚沙」的回答正确突出杜甫，不再误判“陆游在另一首词中重复使用”。未逐请求采集跨 Railway、Tunnel、WSL 的关联 Trace，不将单次成功外推为持续稳定。**原始语料、Embedding、FAISS、BM25 均未改动**。

### Full Corpus

```text
Works            853,385
sentence chunks  4,822,054
clause chunks    9,425,173
```

Embedding：

```text
Qwen/Qwen3-Embedding-0.6B
1024 dimensions
normalized
float16 build artifacts
```

原始 sentence + clause Embedding 合计约 27.17 GiB，继续作为离线构建资产。

### Serving Index

Serving Bundle 使用两套 FAISS IVFPQ：

```text
sentence FAISS   1.189 GiB
clause FAISS     2.320 GiB
total            3.509 GiB
```

当前参数：

```text
nlist=512
pq_m=256
pq_bits=8
nprobe=64
```

pq64 在 ANN Recall 上损失过大；pq256 通过真实 Case 验证后进入 full build。继续增加 nprobe 几乎没有补回主要 Recall，说明当前误差主要来自 PQ 表示压缩。

### Lexical 与 metadata

```text
sentence BM25          1.557 GiB
metadata v2 SQLite     1.828 GiB
Qwen model             1.125 GiB
full serving bundle    ≈ 8.02 GiB
```

metadata v2 删除了请求期不需要的 clause `chunk_id UNIQUE` index。全量 DB 从约 2.313 GiB 降到 1.828 GiB，build 约 73 s。

### Current-work chronology

公开阅读数据库当前没有可靠逐首 dynasty。请求缺少该字段时：

1. 根据当前正文寻找 Werneror exact-content alias；
2. alias 无法解决时，对 exact author 统计 Werneror dynasty；
3. 唯一最高计数作为 corpus-compatible target label；
4. 并列或未知时保持 unknown。

这一值只参与 Candidate Eligibility。

生产节点观测到：

```text
温庭筠 → 唐
韦庄   → 唐
冯延巳 → 唐
李璟   → 唐
李煜   → 唐
```

因此 Werneror dynasty 只能支持粗 chronology。同朝、overlap、unknown 继续保留给 Agent 判断。

### 服务边界与历史资源基线

```text
Railway Web / Agent
        │ HTTPS + Bearer
        ▼
retrieval.poeticus.app（Cloudflare 公网入口）
        │ 命名 Tunnel：poeticus-retrieval
        ▼
Windows cloudflared（连接器）
        │ localhost:8787
        ▼
WSL Text Retrieval Service（127.0.0.1:8787）
```

Windows 连接器和 WSL Serving 是两个独立进程；Tunnel Token 用于连接器认证，Retrieval Bearer Token 用于 HTTP API 认证。Cloudflare 只转发请求，不执行 Qwen／FAISS 检索。2026-10-14 已完成命名 Tunnel 公网健康及正式站点 Agent 问答的实际验收；早期 Quick Tunnel 只作历史记录。旧腾讯云 Nginx 入口已退役。

历史腾讯云 2C8G Linux single worker 的 full Corpus benchmark：

- ready RSS 约 4.4 GiB；
- benchmark 后约 5.3 GiB；
- 首次 cold start 约 34.9 s；
- page cache 后一次 restart 约 18.25 s；
- 5 并发约 1.78 req/s。

上述旧资源基线不代表 WSL 或新 VPS 的性能，现行运维见 [当前部署](../deployment.md)。

### 已验证的 E2E canary

陆游：

```text
片片轻鸥落晚沙
```

在请求显式 `dynasty=null` 的情况下，Retriever 仍返回：

```text
杜甫《小寒食舟中作》
娟娟戏蝶过闲幔，片片轻鸥下急湍。
chronology_status=clearly_earlier
```

历史线上 Agent 曾正确使用杜甫候选，并把“文本对应很强”与“缺少明确引用记载”同时交代。2026-10-11 Quick Tunnel 的 E2E 也成功返回杜甫候选；2026-10-14 已在命名 Tunnel 和正式页面重新验证这条候选。

### 当前已知边界

- 完整拼接导致的重复 self-hit 已由 [#151](https://github.com/montricwang/poeticus/issues/151) 修复；异文／部分拼接／题序仍可能漏检，题名正文错配另见 [#173](https://github.com/montricwang/poeticus/issues/173)；
- 粗 dynasty overlap 会保留部分晚于目标作者的候选；
- Werneror dynasty 不能承担精细历史断代；
- transformed-use 仍可能需要 Agent query reformulation；
- 旧 2C8G 的长期并发上限尚未由真实流量确定；
- 唐宋 Serving Profile / Corpus pruning：#163，deferred。

当前 Retrieval 继续遵循一个停止线：真实产品 Case 出现新的稳定失败，再决定是否增加 reranker、clause BM25、pq512、multi-span 或更细 chronology。

### 从源码学习 Retrieval：先认清构建、运行和诊断

这一节是 **v0.3.0 代码地图**，不是服务器在线状态报告。旧腾讯云节点已销毁；本地恢复和 Railway 降级验收另见 [#180](https://github.com/montricwang/poeticus/issues/180)。下列流程描述模块职责，不表示所有资产在任何机器上都已就绪。

**第一条：离线构建（不会在每次用户请求时运行）**

```text
外部 Werneror CSV
  → scripts/corpus/werneror_import.py               Work JSONL
  → scripts/corpus/werneror_chunk.py                 sentence Chunk JSONL
    / scripts/corpus/werneror_clause_chunk.py       clause Chunk JSONL
  ├→ scripts/corpus/qwen_embedding_build.py
  │  / scripts/corpus/qwen_clause_embedding_build.py
  │        → Embedding shards + manifest
  │        → scripts/retrieval/faiss_full_index.py   两套 FAISS IVFPQ
  ├→ scripts/retrieval/lexical_bm25.py               sentence FTS5/BM25
  └→ scripts/retrieval/build_metadata_store.py      compact metadata SQLite
```

Embedding/Index/SQLite 是**可重建资产**，Work/Chunk 是它们的数据来源。Manifest、SHA256 和 row-id 对应关系是必要的数据契约；不要为缩短代码而删除校验。关键关系：**FAISS vector global row == Chunk JSONL logical row**；检索命中后依据 Metadata Store 回查它属于哪段文字、哪首作品。生产检索本身不扫描原始 JSONL。

**Embedding Artifact 的代码归属（#182 后续审计）**：`backend/retrieval/poem/embedding_artifact.py` 定义已完成 Embedding 的 Manifest 结构及校验规则，包括模型、chunk_policy、分片文件存在性、连续行号和总 Chunk 数。`scripts/retrieval/faiss_full_index.py` 是索引**构建入口**，直接引用这个稳定模块；`scripts/retrieval/artifact_search.py` 和 `exact_search.py` 是**诊断入口**，继续保留各自的检索行为。正式构建不再为校验 Manifest 导入实验入口。

```text
Embedding shards + manifest.json
       │
       ▼
backend/retrieval/poem/embedding_artifact.py
       ├→ FAISS index builder（faiss_full_index.py）
       └→ 单通道/Exact/Hybrid 实验诊断
```

这项检查发生在构建之前，确保行号与源 Embedding 的对应关系可用；但它并不验证来源文学文本的正确性，也不代替 `serving.py` 启动时对 FAISS、Embedding、BM25 与 Metadata 之间的交叉校验。只抽取稳定的 Manifest 契约，实验专属 Query 模型选择和 Corpus 路径规则仍留在对应诊断脚本中。



**第二条：运行期查询（先从这里开始读源码）**

```text
Agent (backend/ai/graph.py)
  → backend/retrieval/poem/client.py            HTTP 请求 / 失败转换
  → backend/retrieval/poem/server.py            API Schema、认证、/health
  → backend/retrieval/poem/serving.py           Runtime：校验资产、装配通道、整理响应
      ├─ serving_manifest.py              Manifest 读取与必要字段校验
      ├─ metadata_store.py                Work / Chunk 行号与正文回查
      └─ service.py                        TextRetrievalService：纯检索编排
          ├─ pipeline/query_strategy.py   passage/sentence/clause Query Plan
          ├─ pipeline/fanout.py            把去重后的 Query 发给各 Channel
          │    └─ serving_channels.py         真正访问模型 / FAISS / SQLite（poem 包）
          │         ├─ QwenQueryEncoder    Qwen Query Embedding + 缓存
          │         ├─ FaissDenseChannel   sentence / clause ANN
          │         └─ SentenceBm25Channel sentence 字符 n-gram + FTS5
          ├─ pipeline/fusion.py            Work-level RRF 聚合排名
          └─ pipeline/eligibility.py       排除自身/明确晚出的候选
  → server.py → client.py → Agent           Top-K 候选供模型比较
```

`scripts/retrieval/run_serving.py` 是**进程启动入口**：创建 `RetrievalServingRuntime`、交给 `server.create_app()`，再启动 Uvicorn。一次用户请求由 `server.py` 调用**已装载的** Runtime；Runtime 使用 `TextRetrievalService`，后者通过 Channel 协议查询常驻索引，不会每次重新加载 Qwen / FAISS。

**职责与信任边界**：`serving_manifest.py` 在启动与通道装载时检查 Manifest；`serving_channels.py` 只知道怎样把查询变成 `RetrievalHit`；`service.py` 不依赖 FAISS、SQLite 或 Qwen 的细节，只关心 Query Plan、Fan-out、RRF、Eligibility。HTTP 错误由 Client / Agent 处理，空候选不意味着已证实出处。

**第三条：哪些脚本不是线上主路径**

| 类别 | 入口 | 保留意义 |
| --- | --- | --- |
| 正式启动 | `run_serving.py` | 配置、加载并启动 HTTP 服务 |
| 离线构建 | `faiss_full_index.py`、`lexical_bm25.py`、`build_metadata_store.py` | 重新生成可检索资产 |
| 基线/实验 | `exact_search.py`、`artifact_search.py`、`faiss_search.py` | 精确向量、不同 Embedding、单通道 ANN 诊断 |
| 评估/诊断 | `hybrid_eval.py`、`benchmark_serving.py`、`smoke_agent_retrieval.py`、`inspect_serving_bundle.py` | 候选质量、性能、端到端行为、资产检查 |
| 辅助 | `vector_sampling.py`、`deploy_vps.sh` | FAISS 训练采样、特定环境的历史部署工具 |


**Hybrid Eval 与生产 Runtime 的取舍（#182 P2 审计）**：保留 `scripts/retrieval/hybrid_eval.py` 作为**离线诊断基线**，它通过 JSONL 回查原始 Chunk/Work，并报告每个 Query × Channel 的 probe rank、缺失列表及融合前后候选情况。正式 `RetrievalServingRuntime` 使用预构建 Metadata SQLite、常驻模型与索引，只返回产品需要的候选和性能摘要。两者共享 Query Plan、RRF、Eligibility 的确定性算法，但**不同的资产读取和诊断语义有意保留**；不能为了减少重复直接将 Eval 入口替换为生产 Runtime。此处是源码职责判断，不代表已完成同一真实 Artifact 下的输出对照验收。

**抽象边界（#182 P1）**：`backend/retrieval/poem/lexical_terms.py` 负责共同字符切分与 FTS5 表达式；离线诊断对不可检索 Query 抛错，在线 Serving 将其视为无结果。`backend/retrieval/poem/artifact_files.py` 提供不依赖模型的 SHA256 文件哈希。长期构建工具不再从 `exact_search.py` 借用路径常量与哈希函数。历史实验仍可复用 Exact Search 的诊断算法。

**推荐学习顺序**：先读 `server.create_app` → `serving.RetrievalServingRuntime.search` → `service.TextRetrievalService.search`，明确「入口、运行时、编排」各自负责什么；再读 `query_strategy`、`fanout`、`fusion`、`eligibility`；最后才进入 `serving_channels.FaissDenseChannel / SentenceBm25Channel`、`serving_manifest` 与离线构建。遇到 Manifest/行号不一致时先查资产版本契约；不要先从历史实验脚本开始，也不必先理解 IVFPQ 的内部数学。

## 1. 目标与非目标

Poem Retrieval 只解决一个问题：

> **给当前诗词中的一段文本，从前代语料中找出值得让 LLM 继续比较的候选文本。**

它不是文学知识库，也不负责最终证明“这句一定化用了那句”。

```text
当前文本
↓
Text Retriever
↓
Top-K 候选前代文本
↓
DeepSeek / Agent
↓
比较、判断关系、解释证据与不确定性
```

因此，相似度高只是候选信号，不自动等于“来源已证实”。

## 2. 与现有 Evidence 的分工

当前按问题类型区分：

- `lookup_allusion`：人物、故事、典故性短语；
- `lookup_reference`：现有 reference evidence；
- Poem Retrieval：当前诗词与语料中前代诗歌之间的候选发现；
- DeepSeek / Agent：综合候选与上下文作最终判断。

不把所有文学证据统一塞进一个万能向量库。

## 3. 离线 Corpus Pipeline

当前外部 Retrieval Corpus 使用 Werneror/Poetry：

```text
Werneror CSV
↓
Work JSONL
↓
sentence / clause Chunk JSONL
↓
Qwen document embedding
↓
Embedding Artifact
↓
FAISS / BM25 Serving Index
```

### Work

第一版字段：

```text
work_id
title
author
dynasty
content
source
source_record_id
```

`work_id` 用于 Chunk 回查整首作品；`source` / `source_record_id` 保留外部来源可追溯性。

### Chunk

当前保留两种检索粒度：

**sentence**

- 在 `。！？!?` 后结束；
- 逗号、分号保留在句内；
- 4,822,054 Chunk；
- 平均 5.651 Chunk / Work；
- 最长 132 字符。

**clause**

- 在逗号、分号和句末标点处分开；
- 9,425,173 Chunk；
- 平均 11.044 Chunk / Work；
- 最长 34 字符。

两者都保留原标点、`work_id` 与 `[start, end)` Unicode code-point offset，可从 `Work.content` 精确还原。

真实 Exact Retrieval 已证明两种粒度互补：当互文只落在 sentence 的一部分时，clause 可以避免上下文稀释；但当化用压缩了同一 sentence 中两个 clause 的信息时，sentence 反而能保留必要上下文。因此当前不再把 sentence / clause 看成二选一，而把它们作为多粒度 Retrieval 的两个候选层。

## 4. Corpus Chunking 与 Query Strategy 分开

这两个问题不要求采用同一粒度。

**Corpus Chunking** 回答：前代语料以什么单位进入检索索引？  
当前保留：sentence + clause。已有真实案例表明两者互补，暂不继续增加更多粒度。

**Query Strategy** 回答：当前正在阅读的一整首诗词，哪些片段需要发起 Retrieval？

第一版不先让 LLM 改写 Query，而是确定性地产生三层候选：

```text
用户选中 / 当前片段
├─ passage：保留完整上下文
├─ sentence：按 Corpus sentence policy 切分
└─ clause：按 Corpus clause policy 切分
```

Query side 与 Corpus side 复用同一套 sentence / clause 边界规则，避免索引切分和查询切分静默漂移。完全相同的 query text 只执行一次搜索，但保留它来自 passage / sentence / clause 哪些位置的 provenance；例如只有一句且没有逗号的短句，不会因为三层策略重复搜索三次。

这一层只负责生成稳定 Query Plan；Dense / Lexical fan-out、Candidate Fusion 和 chronology filtering 仍属于后续层，不在 Query Planner 内耦合。

### Query Fan-out

Query Plan 之后增加独立执行层：

```text
Query Plan
├─ Dense sentence channel
├─ Dense clause channel
├─ Lexical sentence channel
└─ 未来可增加 Lexical clause / ANN channel
      ↓
per-query × per-channel ranked results
```

Fan-out 层只负责把同一批**去重后的 Query**交给每个已配置的 Retrieval channel，并保留：

- query text 与 passage / sentence / clause provenance；
- channel identity；
- retrieval method（Dense / Lexical）；
- corpus chunk policy（sentence / clause）；
- 各 channel 自己的 rank 与 raw score。

这里有两个刻意的边界：

1. **Query 粒度与 Corpus Chunk 粒度继续独立。** passage Query 也可以查 sentence / clause Corpus；是否有价值由后续 Eval / Fusion 判断，而不是在 fan-out 前写死路由。
2. **channel 必须提供 batch-oriented `search_many`。** 一个 channel 一次接收全部 unique query，避免未来 Dense backend 为每条 query 反复加载模型或重复建立连接。

Fan-out 层不归一化 BM25 / cosine，也不做候选去重；这些属于下一层 Candidate Fusion。当前 Exact Search 与 SQLite FTS5 仍是诊断 / baseline 实现，不在这一层反向绑定生产接口。

第一版仍倾向于让诗句都可以进入 Retrieval，而不是先用分类器判断“值不值得查”。诗词本身较短，预过滤带来的计算节省有限，却可能在 Retriever 之前造成不可恢复的 Recall 损失。

## 5. Embedding 模型

第一版默认：

```text
Qwen/Qwen3-Embedding-0.6B
```

选择它是为了先获得一个现代、中文能力强、许可清楚、支持 Matryoshka 降维的默认 Retriever，不代表已经证明它在古典诗词互文检索上优于所有模型。

当前编码约定：

- Corpus Document：直接编码文本；
- Query：未来可使用固定 Retrieval instruction；
- 两者最终进入同一个可比较向量空间；
- Query instruction 尚未冻结。

BERT-CCPoem 作为领域模型 challenger。clause-level Artifact 已完成，并与 Qwen clause 用同一批真实互文案例对照。当前两个代表性案例中，Qwen / BERT 各有小幅胜负，但差异远小于 sentence / clause 粒度变化带来的排名变化，因此暂时没有证据支持把 BERT-CCPoem 升为生产候选；它保留为实验对照即可。官方实现对正文 token 做 mean pooling（排除 [CLS] / [SEP] / padding），本项目实验实现保持这一口径。

## 6. Embedding Artifact

当前已完成的 sentence baseline：

```text
model: Qwen3-Embedding-0.6B
chunk policy: sentence
dimension: 1024
normalized: true
dtype: float16
shard size: 10,000
chunks: 4,822,054
```

当前新增对照构建：

```text
Qwen3-Embedding-0.6B + clause + 1024d
BERT-CCPoem v1.0 + clause + 512d
```

两套 clause Artifact 都从同一份 clause Chunk JSONL 生成，便于比较模型差异；sentence Artifact 保留，便于比较 Chunk 粒度差异。

Embedding 先作为独立离线构建产物保存：

```text
../poeticus-data/retrieval/embeddings/qwen3_0.6b_sentence_1024/
├─ manifest.json
├─ shard_00000.npy
├─ shard_00001.npy
└─ ...
```

manifest 绑定：

- 输入 Chunk 文件 SHA256；
- 模型 fingerprint；
- model id；
- dimension；
- dtype；
- normalize；
- shard size；
- expected / completed chunks；
- 每个 shard 的范围和 SHA256。

生成过程采用分片、原子写入和断点续跑；参数或输入变化时拒绝与旧结果混用。

核心原则：

> **Embedding 是昂贵但可复用的构建资产；Vector DB / ANN Index 是它的部署形式。**

以后更换 pgvector、FAISS 或重建 ANN，不应因此重新做全量模型推理。

## 7. 时间顺序

Poem Retrieval 的产品问题是寻找“前代”文本，而不是任意时代的相似文本。

因此 chronology 至少需要参与最终候选约束，但第一版不建立复杂年代知识库。当前可依赖的基础 metadata 是 dynasty；同朝代的精确先后仍可能不确定，应允许 LLM 输出不确定性。

具体采用 ANN 前过滤、ANN 后过滤还是分区索引，等待真实 Vector Index 方案确定后再决定。

## 8. 语料文本不是最终权威文本

Werneror/Poetry 适合作为大规模候选发现语料，但不能把其中的正文自动当成最终可引用的权威版本。

本轮 Exact Retrieval 已遇到实际例子：王维《渭城曲》在当前语料中出现为“客舍青青杨柳春”，而我们原先用于 Eval 的常见版本是“客舍青青柳色新”。这类差异可能来自版本异文、录入来源差异或语料错误，单靠 Retrieval 本身无法判定。

因此系统边界明确为：

- Retrieval 命中 = 候选证据，不等于原文已经核定；
- 如果候选只用于继续比较，可以先进入 DeepSeek / Agent；
- 如果最终回答要把某句明确说成“某作者原文”或据此判断化用关系，且文本存在冲突、异常或来源不明，应再查可靠外部来源核对；
- 不要求每条候选都联网复核，只有候选将被当作关键证据时才增加这一步。

这也意味着后续 Retrieval 结果应保留 `source` / `source_record_id`，让模型和用户知道当前文本来自哪个语料版本，而不是把语料内容包装成无来源的事实。

## 9. Eval 策略

不为 Embedding 另造一套独立研究 Benchmark。

正式 Retrieval 建成后，优先复用已经整理的 intertext Eval，观察正确 predecessor source 是否进入可供 DeepSeek 处理的候选范围。

重点不是要求 Retriever 自己 Rank 1 下结论，而是：

> **Retriever 是否把真正值得比较的前代文本稳定带进 Top-K？**

当前两个代表性结果已经说明 Chunk 粒度是一级变量：

- “片片轻鸥落晚沙” → 杜甫“片片轻鸥下急湍”：Qwen sentence rank 445，Qwen clause rank 2；
- “蜡烛到明垂泪” → 杜牧“替人垂泪到天明”：Qwen sentence rank 1，Qwen clause rank 10。

因此下一阶段优先保留 sentence + clause 多粒度召回，而不是继续扩大 Embedding 模型比较。

只有真实失败出现后，再按类型判断：

- Corpus coverage；
- Chunk 粒度；
- Query Strategy；
- Embedding 模型；
- chronology；
- lexical / dense hybrid；
- reranker。

不在失败证据出现前同时引入这些复杂度。

## 10. 当前已定事项与仍开放的边界

**已实现且运行中**：Qwen sentence/clause Dense、BM25、Query Plan、RRF、Eligibility、FAISS IVFPQ、compact metadata、独立 HTTP Serving 和可选 Werneror 拼接去重。当前 WSL 经命名 Tunnel 为 Railway Agent 按需服务，**并非长期托管云节点**；历史性能见第 0 节，最新启动与验收命令见 [Deployment](../deployment.md)。

**待解决或待观察**：

- [#151](https://github.com/montricwang/poeticus/issues/151) 已完成：完整拼接造成的重复 self-hit；未覆盖异文仍属边界；
- 粗粒度朝代与同朝先后无法提供准确 chronology，可靠逐首年代数据仍待补；
- #167 涉及已销毁的旧云节点证书，不能作为当前 WSL/Tunnel 的操作步骤；
- WSL/Tunnel 的持续可用性、重启恢复与未来独立主机的稳定性和并发上限；
- 全文 multi-span evidence、curated 文献 RAG，以及必要时的 Agent / Retrieval Eval 增量；
- #163：唐宋 Serving Profile 属 deferred，不是本版发布阻塞项。

**停止线**：没有新增稳定失败前，不再惯性引入 pq512、clause BM25、reranker、古汉语分词、GPU 或多 worker。具体的阶段顺序由 [Roadmap](../roadmap.md) 和各 Issue 维护。

## 历史实验与证据

此前在 2026-10-07 经过 Qwen/BERT 对照、BM25、RRF、FAISS IVFPQ Spike 才收敛到上述运行方案，不能把那天出现的“下一阶段候选”当作今天尚待实现的工作。

- **长期检索取舍与真实数字**：见 [ADR-0002](../adr/0002-hybrid-text-retrieval.md)；
- **年代推断与证据边界**：见 [ADR-0003](../adr/0003-coarse-chronology-fallback.md)；
- **过程、失败假设与实验顺序**：见 [2026-10-07 开发日志](../devlog/2026-10-07.md)；
- 原先本文第 11 节历史方案完整留在 [整理前 Git 版本](https://github.com/montricwang/poeticus/blob/4e44f3e96873d1bff885e83faa0f1ae8d7a73c4c/docs/architecture/text-retrieval.md#11-实验阶段的设计演进2026-10-07历史记录)。

当前参数和流程以本文前述章节及 [部署说明](../deployment.md) 为准。
