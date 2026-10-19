# Critic Notebook｜统一记忆原型（隔离实验）

> 状态：**研究原型**。任务与验收见 [#347](https://github.com/montricwang/poeticus/issues/347)，根本目标与阶段顺序见 [#311](https://github.com/montricwang/poeticus/issues/311)。本代码没有接入线上 Agent、生产 PostgreSQL、用户记忆或正式 Critic Persona，也没有完成真实模型/文学质量评测。

## 为什么不直接安装五套框架

Hindsight、LangMem、A-MEM、MemOS 与 PersMem 提供了各有价值的机制，但大多涉及独立的存取、检索或归纳逻辑。如果同时挂上自动保存/改写，会同时存在多份“当前记忆”，难以保证出处、权限、回滚和评测。我们只借鉴机制，**由一个 append-only Notebook 持有研究记录**，其他机制只能读它、产生候选建议，不能直接覆盖它。

| 参考研究 | 在 Poeticus 中借鉴的职责 | 首版进度 |
| --- | --- | --- |
| [Hindsight](https://github.com/vectorize-io/hindsight) | Retain → Recall → Reflect、事实与观点区分 | 追加事件、当前观点投影、只读整理；尚无模型反思 |
| [LangMem](https://github.com/langchain-ai/langmem) | 离线后台记忆提炼、合并、去重 | 可重建整理稿接口；尚无后台 Worker |
| [A-MEM](https://github.com/agiresearch/A-mem) | 札记之间的显式关联 | `related_claims`，尚无自动关联或向量索引 |
| [MemOS](https://github.com/MemTensor/MemOS) | 多层记忆与经验晋升 Skills | Candidate/Canonical 状态门禁；未自动晋升 Skills |
| [PersMem](https://arxiv.org/abs/2609.34372) | 人格/兴趣影响记忆注意力与召回 | 可选 `interest/surprise/uncertainty` 标注；**不参与**真实性判断或线上排序 |
| Event Sourcing | 修订不覆盖原纪录，投影可重建 | SQLite 追加表 + UPDATE/DELETE 禁止触发器 |

**归属**：Persona / Constitution 稳定且版本化；Skills 承担方法；Library 提供可验证的外部材料；Notebook 保存*Critic 自己*的候选解释和经过审阅的结论。用户记忆仍属于 #45，禁止互相写入。

## 原型的真正契约

`scripts/experiments/critic_memory.py` 使用 Python 标准库 + SQLite，读写由 `CriticNotebook` 管理。一个 SQLite 文件是一份隔离的 Critic 实验记忆，不预设 Web 应用迁移。

- **写入**：`propose(claim_id, ...)` → `challenge(claim_id, ...)` → `revise(claim_id, ..., sources=[...])` → `approve(claim_id, reviewer='human:...')`；如需撤回，用 `retract(claim_id, reason)`。所有动作追加新事件，保留原文和修订史。
- **读出**：`history(claim_id)` 回放完整经历；`current(claim_id)` 从事件推导最新状态；`recall(query)` 默认只召回已审阅观点，`include_candidates=True` 限实验诊断。
- **巩固**：`consolidate()` 生成**只读、确定性摘要草稿**和来源 event ID。这只是一份可输入后续 LLM 的投影，**不是 LLM 已经完成了语义压缩**；定时压缩、模型总结、去重和向量检索都尚未实现。
- **证据**：只接受 `library:` 与 `external:` 锚点；模型旧回答不能假扮独立证据。原型只能校验锚点格式，真正核验文献、版权和 reviewer 身份仍须上游执行。
- **防污染**：`approve` 要求有外部来源、已处理异议和 `human:` 或 `independent-eval:` 标签。此标签**不是鉴权系统**，线上/自动晋升在引入真实审计与权限前禁止。新修订使旧批准失效；撤回后不再参与当前召回。
- **情绪/兴趣**：`appraisal` 仅存分析信号，允许模型“惊讶”的评分影响下一次**候选**选题排序实验，但不能提高证据的可信度或直接修改 Persona。
- **可追溯性**：SQLite 触发器拒绝普通 UPDATE/DELETE；仍需系统级备份与文件权限，数据库拥有者可绕过触发器，**不能宣称具备区块链式防篡改安全**。

## 运行一个不依赖 LLM 的最小例子

```python
from scripts.experiments.critic_memory import CriticNotebook

memory = CriticNotebook("/path/to/private/critic-test.sqlite3")
memory.propose("jiang-kui", "初稿：过分相信王国维的一条批评")
memory.challenge("jiang-kui", "其他词作是否构成反例？")
memory.revise(
    "jiang-kui",
    "修订：这项批评只在限定的审美标准下成立",
    sources=["library:renjian-cihua/42"],
    related_claims=["wang-guowei"],
    appraisal={"surprise": 2},
)
memory.approve("jiang-kui", reviewer="human:editor")
print(memory.consolidate().text)  # 附带事件追溯 ID
```

```bash
python -m pytest tests/test_critic_memory_experiment.py -q
```

示例中的来源 ID 是格式演示，**不能作为已经核实的真实出处**。实际文献应用前先用 #341 的合法底本样本核对来源。

## 下一步（必须依靠实测）

1. 用 #341 的 3～5 段带出处文献建立至少两个相互冲突/可修订的观点案例，保留人工评审。
2. 引入可替换的 LangMem/Hindsight 式 *提炼 Worker*：它只生成带引用的 candidate + trace，不写 Canonical；比较“无巩固 / 定期巩固 / 有反例巩固”。
3. 再比较 FTS/向量召回、关联链接、兴趣权重是否提高对未见作品的解释质量，同时检查旧错误回灌、观点硬化和成本。
4. 若质量增益成立，才讨论按预算定期调度、稳定迁移、权限和线上只读集成。

本原型服务 #347 / #311 P2 研究；不取代 #311 P0（独立判断与文风）的近期交付。
