# Poeticus 文档导航

这个目录不是另一套知识库。**一项当前事实只有一个权威位置**；历史研究记录可以有多份，但不需要随新版同步改写。

## 从问题找文档

| 你想知道 | 去哪里 | 维护粒度 |
| --- | --- | --- |
| Poeticus 做什么、公开体验、项目全局组成 | [根 README](../README.md) | 面向读者/新开发者的简要入口 |
| 已确认的前端视觉规则、首页竖排、颜色/字距和光学修正到哪里改 | [前端视觉与排版规范](design/frontend-visual-conventions.md) | 行为约束与编辑选择分开写；调参以实际 CSS / TSX 为准 |
| **现在**代码和服务怎样组织、数据怎样流动 | [Architecture](architecture/) | 一子系统一份当前说明；变更架构时更新 |
| 某项重要技术方案**为什么**这样选 | [ADR](adr/README.md) | 一个跨阶段的长期决策一篇；证据/Origin/代价/复审条件 |
| 如何安装、启动、测试、提交变更 | [开发者指南](development.md) | 仅当前有效的开发操作 |
| 已修复的常见编码失误怎样避免重犯 | [代码问题复盘](coding-lessons.md) | 只留有复用价值的原因、预防和验证；优先自动化防回归 |
| 如何部署、验证线上健康和排障 | [生产部署](deployment.md) | 仅当前有效的运行环境/操作；不要照历史 Spike 操作 |
| 私人 `poeticus-data/` 放什么、如何备份迁移 | [私人数据工作区](data-management.md) | 私有资产生命周期、目录契约；非项目架构综述 |
| 商业 EPUB 的分册规则、数据字段、来源核实结论 | [EPUB 维护地图](corpus/epub-pipeline-maintenance-map.md) | 当前来源特例和代码定位 |
| 怎样重建、审计和人工核对 EPUB | [EPUB SOP](corpus/epub-import-sop.md) | 当前可以执行的工作流程与命令 |
| 尚未确认的 `font1` / `kaiti` 源书样本 | [EPUB 分类复核记录](corpus/epub-classifier-design.md) | 研究与未决问题，不是权威解析 Schema |
| 产品/工程的下一阶段方向 | [Roadmap](roadmap.md) / [GitHub Issues](https://github.com/montricwang/poeticus/issues) | Roadmap 按阶段，Issue 按单个可验收工作 |
| 文学推荐、诗学画像、持续学习与 Prompt 优化的跨模块研究 | [文学学习研究规划](literary-learning-research-plan.md) | 只保存整体研究地图、文献复用与阶段性启动条件；实际任务仍以对应 Issue 为准 |
| 本地开源模型的离线推理、性能边界与文献 Refine 质量实验 | [推理可行性 #339](https://github.com/montricwang/poeticus/issues/339) / [文献 Refine #341](https://github.com/montricwang/poeticus/issues/341) | Issue 维护实验进度与验收；私人模型权重、路径和日志不入仓库 |
| **已有数字人文资源**：古籍、典故、词话、API、论文与授权 | [数字人文资源地图](digital-humanities-resources.md) / [复用验证 #184](https://github.com/montricwang/poeticus/issues/184) | 资源地图保存现有外部成果与核实状态；Issue 记录实际实验 |
| 某天怎么做、哪些假设被推翻 | [开发日志](devlog/) | 按日期冻结，不追着现行代码改 |
| 某个版本发布时包含什么 | [Releases](releases/) | 按版本冻结，不追着现行代码改 |

## 当前架构

- [Agent / LangGraph](architecture/langgraph.md)：工具调用、Graph State、流式回答；
- [Conversation State](architecture/conversation-state.md)：作品/会话生命周期与浏览器存储；
- [Homepage](architecture/home-screen.md)：首页每日推荐、搜索与入场动效、手机竖排、五列上限及节选规则；
- [Corpus Database](architecture/corpus-database.md)：私人导入、公开白名单、数据身份；
- [Poem Retrieval](architecture/text-retrieval.md)：Work/Chunk、Qwen/FAISS/BM25、RRF、Eligibility、Werneror 拼接去重与 Serving。
- [Document Corpus](architecture/document-corpus.md)：本地四书 PostgreSQL/pgvector 文献库、词话候选证据、可选实验 Reranker 与权利边界；实验方法及结果见 [Document RAG 实验记录](../scripts/experiments/README-document-rag.md)。

## 当前重要决策

- [ADR-0001：独立 Text Retrieval Service](adr/0001-separate-text-retrieval-service.md)
- [ADR-0002：Hybrid 多粒度检索](adr/0002-hybrid-text-retrieval.md)
- [ADR-0003：粗 chronology fallback 与数据可信度](adr/0003-coarse-chronology-fallback.md)
- [ADR-0004：私人来源与公开阅读库分离](adr/0004-private-public-corpus-boundary.md)

## 文档怎样选址、什么时候删除

1. **当前结构、接口、数据语义**写在 `architecture/` 或领域维护地图；不要把历史实验日志直接追加到架构章节。
2. **不可忽视的长期取舍**写 ADR，记录证据强度、替代方案、决策来源及重审条件。普通参数在配置及相关架构说明中，未决事项进入 Issue。不要为每个阈值建立 ADR。
3. **命令和工作步骤**写开发指南、部署指南或 SOP；不把完成的临时 Spike 当作今日操作手册。
4. **某天的过程和当时的错误假设**留在 `devlog/`；日期文件可以真实记载当时不成熟的认识，不代表当前规则。
5. **实验脚本与旧文档退出当前树之前**：将独有的可重复验证能力留下（代码/测试），将可靠结论与未解决问题写入权威说明/ADR/Issue。历史稿可通过 Git 版本找到，不另造永久 `archive/`。
6. **文档更新顺序**：先改代码/配置并验收，再更新唯一权威文档；其他文件只保留链接，避免拷贝同一批参数或步骤。

### 历史文件怎样查

2026-10-08 的知识沉淀整理前，`docs/decisions/` 是按日期保存的决策审计快照，`docs/corpus/` 有独立 DOM、审计、语义旧稿和来源定位工具说明，`docs/deployment/retrieval-linux-spike.md` 记录了首次 Linux 实验。独有知识已迁移到 ADR、EPUB 维护地图与 SOP；完整旧版本仍在 [Git 快照 `4e44f3e`](https://github.com/montricwang/poeticus/tree/4e44f3e96873d1bff885e83faa0f1ae8d7a73c4c/docs)，不要拿旧稿作为当前执行依据。

脚本与知识沉淀后续验收跟踪 [Issue #177](https://github.com/montricwang/poeticus/issues/177)。
