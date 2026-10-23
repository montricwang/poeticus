# LangGraph Checkpointer 最小实验（Issue #46）

状态：**离线验证完成，未接入 Web 聊天生产路径**。实现见 `scripts/experiments/langgraph_checkpoint_spike.py` 和 `tests/test_langgraph_checkpoint_spike.py`。

## 为什么先做实验

当前 `backend/ai/graph.py` 的 `graph = builder.compile()` 没有 Checkpointer。每轮浏览器通过 `history` 传近期历史（登录态分支额外用 PostgreSQL 保存完整消息），LangGraph 只负责一次调用的临时 `AgentState`。这与 LangGraph `thread_id` 下可恢复的节点执行状态、Mem0 私人偏好、以及跨会话的 Store 是不同对象。

**不可直接给 Web 的 `builder.compile()` 添加 Checkpointer、并复用 `conversation_id` 作为 Thread ID。** 目前 Agent 首轮依赖 `state.get("messages")` 判断是否构造新消息，若同一 Thread 跨多次用户提问持续保存 `messages`，下一轮可能继承上次工具消息/回复，重用 `tool_count` 与 `reply`，与已有的前端 `history` 和服务端 SQL 消息形成第二套冲突状态。已有对话删除与访问权限，也没有覆盖 Graph Checkpoint。生产接入需要在确定 Run 语义、Thread 生命周期、授权和清理之后单独评估。

## 实验方法

- 使用当前**真实** `builder`：`agent → tools → agent`，不是重新写一个独立的演示 Graph。
- 使用 `langgraph-checkpoint-sqlite`（本地轻量存储）以及 `SqliteSaver.from_conn_string`；在脚本里启用 `LANGGRAPH_STRICT_MSGPACK=true`。
- 使用固定 Fake LLM 与 Fake Evidence Provider，不依赖付费 API、不访问用户私人数据或 PostgreSQL。
- 第一进程编译 `interrupt_before=["tools"]`，以稳定的**实验 Thread ID** 启动，持久化在工具节点前的完整状态。
- 第二进程重新加载脚本、SQLite 和 Graph，调用 `graph.invoke(None, config={"configurable":{"thread_id":...}})`，使用已保存的 State 继续工作。
- 检查 `get_state()`、`get_state_history()`、工具次数、回答、模型次数与另一 Thread 的隔离。

### 复现

```bash
cd ~/projects/poeticus-agent
../poeticus/.venv/bin/python -m pip install -r requirements-checkpoint-spike.txt

# 任选一个尚未存在的 /tmp 数据库路径（只放合成测试数据）
PYTHONPATH=. ../poeticus/.venv/bin/python -m scripts.experiments.langgraph_checkpoint_spike \
  --db /tmp/poeticus-checkpoint-demo.sqlite3 --stage pause
PYTHONPATH=. ../poeticus/.venv/bin/python -m scripts.experiments.langgraph_checkpoint_spike \
  --db /tmp/poeticus-checkpoint-demo.sqlite3 --stage resume

# 回归测试：使用独立临时 DB、两次独立 Python 进程
../poeticus/.venv/bin/python -m pytest -q tests/test_langgraph_checkpoint_spike.py
```

### 实际观测（2026-10-23）

第一次进程：

```json
{"stage":"pause","next":["tools"],"model_calls":1,"tool_calls":0,"history_depth":3}
```

重启后第二次进程：

```json
{
  "stage":"resume",
  "next":[],
  "model_calls":2,
  "tool_calls":1,
  "reply":"刘郎：用于验证工具节点之后可以从 SQLite 恢复。",
  "other_thread_isolated":true,
  "history_depth":5
}
```

`model_calls=2` 包括**当前恢复线程调用 1 次**和**另一隔离线程调用 1 次**。已保存的首轮 Agent 决策没有重跑；单次工具执行发生在恢复之后。检查点历史深度为 3→5，恢复后 `next=[]` 表示 Graph 结束。

这只证明**节点边界**上的恢复：暂停位置在 `tools` 前，恢复时 `tools` 执行一次。如果一个工具节点内部已调用外部服务、但尚未成功保存节点结果时崩溃，恢复后仍可能**再次调用该工具**。特别是未来有写入、副作用工具时，需要幂等键或补偿策略；Checkpointer 不提供任意 Python 指令级的续跑。

## 与下一阶段的边界

尚**未**实现：Web 的 `run_id`、浏览器 SSE 重连、断开后继续执行、持久的公开/登录用户 Thread 管理、独立数据库访问控制、私人记录删除时的 Checkpoint 清理、失败重试幂等、PostgreSQL 生产级 Checkpointer、Store。

下阶段如果确有需要，优先考虑：

1. 为每次生成分配与 Conversation ID 区分的稳定 **Run ID / Thread ID**，保证 Graph 的暂态不跨用户轮次污染；用户消息由 PostgreSQL 保持权威。
2. 确定用户删除 Conversation 时与其相关的 Checkpoint/Run 如何清理；匿名读者不应意外存储可识别内容。
3. 在独立受保护的环境选择 PostgreSQL Checkpointer 并验证持久化、故障恢复和并发；`setup()` 仅在批准的数据库中执行。
4. SSE 恢复需要服务器 Run 生命周期及可重订阅的输出；**仅编译 Checkpointer 不会自动实现刷新后继续生成**。

先以本次实验交付为止，不动 Mem0，也不直接部署到 Railway。
