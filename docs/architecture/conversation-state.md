# Poeticus：Conversation State 与持久化

## 1. 产品模型

Poeticus 采用 **Poem-first** 的产品模型：

> **Poem 是主要领域对象；Conversation 是围绕阅读发生的上下文；Chat 是进入诗歌世界的一种交互方式。**

因此，不把产品默认建模为“通用 ChatGPT + 诗歌 Prompt”。未来的 Poem、Poet、Collection、Comparison 等阅读对象都可以成为一等领域对象。

## 2. Conversation 与存储实现解耦

Conversation 是产品领域对象，localStorage、数据库只是它的不同持久化实现。

```mermaid
flowchart LR
    A["Poem / Reading Context"] --> B["Conversation"]
    B --> C["Messages / Turns"]
    B --> D["Draft / Selection"]

    B -. v0.1 .-> E["localStorage adapter"]
    B -. future .-> F["Conversation API"]
    F --> G["PostgreSQL"]
```

v0.1 暂不引入数据库、账号或服务端 Thread。浏览器 localStorage 只是当前 persistence adapter，不应反过来决定长期领域模型。

## 3. v0.1：每首诗恢复当前 Conversation

当前 UI 每首诗只暴露一场“当前 Conversation”，但存储中保留独立的 `conversationId`，为未来一首诗多个 Conversation 留出迁移空间。

```text
Poem A
└── Current Conversation A1

Poem B
└── Current Conversation B1
```

不同诗歌的状态彼此隔离：

- 从 A 切到 B，再回到 A，应恢复 A 原来的聊天和草稿；
- 刷新页面后，应恢复刷新前所在的作品与该作品当前 Conversation；
- 不自动把不同诗歌的聊天历史合并进模型 Context。

## 4. 本地持久化内容

v0.1 保存：

- `schemaVersion`
- 上次打开的 `poemId`
- `conversationId`
- `poemId`
- 稳定的聊天 Turn 数据
- 未发送的输入草稿
- 草稿关联的原文 Selection
- `updatedAt`

不持久化纯运行时 UI 状态，例如：

- loading
- scrollTop
- unread badge
- regenerate 临时草稿
- 正在进行中的网络连接

## 5. 正在生成时刷新

Poeticus v0.1 的生成任务仍依赖当前浏览器到 FastAPI 的 SSE 请求，没有服务端 Run persistence 或可重连流。

因此，刷新页面时：

- 已完成回答正常恢复；
- pending / streaming Turn 恢复为“生成中断，可重试”；
- regenerate 中途刷新时保留旧的成功答案，不把临时新草稿当成正式答案。

这是 **v0.1 的降级策略**，不是最终产品原则。未来若需要“刷新后继续原生成”，应实现独立的 resumable generation 能力：服务端 Run ID、生成状态持久化和重新订阅。

## 6. 与模型上下文的区别

产品侧 Conversation 持久化和模型实际看到的 Context 是两个问题。

当前模型上下文采用 #9 的 bounded history：

```text
Conversation turns
        ↓
筛选最近已完成 Turn
        ↓
system + history + current user
        ↓
ReAct Agent
```

localStorage 可以保存更多历史，但模型仍只接收受预算约束的近期有效历史。

## 7. 后续演进

- #44：一首诗多个 Conversation，新建 / 切换 / 删除会话
- #40：将 Conversation persistence 迁移到服务端
- #45：跨 Conversation 的长期记忆与历史召回
- #43：显式的跨作品比较 / 多诗 Context
- #41：Conversation state & memory 的长期架构演进记录
