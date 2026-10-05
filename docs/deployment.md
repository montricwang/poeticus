# Poeticus｜当前生产部署

本文只描述 **当前有效** 的 Railway 生产结构和维护边界。首次上线、Basic Auth 预览、三首合成数据等历史过程已经结束；过程记录保留在 `docs/devlog/` 和 v0.1.0 Release 中。

## 生产结构

```text
Browser
   ↓ HTTPS
Railway poeticus-web
   ├─ FastAPI: backend.app:app
   ├─ frontend/dist
   ├─ /api/poems*
   ├─ /api/chat*
   ├─ /api/analyze
   └─ /health
          ↓
Railway PostgreSQL
```

截至 2026-10-05，`poeticus-web` 连接 GitHub `montricwang/poeticus` 的 `main` 分支，使用 Railpack，单副本运行并开启 sleep mode。

## Railway Web 配置

| 项目 | 当前值 |
| --- | --- |
| Source | `montricwang/poeticus` / `main` |
| Builder | Railpack |
| Build Command | `cd frontend && npm ci && npm run build` |
| Start Command | `uvicorn backend.app:app --host 0.0.0.0 --port $PORT` |
| Pre-deploy | `python -m scripts.corpus.db_import --migrate` |
| Healthcheck | `/health` |
| Frontend | FastAPI 同源提供 `frontend/dist` |

代码合并到 `main` 后由 Railway 自动构建部署。数据库 migration 在新版本启动前执行；已执行的 migration 文件不得改写。

## 配置来源

运行时配置遵循单向关系：

```text
Railway variables
      ↓
backend/config.py / server middleware
      ↓
FastAPI / Agent / LLM
      ↓
/api/capabilities
      ↓
browser（仅获得需要知道的非敏感契约）
```

Railway 保存部署环境的变量与秘密，例如：

- `LLM_API_KEY`
- `POETICUS_DATABASE_URL`
- `POETICUS_AI_IP_HASH_SECRET`
- AI 每日/每 IP/分钟/并发限额
- `POETICUS_LLM_MAX_OUTPUT_TOKENS`
- `POETICUS_SERVE_FRONTEND`
- `POETICUS_TRUST_RAILWAY_REAL_IP`

模型 Key、数据库 DSN、IP 哈希密钥和内部预算不得通过浏览器接口公开。`/api/capabilities` 只公开客户端需要遵守的聊天契约，例如历史轮数和输入长度。

## 作品数据

生产作品库目前包含 3491 首宋词，公开 Web 只读取阅读需要的 `poems` 字段。

私人数据链：

```text
private EPUB + glyph maps
        ↓
all_normalized.json
        ↓
private PostgreSQL
        ↓
scripts/corpus/public_corpus_transfer.py
        ↓
Railway PostgreSQL
```

公开迁移不上传私人 `poem_source_texts`、现代注评、源 EPUB 或本地检查报告。生产发布数据的详细边界见 [作品数据库架构](architecture/corpus-database.md)。

## AI 保护

匿名 AI 请求由服务端统一保护，包括：

- AI 总开关
- 请求体和字段长度限制
- 每 IP 分钟限制
- 每 IP 每日额度
- 全站每日额度
- 单实例并发限制
- LLM 输出 Token 上限
- Agent 工具调用预算
- 模型调用超时与零自动重试

这些限制是服务保护，不等于精确的人民币成本上限；供应商账户余额仍需独立控制。

## 部署后检查

影响运行时的合并至少检查：

1. Railway deployment 状态为 SUCCESS；
2. `GET /health` 返回 200；
3. 首页和 `GET /api/poems` 可读取；
4. 涉及聊天时验证 `/api/chat/stream` SSE；
5. 涉及数据库时确认 migration 和作品总数；
6. 不在日志、截图或文档中暴露 DSN、API Key 或私人语料。

普通文档修改不需要人为重建数据库；只有 migration、数据迁移或部署配置变化才打开对应层。
