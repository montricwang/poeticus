# Poeticus：系统与职责总览

> 更新：2026-10-21。本页说明各部分怎样配合，以及哪些能力已经落地。具体实现以对应架构文档为准；待办和优先级以 [Roadmap](../roadmap.md) 与 GitHub Issue 为准。

## 现在怎样工作

1. 读者在 React 阅读界面浏览作品、搜索、选中文字或发起对话。公开作品来自 Railway PostgreSQL；私人来源材料不会随阅读库发布。
2. FastAPI 提供作品接口、聊天与流式输出。聊天由单个 LangGraph ReAct Agent 决定是否查证；“整首赏析”仍是独立模型调用，没有自动进入 Agent 的工具循环。
3. Agent 可按配置查询 CNKGraph、独立诗句检索和本地文献库。诗句检索经 Cloudflare Tunnel 访问按需运行的 WSL 服务；工具返回的是待核查的资料，不会直接修改作品正文。
4. 浏览器按作品在 localStorage 保存会话和草稿；服务端目前没有用户账号、长期会话存储或跨设备同步。

各处细节：[作品数据库](corpus-database.md) · [LangGraph](langgraph.md) · [诗句检索](text-retrieval.md) · [会话状态](conversation-state.md) · [部署](../deployment.md)。

## 六个领域各管什么

| 领域 | 主要职责 | 现有文档 |
| --- | --- | --- |
| 阅读体验 | 作品展示、目录、选区、移动端布局与交互 | [阅读信息架构](../design/reading-information-architecture.md) |
| 作品与文献 | 作品身份、版本、出处、私有导入与公开发布；文献原文按卷则保留 | [作品数据库](corpus-database.md) · [文献库](document-corpus.md) |
| 证据与检索 | 查询外部资料、召回候选、回读原文、记录来源与失败 | [能力地图](agent-capability-map.md) · [诗句检索](text-retrieval.md) |
| 文学评论者 | Agent 如何选工具、解释证据；研究中的 Persona、Skills 与 Critic Notebook | [LangGraph](langgraph.md) · [Critic 研究](../research/critic-self-evolution.md) |
| 会话与个人数据 | 当前 Conversation、未来的账号与读者私人记忆 | [会话状态](conversation-state.md) |
| 评测与运行 | 自动测试、文学题回归、实际部署、调用记录和故障排查 | [开发指南](../development.md) · [部署](../deployment.md) |

这些是工作分工，不是六个实际团队，也不要求拆成六个服务。

## 已实现、正在研究、远期考虑

| 状态 | 范围 |
| --- | --- |
| **已在主线实现** | 3491 首公开阅读作品、私有到公开的白名单数据发布、ReAct 对话与 SSE、基础 CNKGraph 查询、诗句检索、浏览器本地会话。现有线上检索依赖 WSL 与 Tunnel 按需运行。 |
| **仅本地研究或实验** | Document Corpus 已在私人数据库导入六部文献并可选检索；CNKGraph 五项研究工具、DeepSeek Search/Fetch、萌典与维基文库工具虽已入代码，但默认关闭，尚未作为公开服务验收。相关效果与许可须分别核查。 |
| **待验证的产品功能** | 可独立阅读的词话文献、整首赏析使用研究工具、读者身份与服务端会话、词义和评论的离线审校、文学解释质量提升。是否施工按具体 Issue 和实测决定。 |
| **远期设想** | Critic 长期观点记忆、自主研究、共享审美积累、多产品拆分，以及可能需要的专门关系图谱。相关研究或独立原型不等于已经上线。 |

## 已经确认的边界

- **作品、检索结果与文献各有身份**：公开作品 UUID、诗句检索 Work ID、外部实体 ID、文献版本与卷则不能混用；外部结果不能覆盖本地作品正文。
- **原文与检索索引分开**：文献先有可回读的版本和章节，再由它生成检索块；诗句检索也不是通用古籍全文库。
- **找到资料不等于证明结论**：相似句不能直接定为化用，人物关联也要核对出处和含义。
- **私有资料与公开服务分开**：遵守 [ADR-0004](../adr/0004-private-public-corpus-boundary.md)；CNKGraph 非商业研究许可不能自动扩展为公开或商业使用。
- **Critic 与读者记忆分开**：Critic 的研究观点属于可修订的共享研究记录；个人对话、收藏和偏好应有独立归属、删除和访问控制。

本页从 [2026-10-18 架构现状盘点](../research/architecture-assessment-2026-10-18.md) 与 [架构依赖分析](../research/architecture-dependency-review-2026-10-18.md) 提取已经确认的原则。两份报告记录当时的调查状态，不再维护第二套实时任务清单。
