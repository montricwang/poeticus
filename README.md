# Poeticus

**在诗词中阅读，也在诗词中追问。**

Poeticus 是一个面向中国古典诗词的 AI 辅助阅读器。读者可以在阅读作品时直接划选字句、提出问题，围绕原文展开连续讨论；不必为了查询一个典故或理解一处措辞而反复离开阅读页面。

**项目状态：v0.1.0 上线准备中。** 在线体验网址将在公网部署和安全验收完成后公布。当前仓库提供源代码、测试及架构文档，尚不是一个已开放的公共网站。

## 阅读体验

- **作品目录与检索**：从 PostgreSQL 读取作品目录和正文，按作品标识切换阅读；支持目录分页及作品字段检索。
- **划词追问**：选中诗词中的字词或句子，将引用、作品信息和问题一起交给 AI。
- **连续讨论**：围绕同一作品保留最近几轮有效问答作为上下文；阅读历史和草稿在当前浏览器本地保存。
- **典故查证**：Agent 根据问题决定是否使用 CNKGraph 典故检索。检索结果是参考线索，不等于已经完成文献校勘。
- **整首赏析**：生成现代汉语译文、词语解释和作品赏析；AI 回答支持流式呈现。

Poeticus 尝试让**作品成为阅读中心，AI 成为可以随时交谈的伴读者**。界面仍在持续调整，见 [设计讨论 #63](https://github.com/montricwang/poeticus/issues/63)。

> 产品截图和在线体验链接将在首版公开部署后补充；这里不提供未上线的演示地址。

## 工程架构

| 层次 | 使用的技术 | 主要职责 |
| --- | --- | --- |
| 前端 | React、TypeScript、Vite | 作品阅读、划词引用、对话与流式展示 |
| HTTP 后端 | FastAPI、Pydantic | 作品查询、请求校验、聊天与赏析 API |
| AI 工作流 | LangGraph、LLM API | 结合作品上下文生成回答，按需调用查证工具 |
| 作品存储 | PostgreSQL、psycopg | 作品目录分页、正文读取、字段搜索 |
| 验证 | pytest、前端 lint/build、Node 测试 | 回归检查与数据处理验证 |

作品读取采用 `GET /api/poems` 与 `GET /api/poems/{UUID}`；聊天使用 `POST /chat/stream` 提供 SSE。前端开发环境将该聊天入口代理为 `/api/chat/stream`；正式部署时需要配置生产环境的 HTTP 路由。服务状态与公开版本信息分别可通过 `GET /health`、`GET /api/info` 获取（正在部署分支中开发）。

了解技术细节，可阅读 [LangGraph 架构](docs/architecture/langgraph.md)、[作品数据库架构](docs/architecture/corpus-database.md) 和 [开发日志](docs/devlog/)。

## 当前阶段与边界

- 当前以古典词作为主要阅读对象，仍有作品字段与文本尚待核对；不要将 AI 解释或检索候选视为可靠的校勘结论。
- 会话历史目前存储在**当前浏览器的 localStorage**，没有账号登录、跨设备同步或服务端长期记忆。
- 公开仓库不包含私有商业 EPUB、来源证据、批量抽取结果、数据库凭证或开发者的本地作品库。要运行数据库阅读功能，需自行准备具有使用权限的作品数据。
- 第一个公开演示版本的部署、访问限制和发布验收见 [#76](https://github.com/montricwang/poeticus/issues/76)、[#77](https://github.com/montricwang/poeticus/issues/77)、[#78](https://github.com/montricwang/poeticus/issues/78)。后续功能与缺陷由 [GitHub Issues](https://github.com/montricwang/poeticus/issues) 跟踪。

## 面向开发者

本地环境准备、运行命令、数据库初始化与自动化测试见 [开发者指南](docs/development.md)。首次正式发布前，此仓库仍可能存在尚未合并的 Draft PR；请以 `main` 和具体 Release 中的版本说明为准。
