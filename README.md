# Poeticus

**在诗词中阅读，也在诗词中追问。**

Poeticus 是一款面向中国古典诗词的 AI 辅助阅读器。读者可以从一首词出发，阅读原文、查找作品、划词提问，也可以与 AI 讨论典故、措辞和作品之间的联系。

**[在线体验 poeticus.app](https://poeticus.app/)** · [最新版本](https://github.com/montricwang/poeticus/releases/latest)

## 阅读体验

- **每日一词**：每天从 3491 首公开词作中推荐一首，以竖排呈现，点击即可进入阅读室。
- **馆藏阅读**：按词人、词牌或诗句搜索；阅读页提供逐句排版、前后首切换，以及适配手机和桌面的布局与深浅主题。
- **对话伴读**：划选词句直接提问，围绕当前作品连续讨论，也可以生成整首词的译文、词语解释与赏析。
- **文学线索**：AI 可以按需查询典故，并在约 85 万首古典诗词构成的检索库中寻找可能的前代文本联系，供进一步阅读和辨析。

阅读库目前以词作为主，包含晚唐、五代及宋代等时期的作者。作品尚未逐首人工校勘；AI 生成的解释与检索候选也需要结合原文和文献判断。

## 技术架构

Poeticus 使用 React、TypeScript 和 Vite 构建前端，FastAPI 提供作品、对话及赏析接口，PostgreSQL 保存公开阅读作品。AI 伴读由 LangGraph 组织模型调用与查证工具。

前代文本检索使用 Qwen3-Embedding、FAISS 和 SQLite FTS5/BM25 进行混合召回，再按作品汇总候选。检索服务当前运行在开发机 WSL，通过 Cloudflare Tunnel 按需连接线上应用；检索节点离线时，该项能力会受影响。网站及公开作品库部署在 Railway。

## 开发与文档

项目代码与文档公开，作品数据库的私人原始资料及凭据不包含在仓库中。自行运行阅读功能需要准备具有使用权限的作品数据；在线体验无需账号，AI 功能设有共享用量限制。

- [开发者指南](docs/development.md)：环境准备、启动和测试
- [架构与文档导航](docs/README.md)：系统结构、数据和设计决策
- [生产部署](docs/deployment.md)：线上服务与检索节点
- [版本记录](https://github.com/montricwang/poeticus/releases) · [开发日志](docs/devlog/) · [问题与计划](https://github.com/montricwang/poeticus/issues)
