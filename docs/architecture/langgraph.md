# Poeticus：LangGraph Agent 架构

## 1. 当前模型

Poeticus 的聊天工作流定义在 `backend/ai/graph.py`，`langgraph.json` 直接指向 `backend/ai/graph.py:graph`。

当前使用 ReAct 式循环：模型根据当前作品、作品元数据、用户选区、近期对话和问题，决定直接回答或调用外部工具。系统不再使用固定 Intent Router。

```mermaid
flowchart TD
    A["START：作品 + 历史 + 当前问题"] --> B["agent"]
    B --> C{"tool_calls?"}
    C -->|否| D["reply → END"]
    C -->|是| E["tools"]
    E --> F["追加 tool 结果"]
    F --> B
```

## 2. Agent

首次进入 `agent` 时，系统组合：

1. system prompt；
2. 前端携带、后端已经校验的 bounded history；
3. 当前作品上下文、选区和问题。

之后的 Agent 轮次沿用本次请求的 `messages`，其中包含工具调用与工具返回。

模型、输出 Token 预算和工具调用预算都来自后端统一配置。当前单次用户请求最多执行 **2 次实际工具调用**；达到预算后不再允许新的真实工具执行。

## 3. 工具与 Evidence

当前 Agent 可见三类工具：

- `lookup_allusion`：人物故事、掌故、神话与典故性短语；
- `lookup_reference`：外部 reference evidence；
- `search_predecessor_texts`：Poeticus 自建 Corpus 的前代文本候选检索。

`search_predecessor_texts` 只有在 Retrieval URL 已配置时才注册。它通过 `TextRetrievalClient` 调用独立 Retrieval Service；当前作品正文、作者、题名和可用 dynasty 由 host application 注入，模型只决定检索文本。

用户明确追问“借了谁哪一句 / 化用了哪段前代文本”时，Agent 优先使用 `search_predecessor_texts`。第一轮结果弱时，可以在当前 2 次工具预算内换一个更有辨识度的文本锚点继续检索。

工具返回可以是：

- `ok`
- `no_hit`
- `error`
- `budget_exceeded`

候选资料只是回答材料，不自动等于已经完成文献校勘。外部文本进入后续模型调用前会做长度限制。

Text Retrieval 返回的 chronology status 也只是粗粒度信号。Werneror 的 dynasty label 会把部分五代人物标成“唐”；Agent 不能把它直接表述成精确历史断代。

当前已验证的产品路径：

```text
textual provenance question
→ search_predecessor_texts
→ first corpus result
→ 必要时 query reformulation
→ second corpus retrieval
→ candidate evidence
→ final answer
```

陆游“片片轻鸥落晚沙”已经完成真实线上 E2E：Retriever 在 `dynasty=null` 的请求下召回杜甫“片片轻鸥下急湍”，Agent 最终采用该证据，并保留“文本对应很强 / 缺少明确引用记载”的不确定性边界。

## 4. Graph State

`RouterState` 的主要字段：

| 字段 | 用途 |
| --- | --- |
| `poem` / `question` | 当前原文和问题 |
| `selection` / `context` | 可选选区与作品元数据 |
| `history` | 此轮之前的短期 user / assistant 历史 |
| `messages` | 当前一次 Agent 执行内部消息 |
| `tool_calls` / `tool_results` | 当前工具请求与最近结果 |
| `tool_count` | 已执行工具数量 |
| `evidences` | 累计候选证据 |
| `reply` | 最终回答 |
| `stream_reply` | 是否使用流式模型调用 |

`history` 与 `messages` 不是同一层：前者跨用户轮次，由客户端携带；后者只服务当前这一次 Graph 执行。

## 5. HTTP 与流式输出

公开聊天入口：

- `POST /api/chat` → `graph.invoke()`
- `POST /api/chat/stream` → `graph.stream()`

开发代理兼容的无 `/api` 路径仍由 FastAPI 路由支持，但项目内部 Python 模块不再保留根目录兼容入口。

流式模式使用 LangGraph `custom` 事件传正文 token，用 `updates` 获取节点结果。FastAPI 转为 SSE：

- `token`
- `done`
- `error`

如果模型在工具调用前先输出说明文字，这部分可能先显示；工具完成后的正式回答以新的 token 段继续输出。API 会校验最终正式回答与 Graph 的 `reply` 一致。

## 6. 会话边界

浏览器可以保存比模型实际看到的更多历史。发送请求时，前端从 `/api/capabilities` 获取后端声明的最大历史轮数，再只发送最近已完成 Turn；后端仍做最终校验。

服务端目前没有长期 Conversation persistence、跨设备同步或可恢复 Run。详情见 [conversation-state.md](conversation-state.md)。
