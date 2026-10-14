"""Poem Retrieval 的只读组诗拼接关系检查。

关系只来自离线已验证的完整串接。不同作者或不同作品身份不得靠
标题和语义向量推测；没有加载该快照时保持现有 Retrieval 行为。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Collection, Protocol, Sequence, TypeVar


class CandidateWithWorkId(Protocol):
    @property
    def work_id(self) -> str: ...

    @property
    def text(self) -> str: ...


CandidateT = TypeVar("CandidateT", bound=CandidateWithWorkId)


def _same_hit(left: str, right: str) -> bool:
    a = "".join(left.split())
    b = "".join(right.split())
    return len(a) >= 6 and len(b) >= 6 and (a in b or b in a)


class WorkCompositionLookup:
    """使用独立 SQLite 快照做两次 indexed lookup，不读取全文或改变索引。"""

    def __init__(self, db_path: Path, *, work_sha256: str):
        self.path = db_path.expanduser().resolve()
        manifest_path = self.path.with_name("work_compositions_manifest.json")
        if not self.path.is_file() or not manifest_path.is_file():
            raise ValueError(f"组诗关系快照或 manifest 不存在：{self.path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("corpus_sha256") != work_sha256:
            raise ValueError("组诗关系快照与当前 Serving Corpus SHA-256 不匹配")
        with self._connect() as db:
            count = db.execute("SELECT COUNT(*) FROM work_compositions").fetchone()[0]
        if count != manifest.get("relation_rows"):
            raise ValueError("组诗关系表行数与 manifest 不匹配")
        self.relation_rows = count

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")
        return conn

    @staticmethod
    def _query_pairs(db: sqlite3.Connection, sql: str, values: set[str]) -> set[tuple[str, str]]:
        if not values:
            return set()
        placeholders = ",".join("?" for _ in values)
        rows = db.execute(sql.format(placeholders=placeholders), sorted(values)).fetchall()
        return {(row[0], row[1]) for row in rows}

    def excluded_parents(
        self,
        candidates: Sequence[CandidateT],
        current_aliases: Collection[str],
        *,
        current_text: str,
    ) -> set[str]:
        """仅排除明确包含当前 Work，或与同时召回的独立 Work 重复命中的合集。"""
        if not candidates:
            return set()
        by_id = {c.work_id: c for c in candidates}
        candidate_ids = set(by_id)
        aliases = set(current_aliases)
        with self._connect() as db:
            # 已可靠识别当前作品时，直接排除所有包含它的合集候选。
            self_pairs = self._query_pairs(
                db,
                "SELECT parent_work_id, member_work_id FROM work_compositions "
                "WHERE member_work_id IN ({placeholders})",
                aliases,
            )
            exclude = {
                parent
                for parent, _ in self_pairs
                if parent in candidate_ids
                and _same_hit(by_id[parent].text, current_text)
            }
            # 同次召回的 parent 与 member，只有命中原文片段重合时才去重。
            pairs = self._query_pairs(
                db,
                "SELECT parent_work_id, member_work_id FROM work_compositions "
                "WHERE parent_work_id IN ({placeholders})",
                candidate_ids - exclude,
            )
            for parent, member in pairs:
                if parent in by_id and member in by_id and _same_hit(
                    by_id[parent].text, by_id[member].text
                ):
                    exclude.add(parent)
        return exclude


def filter_compositions(
    candidates: Sequence[CandidateT],
    current_aliases: Collection[str],
    relation_lookup: WorkCompositionLookup,
    *,
    current_text: str,
    final_top_k: int,
) -> tuple[CandidateT, ...]:
    """对已完成 Eligibility 的 Work 候选做过滤，按原 RRF 顺序补齐名额。"""
    excluded = relation_lookup.excluded_parents(
        candidates, current_aliases, current_text=current_text,
    )
    return tuple(
        candidate
        for candidate in candidates if candidate.work_id not in excluded
    )[:final_top_k]
