"""LangGraph 执行路径日志。"""

import json
import logging
import time
import uuid
from functools import wraps
from typing import Callable


# 与 Uvicorn 使用同一个日志输出通道。
logger = logging.getLogger("uvicorn.error")


def log_event(
    trace_id: str,
    event: str,
    **fields,
) -> None:
    """记录结构化事件，不自动记录原诗、问题或证据全文。"""
    payload = {
        "trace_id": trace_id,
        "event": event,
        **fields,
    }

    logger.info(
        "poeticus.workflow %s",
        json.dumps(payload, ensure_ascii=False),
    )


def traced_node(name: str, node: Callable) -> Callable:
    """包装 Graph 节点，自动记录耗时及成功、失败状态。"""

    @wraps(node)
    def wrapped(state: dict) -> dict:
        trace_id = state.get("trace_id") or uuid.uuid4().hex[:12]
        started = time.perf_counter()

        # 把 trace_id 传给实际节点，供内部工具调用记录使用。
        node_state = {
            **state,
            "trace_id": trace_id,
        }

        try:
            result = node(node_state)
        except Exception as exc:
            log_event(
                trace_id,
                "node_finished",
                node=name,
                status="error",
                duration_ms=round(
                    (time.perf_counter() - started) * 1000,
                    1,
                ),
                error_type=type(exc).__name__,
            )
            raise

        result = {
            **result,
            "trace_id": trace_id,
        }

        log_event(
            trace_id,
            "node_finished",
            node=name,
            status="ok",
            duration_ms=round(
                (time.perf_counter() - started) * 1000,
                1,
            ),
            intent=result.get("intent") or state.get("intent"),
            next_step=result.get("next_step"),
            evidence_count=(
                len(result["evidences"]) if "evidences" in result else None
            ),
        )

        return result

    return wrapped
