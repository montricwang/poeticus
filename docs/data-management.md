# poeticus-data：私人数据工作区与资产管理

本文件专门说明仓库旁边的 **`poeticus-data/`**：目录职责、哪些输入/Artifact 值得保存、如何备份和迁移，以及如何验证重建。它**不**解释全项目的数据库 Schema、在线 Retrieval 架构或通用文件存储原则；相关内容分别见 [Corpus Database](architecture/corpus-database.md) 与 [Text Retrieval](architecture/text-retrieval.md)。这些私人文件不进入公开 Git 历史，是否值得保留也不能由 `.gitignore` 判断。

## 1. 数据根目录和路径规则

默认从代码所在位置推导：`poeticus/` 的**同级目录**为 `poeticus-data/`。不假定 D 盘、Windows 或特定用户名，也不依赖运行脚本时的当前工作目录。仅在需要时设置**绝对路径**环境变量 `POETICUS_DATA_ROOT`，覆盖默认目录。实现统一维护于 `backend/data_paths.py`。

```text
workspace/
├── poeticus/                    # Git 仓库：代码、测试、文档
└── poeticus-data/               # 不受 Git 管理的私人数据
    ├── reading-corpus/
    │   ├── raw/                  # EPUB、glyph_maps/
    │   ├── normalized/           # all_normalized.json、all_manifest.json、分册快照
    │   └── review/               # glyph_review_backup.json 等人工复核备份
    ├── retrieval/
    │   ├── corpus/               # Werneror Work、sentence/clause Chunk JSONL
    │   ├── embeddings/           # 离线计算向量及每批 manifest
    │   ├── faiss/                # FAISS 索引及 manifest
    │   ├── lexical/              # BM25 / SQLite 索引
    │   ├── serving/              # Retrieval metadata SQLite 及 manifest
    │   └── relationships/         # 组诗去重快照 v3：SQLite、CSV、manifest
    ├── lexicon/                  # 私人历史语汇书库：源修订、清单、离线 SQLite 索引
    ├── models/                   # Embedding / GGUF 本地推理模型权重
    ├── tools/                    # 私人模型运行时与实验日志（若安装）
    └── reports/
        ├── epub-import/          # EPUB 诊断、审计及复核材料
        ├── retrieval/            # 检索评测和构建报告
        └── evals/                # Agent / Evidence 评测报告
```

`all_manifest.json` 与 `all_normalized.json` 属于同一批规范化数据，应该同目录。向量或索引的 `manifest.json` 应紧贴其对应 Artifact，不集中放在一个全局 manifests 文件夹。

### 本地模型目录与核验（2026-10-19）

开发机 WSL 的实际根目录是 `~/projects/poeticus-data/models/`，与 `~/projects/poeticus/` 并列。路径按仓库相对关系描述；换电脑时应从 `POETICUS_DATA_ROOT` 或 `backend/data_paths.py` 推导，不把用户名、盘符写死进程序。

| 用途 | 相对 `poeticus-data/models/` 的位置 | 状态 |
| --- | --- | --- |
| Poem Retrieval 查询向量 | `Qwen3-Embedding-0.6B-7c0e29cfcdf2/` | 现有 Serving 资产；不要与生成式 Qwen 混用 |
| BERT/CCPoem 研究 | `BERT_CCPoem_v1/` | 原有实验资产 |
| 本地生成式推理 | `Qwen3.5-4B/Qwen3.5-4B-Q4_K_M.gguf` | 2,740,937,888 bytes；SHA-256 `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`；CPU / Windows Vulkan 已生成中文回答 |
| 本地生成式推理 | `DeepSeek-R1-0528-Qwen3-8B/DeepSeek-R1-0528-Qwen3-8B-Q4_K_M.gguf` | 5,027,785,216 bytes；SHA-256 `a86349a4180c4e6bb43f874c29c404fa2be3f90b15509bd6d86f697dba724ec1`；CPU / Windows Vulkan 已生成 Token，短测试未得到完整文学回答 |
| 低比特生成式推理 | `Ternary-Bonsai-2-27B/Ternary-Bonsai-2-27B-PTQ1_0.gguf` | 5,946,648,928 bytes；SHA-256 `53107f530aa52eb00912263ab1ee29bd199261c87cd7b4ad4ca1318c1fe33ee3`；**需 Prism ML 定制版 llama.cpp**，Windows Vulkan 已生成完整中文短答 |
| Document RAG 精排实验 | `Qwen3-Reranker-0.6B/`（含原始模型与 `Qwen3-Reranker-0.6B-Q4_K_M.gguf`） | GGUF 396,476,288 bytes；SHA-256 `c04f5f5657c52e04538c455e8c62817db3d3b795b39e9f547f8581510445f075`；本地 CPU 与 Windows Vulkan `/v1/rerank` 均已验证，**产品默认关闭** |

Qwen3.5-4B 与 DeepSeek 8B 的 GGUF 从 ModelScope 的 `unsloth/Qwen3.5-4B-GGUF`、`unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF` 获取，原先已核对 SHA-256 与镜像文件清单一致；Bonsai 27B 和 Reranker 的上述 SHA-256 则于 2026-10-19 从本地现存文件重新计算。**哈希校验与能否完成推理是不同的验证**：前三款生成式模型的 CPU/Windows Vulkan 短测试见 [当日 devlog](devlog/2026-10-19.md) 与 [#339](https://github.com/montricwang/poeticus/issues/339)；Reranker 的 16 题精排结果见 [Document RAG 实验记录](../scripts/experiments/README-document-rag.md)。后续仍需独立检验长上下文、稳定性、实际文学分析质量与推理开销。

私人下载脚本位于 `poeticus-data/models/download_cn_models.sh`，不是产品运行依赖。所有模型权重保留在仓库外的 `poeticus-data/models/`，不得复制到公开仓库、前端资产或 Railway 构建上下文；本机推理运行时另放 `poeticus-data/tools/`。Benchmark 与报告应放在所属私有实验目录（如 `document-corpus/evals/results/` 或 `reports/evals/`）。模型切换不应改写现有 Poem Retrieval 的 Embedding 模型目录与 FAISS 索引。**密钥存放、生产环境变量及安全边界**见 [开发者指南的本地配置](development.md#2-本地配置) 和 [部署指南](deployment.md)。


**不强制设置顶层 `output/`**。只运行一次、无需留存的临时输出可使用系统临时目录或终端输出；有长期价值的生成数据放在具有稳定职责的目录。

## 2. 哪些数据应当保留

| 数据 | 恢复能力与用途 | 建议 |
| --- | --- | --- |
| `reading-corpus/raw/历代名家词集精华录.epub` | 完整解析的原始来源，不可由代码恢复 | **异地备份** |
| `reading-corpus/raw/glyph_maps/*.json` | 人工确认的图片字映射，不可自动恢复 | **异地备份** |
| `reading-corpus/review/glyph_review_backup.json` | 曾经的人工辨字工作备份；与 glyph_maps 核对后仍有独立备份价值 | **保留** |
| `reading-corpus/normalized/all_normalized.json` | 已验收的数据库恢复快照；免去重新提取、复核 EPUB | **保留与备份** |
| `reading-corpus/normalized/all_manifest.json` | 与规范化快照同行的构建清单 | 保留 |
| 其他分册 `*.json` / `*_normalized.json` | 已汇入可信全量快照后原则上可重建 | 按需要归档 |
| `retrieval/corpus/*.jsonl` | 完整 Werneror 作品和 Chunk 中间数据，用于离线重建 | 保留，重建索引时可能需要 |
| `retrieval/embeddings/` | 原始数千万 float16 向量，重建成本高 | **重点保护** |
| `retrieval/faiss/`、`lexical/`、`serving/` | 线上可用的检索索引与元数据 | **必须保留可用 Serving 版本** |
| `retrieval/relationships/v3/` | 组诗重复过滤的 SQLite 快照、导入 CSV 与来源指纹 manifest；不是原始语料，也不是 Railway PostgreSQL 表 | **与当前 Serving 一起保留／备份**，避免启动时缺失或版本不匹配 |
| `lexicon/shi-ci-qu-yu-ci-hui-shi/sources/` 与 `manifest.json` | 张相《詩詞曲語辭匯釋》2026-10-20 私人源修订 906 页，含原始 Wikitext、revision ID、来源、时间、SHA-256 | **保留与备份**，不进入 Git / Railway；详见[本地词典说明](../scripts/corpus/README-local-lexicon.md) |
| `lexicon/shi-ci-qu-yu-ci-hui-shi/lexicon.sqlite` | 537 个词头的 FTS5 派生查询索引 | 可从原始源文件离线重建，不必优先备份 |
| `models/` | Embedding 权重及离线 LLM GGUF 试验权重、校验指纹；后者已在本机验证，不是线上模型服务依赖 | 保留当前所需版本与校验值；大文件不入 Git，按重下成本决定是否备份 |
| `tools/`（若存在） | 隔离的本地推理运行时、实验脚本与日志，不属于产品虚拟环境 | 正式化前按实验价值保留；勿因清理 Git worktree 误删私人资产 |
| `reports/` | 诊断、Benchmark、历史研究记录 | 按证据价值归档；不要求永久保留每次运行 |

**恢复成本与“能否重新生成”是两回事**。Embedding 技术上可重算，但很昂贵；人工校对成果更不应因为程序能再次运行而删除。已有报告中人工备注也需要先提取。

历史 `corpus_quality_report.json` 仅涉及温庭筠、韦庄旧流程；`epub_coverage_all_10021601.md` 是旧版 15 册候选抽取审计，不代表现行最终质量结论。若仍有未关闭的审计问题，先保留对应记录。

## 3. 旧数据迁移映射（**先检查和备份，再手动移动**）

以下路径都**相对于原 `poeticus-data/` 根目录**。迁移只涉及本地目录，不能用 `git pull` 自动搬动你的私有数据。

| 旧目录或文件 | 新目录或文件 |
| --- | --- |
| `raw/` | `reading-corpus/raw/` |
| `output/all_normalized.json`、`output/all_manifest.json` 及同批分册 JSON | `reading-corpus/normalized/` |
| `output/retrieval/werneror_works.jsonl`、`werneror_chunks_*.jsonl` | `retrieval/corpus/` |
| `output/retrieval/{embeddings,faiss,lexical,serving}/` | `retrieval/{embeddings,faiss,lexical,serving}/` |
| `output/retrieval/werneror_clause_chunks.json` | `reports/retrieval/werneror_clause_chunks.json` |
| `models/` | 不变 |
| `reports/retrieval/` | 不变 |
| `reports/glyph_review_backup.json` | `reading-corpus/review/glyph_review_backup.json` |
| `reports/` 下 EPUB 审计、诊断、复核材料 | `reports/epub-import/` |
| 仓库内部遗留 `poeticus/data/` | 检查有无尚未迁出的私有文件，核对后再清理 |

**不要在目标已有同名文件时覆盖，不要用 `git clean -fdx` 清理私人数据。** 先确认两个文件树中的文件、大小、hash 与用途，再移动。大目录建议在同一磁盘分区内移动；迁移途中保持原资料备份，迁移前停止读写相应数据的进程。原始数据、原始 Embedding 和 Serving Bundle 不应在迁移步骤中被自动重建。

**历史说明**：曾经的腾讯云 Retrieval 主机已销毁；旧 `/opt/poeticus-data/output/retrieval` 不是现在的生产路径，切勿照此向旧节点部署。当前实际运行在 WSL，按 [部署文档](deployment.md) 使用 `poeticus-data/retrieval/relationships/v3/`。

## 4. 重新生成与验证

从 EPUB 重建阅读数据（先确保本地文件已按新目录放置）：

```powershell
python -m scripts.corpus.epub_import.import_poems --all --check
python -m scripts.corpus.epub_import.import_poems --all
python -m scripts.corpus.db_import --check
python -m scripts.corpus.db_import --migrate
python -m scripts.corpus.db_import --import
```

如果已有可信 `all_normalized.json` 且只需恢复 PostgreSQL，可跳过 EPUB 重新解析，直接运行 `db_import` 命令。

检验 Retrieval Serving Bundle 是否包含 sentence/clause Embedding manifest、FAISS、BM25、metadata SQLite 和 Qwen 模型：

```powershell
python -m scripts.retrieval.inspect_serving_bundle
```

正式启动时还需确认 `retrieval/relationships/v3/work_compositions.sqlite3` 与相邻 `work_compositions_manifest.json` 同时存在，并与当前 Werneror Corpus 指纹相符。完整的合集关系表可由 `scripts/corpus/export_work_compositions.py` 根据已有审计报告重新导出（归一化补漏需传 `--normalized-audit`），但是**首次缺失快照时不要直接重跑向量或索引**。正常加载后，再运行 Retrieval E2E 和 benchmark；**文件存在不等于索引能加载或召回正确**。完整模型与向量构建需要额外 `requirements-retrieval.txt` 依赖。

### 《詩詞曲語辭匯釋》离线恢复（2026-10-20）

私人源修订和索引位于项目同级 `poeticus-data/lexicon/shi-ci-qu-yu-ci-hui-shi/`。已保存 `sources/`、`manifest.json` 时不需要网络、模型或 PostgreSQL，即可重建、查询：

```bash
.venv/bin/python -m scripts.corpus.local_lexicon build
.venv/bin/python -m scripts.corpus.local_lexicon lookup 怎生
```

采集器可通过 `--data-root` / `POETICUS_LEXICON_DATA_ROOT` 单独指定私人数据路径；它尚未复用其它语料工具的 `POETICUS_DATA_ROOT` 环境变量。详见[词典采集、版本与验收说明](../scripts/corpus/README-local-lexicon.md)。这只是本地候选证据，并未更改生产诗词库或公开 Agent；后续 AI 识词与多义项展示归 [#335](https://github.com/montricwang/poeticus/issues/335)。

## 5. 脚本和报告的保留约定

- **保留正式入口**：EPUB 全量预检、字形复核/导入、Werneror 语料转换、Embedding/索引构建、DB 恢复、Retrieval Serving。
- **保留可复用诊断能力**：`scripts/corpus/epub_import/diagnostics/` 和 Retrieval Eval 中有实际复现价值的工具。
- **实验和一次性 Probe**：按功能、正式调用、测试与知识沉淀逐个评估；已经退役的入口可从 Git 历史找回。其余九个专项脚本的验收见 #177。
- **报告与脚本分开决定**：可重建报告不必全部永久放在活跃目录，但作为选型证据或含人工结论的历史报告可归档。脚本不常运行也不等于无价值。
- 若脚本输出私人 EPUB 原文、glyph 上下文或私有证据，一律不能写入公开仓库或 `VITE_*` 等前端配置。

本文件为当前目录契约。EPUB 相关报告的标准子目录拼写是 `reports/epub-import/`（连字符），不是 `reports/epub_import/`。旧布局中的具体文件应先盘点，再分批迁移；脚本整理工作跟踪 [#177](https://github.com/montricwang/poeticus/issues/177)。
