"""离线 Critic Notebook 原型：追加事件为真，当前观点与摘要只是可重建投影。

仅供实验目录调用；不能直接接入线上 Agent 或用户长期记忆。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ClaimSnapshot:
    """由事件历史重建的当前观点状态，不是另一份权威记录。"""

    claim_id: str
    content: str
    state: str
    sources: tuple[str, ...]
    related_claims: tuple[str, ...]
    last_event_id: int


@dataclass(frozen=True)
class ConsolidationDraft:
    """只读、带回溯线索的整理稿；未经审阅不能成为 Canonical Notebook。"""

    text: str
    contributing_events: tuple[int, ...]


class CriticNotebook:
    """每个实例只负责一个隔离的 Critic 实验数据库。

    source anchors 只接受 library:/external: 引用；真实出处、权限和审校由调用方保证。
    reviewer 是审阅来源标签，不是鉴权系统；本原型不提供生产晋升接口。
    """

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS critic_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    claim_id TEXT NOT NULL,
                    action TEXT NOT NULL CHECK (
                        action IN ('propose', 'challenge', 'revise', 'approve', 'retract')
                    ),
                    content TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    related_json TEXT NOT NULL,
                    appraisal_json TEXT NOT NULL,
                    reviewer TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_critic_claim
                    ON critic_events(claim_id, id);
                CREATE TRIGGER IF NOT EXISTS critic_events_no_update
                    BEFORE UPDATE ON critic_events
                    BEGIN SELECT RAISE(ABORT, 'critic events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS critic_events_no_delete
                    BEFORE DELETE ON critic_events
                    BEGIN SELECT RAISE(ABORT, 'critic events are append-only'); END;
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _text(value: str, field: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"{field} must not be empty")
        return value

    @classmethod
    def _sources(cls, refs: Sequence[str]) -> tuple[str, ...]:
        result = tuple(cls._text(ref, "source") for ref in refs)
        if any(not ref.startswith(("library:", "external:")) for ref in result):
            raise ValueError("sources must reference external Library material")
        return result

    @staticmethod
    def _appraisal(scores: Mapping[str, int] | None) -> dict[str, int]:
        """认知重要性标注仅用于未来检索 A/B；不决定证据真假或晋升。"""
        result = dict(scores or {})
        if any(
            key not in {"interest", "surprise", "uncertainty"}
            or type(value) is not int
            or not 0 <= value <= 3
            for key, value in result.items()
        ):
            raise ValueError("appraisal scores must be integers between 0 and 3")
        return result

    def _append(
        self,
        claim_id: str,
        action: str,
        content: str,
        sources: Sequence[str] = (),
        related_claims: Sequence[str] = (),
        appraisal: Mapping[str, int] | None = None,
        reviewer: str = "",
    ) -> int:
        claim_id = self._text(claim_id, "claim_id")
        content = self._text(content, "content")
        refs = self._sources(sources)
        relations = tuple(self._text(item, "related claim") for item in related_claims)
        signals = self._appraisal(appraisal)
        with self._connect() as db:
            cursor = db.execute(
                """INSERT INTO critic_events
                (claim_id, action, content, sources_json, related_json,
                 appraisal_json, reviewer) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    claim_id,
                    action,
                    content,
                    json.dumps(refs, ensure_ascii=False),
                    json.dumps(relations, ensure_ascii=False),
                    json.dumps(signals),
                    reviewer,
                ),
            )
            assert cursor.lastrowid is not None
            return cursor.lastrowid

    def history(self, claim_id: str) -> list[dict[str, object]]:
        claim_id = self._text(claim_id, "claim_id")
        with self._connect() as db:
            rows = db.execute(
                """SELECT * FROM critic_events WHERE claim_id = ?
                   ORDER BY id""",
                (claim_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "action": row["action"],
                "content": row["content"],
                "sources": tuple(json.loads(row["sources_json"])),
                "related_claims": tuple(json.loads(row["related_json"])),
                "appraisal": json.loads(row["appraisal_json"]),
                "reviewer": row["reviewer"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def current(self, claim_id: str) -> ClaimSnapshot | None:
        events = self.history(claim_id)
        if not events:
            return None
        content = ""
        state = "candidate"
        sources: tuple[str, ...] = ()
        related: tuple[str, ...] = ()
        for event in events:
            action = event["action"]
            if action in {"propose", "revise"}:
                content = str(event["content"])
                sources = event["sources"]  # type: ignore[assignment]
                related = event["related_claims"]  # type: ignore[assignment]
                state = "candidate"
            elif action == "challenge":
                state = "contested"
            elif action == "approve":
                state = "canonical"
            elif action == "retract":
                state = "retracted"
        return ClaimSnapshot(
            claim_id=claim_id,
            content=content,
            state=state,
            sources=sources,
            related_claims=related,
            last_event_id=int(str(events[-1]["id"])),
        )

    def propose(
        self,
        claim_id: str,
        content: str,
        *,
        sources: Sequence[str] = (),
        related_claims: Sequence[str] = (),
        appraisal: Mapping[str, int] | None = None,
    ) -> int:
        if self.current(claim_id) is not None:
            raise ValueError("claim already exists; revise its history instead")
        return self._append(claim_id, "propose", content, sources, related_claims, appraisal)

    def challenge(self, claim_id: str, objection: str) -> int:
        snapshot = self.current(claim_id)
        if snapshot is None or snapshot.state == "retracted":
            raise ValueError("no active claim to challenge")
        return self._append(claim_id, "challenge", objection)

    def revise(
        self,
        claim_id: str,
        content: str,
        *,
        sources: Sequence[str] = (),
        related_claims: Sequence[str] = (),
        appraisal: Mapping[str, int] | None = None,
    ) -> int:
        if self.current(claim_id) is None:
            raise ValueError("claim must be proposed before revising")
        return self._append(claim_id, "revise", content, sources, related_claims, appraisal)

    def approve(self, claim_id: str, *, reviewer: str) -> int:
        """受控人工/独立评测确认；缺来源或存在未处理异议则拒绝。"""
        snapshot = self.current(claim_id)
        if snapshot is None or snapshot.state != "candidate" or not snapshot.sources:
            raise ValueError("only sourced, unchallenged candidates may be approved")
        if not reviewer.startswith(("human:", "independent-eval:")) or not reviewer.split(":", 1)[1].strip():
            raise ValueError("reviewer must identify an external review origin")
        return self._append(
            claim_id, "approve", snapshot.content,
            snapshot.sources, snapshot.related_claims, reviewer=reviewer,
        )

    def retract(self, claim_id: str, reason: str) -> int:
        if self.current(claim_id) is None:
            raise ValueError("claim does not exist")
        return self._append(claim_id, "retract", reason)

    def snapshots(self) -> list[ClaimSnapshot]:
        with self._connect() as db:
            ids = [row["claim_id"] for row in db.execute(
                "SELECT DISTINCT claim_id FROM critic_events ORDER BY claim_id"
            )]
        return [snapshot for claim_id in ids if (snapshot := self.current(claim_id))]

    def recall(
        self, query: str, *, include_candidates: bool = False, limit: int = 5,
    ) -> list[ClaimSnapshot]:
        """最小词面检索；默认仅使用审阅过的当前观点，不检索历史废案。"""
        if limit < 1:
            raise ValueError("limit must be positive")
        keyword = self._text(query, "query").casefold()
        return [
            item for item in self.snapshots()
            if (item.state == "canonical" or
                (include_candidates and item.state in {"candidate", "contested"}))
            and (keyword in item.content.casefold() or keyword in item.claim_id.casefold())
        ][:limit]

    def consolidate(self, *, include_candidates: bool = False) -> ConsolidationDraft:
        """从事件重建只读摘要：可喂给 LLM 起草，结果本身不写回为证据。"""
        selected = [
            item for item in self.snapshots()
            if item.state == "canonical" or (
                include_candidates and item.state in {"candidate", "contested"}
            )
        ]
        lines = [
            f"[{item.state}] {item.claim_id} @event:{item.last_event_id}: "
            f"{item.content} | evidence={','.join(item.sources) or 'unverified'}"
            for item in selected
        ]
        return ConsolidationDraft(
            text="\n".join(lines),
            contributing_events=tuple(item.last_event_id for item in selected),
        )
