# Poeticus

**在诗词中阅读，也在诗词中追问。**

Poeticus 是一个面向中国古典诗词的 AI 辅助阅读器。读者可以在阅读作品时直接划选字句、提出问题，围绕原文展开连续讨论；不必为了查询一个典故或理解一处措辞而反复离开阅读页面。

**项目状态：v0.1.0 发布候选。** Railway 上的作品 API 已核实可以读取完整 **3491 首**宋词；当前网站仍处于受密码保护的只读预览阶段。匿名 AI 限流、使用预算、正式开放及 Release 正在验收，**尚未向所有读者开放**。

## 在线体验

正式 HTTPS 阅读网址将在安全和实际 AI 交互验收完成、临时访问门禁撤除后在这里公开。部署操作和当前验收进度见 [#76](https://github.com/montricwang/poeticus/issues/76)；现阶段的受控预览不作为公共发布入口。

## 阅读体验

- **3491 首宋词作品库**：从 PostgreSQL 读取真实宋词目录与正文，支持分页、词人/词牌检索和划词阅读；正文均保留 `imported_unreviewed` 状态，不冒充逐首人工校勘。
- **划词追问**：选中诗词中的字词或句子，将引用、作品信息和问题一起交给 AI。
- **连续讨论**：围绕同一作品保留最近几轮有效问答作为上下文；阅读历史和草稿在当前浏览器本地保存。
- **典故查证**：Agent 根据问题决定是否使用 CNKGraph 典故检索。检索结果是参考线索，不等于已经完成文献校勘。
- **整首赏析**：生成现代汉语译文、词语解释和作品赏析；AI 回答支持流式呈现。

Poeticus 尝试让**作品成为阅读中心，AI 成为可以随时交谈的伴读者**。界面仍在持续调整，见 [设计讨论 #63](https://github.com/montricwang/poeticus/issues/63)。

> 正式产品截图与无需口令的在线体验链接将在发布验收后补充；当前受控预览尚不是公开产品。

## 工程架构

| 层次 | 使用的技术 | 主要职责 |
| --- | --- | --- |
| 前端 | React、TypeScript、Vite | 作品阅读、划词引用、对话与流式展示 |
| HTTP 后端 | FastAPI、Pydantic | 作品查询、请求校验、聊天与赏析 API |
| AI 工作流 | LangGraph、LLM API | 结合作品上下文生成回答，按需调用查证工具 |
| 作品存储 | PostgreSQL、psycopg | 作品目录分页、正文读取、字段搜索 |
| 验证 | pytest、前端 lint/build、Node 测试 | 回归检查与数据处理验证 |

作品读取采用 `GET /api/poems` 与 `GET /api/poems/{UUID}`；聊天在正式部署中使用同源 `POST /api/chat/stream` SSE；FastAPI 同时提供 Vite 静态文件和作品 API。`GET /health` 用于存活检查，`GET /api/info` 返回非敏感版本元数据。公网 AI 使用量限制及故障保护见 [#77](https://github.com/montricwang/poeticus/issues/77)。

了解技术细节，可阅读 [LangGraph 架构](docs/architecture/langgraph.md)、[作品数据库架构](docs/architecture/corpus-database.md) 和 [开发日志](docs/devlog/)。

## 当前阶段与边界

- 当前以古典词作为主要阅读对象，仍有作品字段与文本尚待核对；不要将 AI 解释或检索候选视为可靠的校勘结论。
- 会话历史目前存储在**当前浏览器的 localStorage**，没有账号登录、跨设备同步或服务端长期记忆。
- 公开仓库不包含私有商业 EPUB、来源证据、批量抽取结果、数据库凭证或开发者的本地作品库。要运行数据库阅读功能，需自行准备具有使用权限的作品数据。
- 云端只含可供阅读的作品字段，不包括私人出版社注评和源书证据；所有内容仍应按具体版本追溯来源，未做逐首校勘。公开 AI 采用服务端请求配额与并发限制，不提供无限免费调用。
- 第一个公开演示版本的部署、访问限制和发布验收见 [#76](https://github.com/montricwang/poeticus/issues/76)、[#77](https://github.com/montricwang/poeticus/issues/77)、[#78](https://github.com/montricwang/poeticus/issues/78)。后续功能与缺陷由 [GitHub Issues](https://github.com/montricwang/poeticus/issues) 跟踪。

## 面向开发者

本地环境准备、运行命令、数据库初始化与自动化测试见 [开发者指南](docs/development.md)。首次正式发布前，此仓库仍可能存在尚未合并的 Draft PR；请以 `main` 和具体 Release 中的版本说明为准。
