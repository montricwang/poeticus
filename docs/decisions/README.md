# Engineering Decision Register

这个目录记录 Poeticus 中**会影响架构、产品行为、资源成本或后续实验解释**的工程决策。

它不替代：

- `docs/architecture/*`：记录当前系统是什么；
- GitHub Issue：记录问题、任务、验收和后续工作；
- `docs/devlog/*`：记录当天发生了什么；
- PR：记录具体代码变更。

Decision Register 只回答另一组问题：

> **为什么当时这样选？当时证据有多强？是谁先提出的？什么情况出现时应该重新审视？**

这样可以避免一个临时默认值在代码里活久了以后，被误认为“这是经过充分论证的架构原则”。

## 四层证据分类

### Level 1 — Evidence-backed

已有真实产品 Case、Benchmark、故障、数据或明确外部约束支持。

可以作为当前基线，但仍然允许在环境变化后重审。

### Level 2 — Reasonable but unproven

有清楚的工程理由，也符合当前约束，但还没有足够真实数据证明它优于替代方案。

应明确写出验证条件。

### Level 3 — Working default

为了让闭环先跑起来而选择的参数、阈值、容量、超时、缓存大小或实现细节。

这类决定**尤其不能因为写进代码就自动升级成架构事实**。

### Level 4 — Open / unresolved

已经暴露问题或存在多个合理方向，当前证据不足，不应静默选择一个方案并把它冻结。

## Origin

每条重要决策同时记录来源：

- `user-directed`：用户明确指定；
- `AI-proposed`：AI 在实现或讨论中首先提出；
- `joint`：双方讨论后共同收敛；
- `inherited`：来自已有代码、库默认或历史实现，当前只是继续沿用。

`AI-proposed` 不表示决定错误，也不表示用户没有接受；它只是让未来复盘时知道这个选择最初不是由用户主动提出。

## 建议字段

| 字段 | 含义 |
| --- | --- |
| Decision | 当时实际选择了什么 |
| Level | 1–4 |
| Origin | 谁首先提出 / 从哪里继承 |
| Why | 当时为什么这样选 |
| Evidence | 当时已有的事实或数据 |
| Status | active / superseded / experiment / open |
| Re-review trigger | 什么情况出现时应该重新讨论 |
| References | Issue / PR / Eval / Benchmark |

## 记录边界

不是每一次函数命名、变量命名都需要进入 Decision Register。

优先记录：

- 会明显改变产品行为；
- 会改变资源 / 部署成本；
- 会改变数据语义；
- 会使后续某条路线更容易或更难；
- 有多个合理方案，而当前只是选了其中一个；
- AI 在推进实现时自行补上的非显然默认值。

原则：

> **架构文档保存当前真相；Decision Register 保存当前真相是怎样变成现在这样的。**
