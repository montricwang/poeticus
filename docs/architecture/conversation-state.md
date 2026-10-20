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

v0.1 的**会话层**暂不引入服务端数据库、账号或 Thread persistence；作品库本身已经使用 PostgreSQL。浏览器 localStorage 只是当前 Conversation persistence adapter，不应反过来决定长期领域模型。

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

这是 **v0.1 的降级策略**，不是最终产品原则。未来若需要“刷新后继续原生成”，应实现独立的 resumable generation 能力：服务端 Run ID、生成状态持久化和重新订阅，见 #46。

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
- #46：刷新后的可恢复生成
- #41：Conversation state & memory 的长期架构演进记录

## 8. 多入口 Conversation 的设计契约（规划，尚未实现）

首页的自由文学探索和单首作品伴读可以共用 Conversation 领域模型，**但默认上下文不同**：

- **首页探索**：用户不必先选一首词；新讨论不自动绑定上一首正在阅读的作品。
- **作品伴读**：新讨论默认拥有当前 `poem_id` 与用户明确引用的原文；切换作品不自动合并不同会话的消息。
- **跨作品比较**：未来由用户显式选择参与比较的作品及上下文；不能靠拼接两场旧聊天冒充已选择的作品证据。
- **会话生命周期**：Conversation 有稳定 ID；新建不等于清空旧会话，删除也不等于复用旧 ID。历史重新生成若改变较早的答案，须明确定义后续轮次的截断、失败保留和引用快照的行为。
- **数据责任分开**：浏览器保存的当前草稿、服务端私人历史、模型当轮可见的 bounded history、跨会话用户记忆以及用户主动收藏的札记各有不同生命周期。删除某场 Conversation 不应隐式删除独立收藏；用户级存储必须在服务端校验身份。

这些是后续交付时应保护的目标契约，**不是当前 `localStorage` 原型已经实现的能力**。当前状态见上文；实施与验收由 [#44](https://github.com/montricwang/poeticus/issues/44) 及相关子任务承担。入口与导航关系另见[阅读信息架构](../design/reading-information-architecture.md)。
