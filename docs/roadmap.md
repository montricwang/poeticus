# Poeticus Roadmap

> 更新日期：2026-10-06  
> 当前状态：`v0.2.0` 已公开发布；当前 main 已进一步加入响应式阅读体验、Seed AI Eval baseline、Agent Process Trace，以及典故 / 出处两类 Evidence Tool。

Roadmap 只记录**下一阶段方向**。已经完成的发布过程不再混在未来计划里；具体任务和验收进入 GitHub Issues。

## 1. 当前基线

Poeticus 已经走通：

- React / TypeScript / Vite 阅读界面；
- FastAPI 同源后端；
- PostgreSQL 作品库与 3491 首宋词；
- 私人 EPUB → JSON → 私人 DB → 公网 DB 的数据链；
- LangGraph ReAct Agent；
- CNKGraph 典故工具；
- bounded multi-turn context；
- SSE 流式回答；
- localStorage Conversation persistence；
- Railway 公网部署；
- Python、前端 build/lint 和 Node 回归测试；
- 匿名 AI 的限额、并发和预算保护。

因此后续不再把“是否要引入 PostgreSQL”“是否要做多轮”等已完成事项当作未来目标。

## 2. 近期优先级

### 2.1 Corpus quality

当前最大的事实风险不是“作品数量不够”，而是 `imported_unreviewed` 数据质量。

近期重点：

- 修复已经发现的 EPUB 结构误判；
- 为小序、注释、寓声、缺文等边界补回归样本；
- 保持可重建的数据链；
- 逐步建立 curated/editorial correction 与原始抽取之间的明确边界。

原则仍是：

> 找到第一层错误数据就停在那里修，不跨层打补丁。

### 2.2 Evidence / RAG

当前已有两类 CNKGraph Evidence Tool：

- `lookup_allusion`：人物、故事、典故性短语；
- `lookup_reference`：前代成句、近似文本、改写与拆取重组候选。

Seed Eval 已确认它们具有互补性，也确认了共同边界：高度压缩、反用、翻案和大幅重组仍可能无法稳定检索。

下一阶段优先做 [#119 Text Retrieval / BERT-CCPoem Retrieval Benchmark](https://github.com/montricwang/poeticus/issues/119)，先回答“embedding retrieval 到底能补多少”，再决定是否建设正式 RAG。候选资料仍包括可靠注释、词话与历代评论、作者编年 / 生平资料和可追溯的作品出处。

需要实际回答：

- 什么问题应该走 allusion、reference 或未来的 text retrieval；
- 候选库、chunk 和 metadata 如何设计；
- 正确来源在 Top-1 / Top-5 / Top-20 的位置；
- 如何保留出处、处理未命中和冲突证据；
- retrieval 是否真的改善回答，而不是只增加复杂度。

### 2.3 Evaluation

第一轮 Seed AI Eval baseline 已完成，并实际用于：

- 对比 `control_no_tools` 与 `current_agent`；
- 发现并修复 Tool budget 后的协议泄漏；
- 增加 Tool Call / Tool Result / Evidence 的 Process Trace；
- 发现 Routing 缺陷与 Tool 能力边界；
- 复核并修正一条错误 Ground Truth；
- 验证 `lookup_reference` 对近似成句检索的增量。

下一阶段不继续为了固定 Case 调 Prompt。保留小而稳定的 Core Set，并在真实失败、模型 / Prompt / Retrieval 变化时做回归。未来若需要“裸基模 → Poeticus Prompt → Agent + Tool”的严格对照，再单独设计受控实验。

单元测试、AI Eval、Trace 和真实浏览器验收继续分层，不互相冒充。

### 2.4 UX reliability

已发布后的体验问题以 Issue 为准，例如：

- 移动端与窄屏；
- iOS 选区行为；
- Conversation 交互；
- SSE 中断与失败恢复；
- 长对话的可读性。

这类问题按真实用户路径修，不为了“重构漂亮”提前扩张。

## 3. 中期方向

### Conversation

当前 Conversation 存在浏览器 localStorage。只有当出现明确需求时，再考虑：

- 一首作品多个 Conversation；
- 服务端 Conversation persistence；
- 跨设备同步；
- resumable generation；
- 跨作品比较；
- 长期记忆。

### Skills

如果把文学分析拆成 Skill，需要有真实不同的输入、数据依赖和验证方式，而不是简单增加几个 Prompt 文件。

可能的方向：

- 文本/章法分析；
- 典故与 Evidence；
- 知人论世；
- 多作品比较。

### Engineering spikes

MCP、Reranker、Hybrid Search、Redis、Checkpointer 等可以做短期 Spike，但进入主线前必须回答“它解决 Poeticus 的哪个真实问题”。

当前已知低优先级优化：

- [#120 避免同一轮 Agent 重复执行相同 Tool Call](https://github.com/montricwang/poeticus/issues/120)：属于效率与 Tool budget 稳健性问题，不阻塞现有正确性。

## 4. 求职与学习目标

一个技术点准备写进简历前，至少满足：

> 做过 → 遇到过问题 → 能解释为什么这样做，以及没有这样做会怎样。

Poeticus 的价值不是覆盖最多名词，而是用一个真实产品贯穿：

```text
Frontend
   ↓
API / Validation
   ↓
Agent / LLM / Tool
   ↓
Evidence
   ↓
PostgreSQL / Data Pipeline
   ↓
Deployment / Observability / Evaluation
```

## 5. 停止线

每个阶段只打开当前真正需要的一层：

1. 明确问题；
2. 做最小真实闭环；
3. 运行并观察；
4. 记录取舍；
5. 再决定是否深入。

当前不追求把 Poeticus 变成“什么都有”的平台。优先保持现有闭环可信、可解释、可维护。
