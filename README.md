# Poeticus

**在诗词中阅读，也在诗词中追问。**

Poeticus 是一个面向中国古典诗词的 AI 辅助阅读器。读者可以在阅读作品时直接划选字句、提出问题，围绕原文展开连续讨论；不必为了查询一个典故或理解一处措辞而反复离开阅读页面。

**项目状态：v0.3.0 公网版。** 网站已面向访客开放，无需账号或自备 API Key；作品 API 的 **3491 首词作**已通过公网读取验收。AI 问答和赏析使用服务端共享的每日额度及限流保护。前代文本问题还可以调用 Poeticus 自建 Text Retrieval Service，从约 85 万首外部古典诗词中寻找候选来源。

## 在线体验

**[打开 Poeticus 在线阅读器](https://poeticus-web-production.up.railway.app/)**

直接打开即可搜索、阅读、划词提问或请求整首赏析。AI 使用免费体验额度，服务端设置全站每日请求上限；超额时仍可正常阅读作品。公开只读链路的 [GitHub Actions 外网验收记录](https://github.com/montricwang/poeticus/actions/runs/37176951820) 已通过。

## 阅读体验

- **3491 首公开词作**：从 PostgreSQL 读取目录与正文，支持分页、词人/词牌检索和划词阅读；当前数据包含晚唐、五代与宋代作者，正文均保留 `imported_unreviewed` 状态。
- **划词追问**：选中诗词中的字词或句子，将引用、作品信息和问题一起交给 AI。
- **连续讨论**：围绕同一作品保留最近几轮有效问答作为上下文；阅读历史和草稿在当前浏览器本地保存。
- **典故查证**：Agent 根据问题决定是否使用 CNKGraph 典故检索。检索结果是参考线索，需要继续结合原文判断。
- **前代文本检索**：询问“这句借了谁哪一句、可能化用了什么前代文本”时，Agent 可以调用自建 Hybrid Retrieval；候选由 Qwen sentence/clause Dense Retrieval、character n-gram BM25、Work-level RRF 与 chronology filtering 共同产生。
- **整首赏析**：生成现代汉语译文、词语解释和作品赏析；AI 回答支持流式呈现。

Poeticus 尝试让**作品成为阅读中心，AI 成为可以随时交谈的伴读者**。界面仍在持续调整，见 [设计讨论 #63](https://github.com/montricwang/poeticus/issues/63)。

> 作品库由历史材料整理，保留 `imported_unreviewed` 标识，并不表示已逐首校勘。模型生成的解释和译文可能有误，请结合原作阅读。

## 工程架构

| 层次 | 使用的技术 | 主要职责 |
| --- | --- | --- |
| 前端 | React、TypeScript、Vite | 作品阅读、划词引用、对话与流式展示 |
| HTTP 后端 | FastAPI、Pydantic | 作品查询、请求校验、聊天与赏析 API |
| AI 工作流 | LangGraph、LLM API | 结合作品上下文生成回答，按需调用查证与 Retrieval 工具 |
| 作品存储 | PostgreSQL、psycopg | 作品目录分页、正文读取、字段搜索 |
| Text Retrieval | Qwen3-Embedding、FAISS、SQLite FTS5 BM25、RRF | 从 Werneror 约 85 万首作品中发现前代文本候选 |
| Retrieval Serving | FastAPI、Nginx、systemd、腾讯云 2C8G | 独立承载模型与索引，通过 HTTPS + Bearer token 供 Railway Agent 调用 |
| 验证 | pytest、前端 lint/build、Node 测试、AI Eval、生产 E2E | 回归检查、检索增量验证与真实链路验收 |

作品读取采用 `GET /api/poems` 与 `GET /api/poems/{UUID}`；聊天在正式部署中使用同源 `POST /api/chat/stream` SSE；FastAPI 同时提供 Vite 静态文件和作品 API。`GET /health` 用于存活检查，`GET /api/info` 返回非敏感版本元数据。公网 AI 使用量限制及故障保护见 [#77](https://github.com/montricwang/poeticus/issues/77)。

文档按当前架构、决策、开发操作、私有数据和历史日志分工，先看 [文档导航](docs/README.md)。了解技术细节，可阅读 [LangGraph 架构](docs/architecture/langgraph.md)、[Text Retrieval 架构](docs/architecture/text-retrieval.md)、[作品数据库架构](docs/architecture/corpus-database.md)、[当前生产部署](docs/deployment.md) 和 [开发日志](docs/devlog/)。

后端实现统一位于 `backend/` 包：`app.py` 组装 FastAPI，`api/` 负责 HTTP 接口，`ai/` 放模型与 LangGraph，`corpus/` 管作品数据，`evidence/` 管典故查证。生产环境直接以 `backend.app:app` 启动，不再保留根目录兼容模块。

## 当前阶段与边界

- 当前以古典词作为主要阅读对象，仍有作品字段与文本尚待核对；AI 解释、典故候选和 Text Retrieval 候选都需要结合原文与可靠文献继续判断。
- 会话历史目前存储在**当前浏览器的 localStorage**，没有账号登录、跨设备同步或服务端长期记忆。
- 公开仓库不包含私有商业 EPUB、来源证据、批量抽取结果、数据库凭证或开发者的本地作品库。要运行数据库阅读功能，需自行准备具有使用权限的作品数据。
- 云端只含可供阅读的作品字段，不包括私人出版社注评和源书证据；所有内容仍应按具体版本追溯来源，未做逐首校勘。公开 AI 采用服务端请求配额与并发限制，不提供无限免费调用。
- 第一个公开演示版本的部署、访问限制和发布验收见 [#76](https://github.com/montricwang/poeticus/issues/76)、[#77](https://github.com/montricwang/poeticus/issues/77)、[#78](https://github.com/montricwang/poeticus/issues/78)。v0.3.0 的 Retrieval 生产链见 [#164](https://github.com/montricwang/poeticus/issues/164) 与 [PR #165](https://github.com/montricwang/poeticus/pull/165)。后续功能与缺陷由 [GitHub Issues](https://github.com/montricwang/poeticus/issues) 跟踪。

## 面向开发者

本地环境准备、运行命令、数据库初始化与自动化测试见 [开发者指南](docs/development.md)。正式版本以 `main` 和对应 GitHub Release 中的版本说明为准；其他 Draft PR 不等同于已发布功能。
