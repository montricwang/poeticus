# Critic Notebook：观点与工具经验原型

关联 [#347](https://github.com/montricwang/poeticus/issues/347)、[#407](https://github.com/montricwang/poeticus/issues/407) 与 [#148](https://github.com/montricwang/poeticus/issues/148)。

这个隔离实验复用 [PR #348](https://github.com/montricwang/poeticus/pull/348) 的 SQLite 追加事件设计。一次研究可以留下文学判断或工具选择经验；两种记录通过 `kind` 区分，不写入用户 Mem0。

- **写入**：`propose` → `challenge` / `revise` → `approve`，必要时 `retract`。撤回、被挑战或刚修订的记录不会进入默认召回；旧事件仍可追溯。
- **文学判断**：必须附 `library:` 或 `external:` 来源，审阅通过后才进入默认召回。
- **工具经验**：必须附 `trace:` 的可观察工具运行记录锚点，审阅通过后才进入默认召回；不能凭一次成功或模型自述直接推断工具普遍更好。
- **召回**：`recall(query, kind="literary")` / `recall(query, kind="tool")` 按关键字检索已批准记录。`consolidate(kind=...)` 生成带事件 ID 的确定性只读摘要。

示例（`trace:` 须在实际实验中对应真实记录）：

```python
from scripts.experiments.critic_memory import CriticNotebook

book = CriticNotebook("/path/to/private/critic.sqlite3")
book.propose(
    "tool:前代诗句查询",
    "明确询问诗句来源时先尝试前代诗句检索，再核对年代与上下文。",
    kind="tool",
    sources=["trace:eval-run-001"],
)
book.approve("tool:前代诗句查询", reviewer="human:reviewer")
assert book.recall("前代诗句", kind="tool")
```

运行：`python -m pytest tests/test_critic_memory_experiment.py -q`。

**本轮边界**：尚未接入线上 LangGraph、自动采集 Tool Trace、向量召回、自动提炼或 Persona 更新，也不替代用户私人记忆。来源锚点与审阅标签只校验格式，不能证明文献真实性或身份权限。下一步应选真实工具失败案例与未见文学问题，验证召回是否改善后续行为，而非增加中间提示词长度。
