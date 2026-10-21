"""Build a uniform, lossless analysis view of private Critic method records.

The per-essay records and the original export remain immutable. A pilot_v1
record is projected into article_v2 field names without inventing literary
claims for fields that were never annotated; its full original stays attached
as provenance. The resulting JSONL is private, never a Git artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path

FIELDS = (
    "essay_no", "essay_id", "core_argument", "analysis_target", "methods",
    "special_observation", "limitations", "transferable", "author_vs_ai",
    "analysis_source", "source", "critic", "poet", "work",
)


def normalize_record(original: dict) -> dict:
    """Keep one article_v2-shaped record without inventing missing pilot prose."""
    common = {key: original[key] for key in ("essay_no", "essay_id", "source", "critic", "poet", "work")}
    has_methods = isinstance(original.get("methods"), list) and bool(original["methods"])
    has_moves = isinstance(original.get("moves"), list) and bool(original["moves"])
    if has_methods == has_moves:
        raise ValueError(f"Ambiguous method schema: {common['essay_id']}")

    if has_methods:
        required = ("core_argument", "analysis_target", "special_observation",
                    "limitations", "transferable", "author_vs_ai")
        if any(not isinstance(original.get(key), str) for key in required):
            raise ValueError(f"Incomplete article_v2: {common['essay_id']}")
        normalized = {key: original[key] for key in FIELDS if key != "analysis_source"}
        normalized["analysis_source"] = original.get("analysis_source", "")
        missing_fields = [] if "analysis_source" in original else ["analysis_source"]
        origin = "article_v2"
        legacy = None
    else:
        moves = original["moves"]
        methods = []
        for move in moves:
            evidence = {
                "paragraph": move["paragraph"],
                "quote": move["exact_quote"],
                "char_start": move["char_start"],
                "paragraph_sha256": move["paragraph_sha256"],
            }
            methods.append({
                "code": move["method_code"],
                "argument_path": move["analysis"],
                "evidence": [evidence],
            })
        # These fields are genuinely absent in the pilot annotations.
        # Empty strings mean "not annotated", NOT "the reviewer found nothing".
        normalized = {
            **common,
            "core_argument": "",
            "analysis_target": original["research_question"],
            "methods": methods,
            "special_observation": "",
            "limitations": original["interpretive_limitations"],
            "transferable": "",
            "author_vs_ai": "",
            "analysis_source": "pilot_v1 structural projection; missing interpretive fields not inferred",
        }
        origin = "pilot_v1"
        legacy = original
        missing_fields = ["core_argument", "special_observation", "transferable", "author_vs_ai"]

    if any(not isinstance(normalized.get(key), str) for key in ("essay_id", "critic", "poet", "work")):
        raise ValueError(f"Invalid identity: {common['essay_id']}")
    if not isinstance(normalized["methods"], list) or not normalized["methods"]:
        raise ValueError(f"Missing methods: {common['essay_id']}")
    for method in normalized["methods"]:
        if not method.get("code") or not method.get("argument_path") or not method.get("evidence"):
            raise ValueError(f"Incomplete method: {common['essay_id']}")
        for evidence in method["evidence"]:
            if any(key not in evidence for key in ("paragraph", "quote", "char_start", "paragraph_sha256")):
                raise ValueError(f"Incomplete evidence: {common['essay_id']}")

    return {
        **{key: normalized[key] for key in FIELDS},
        "_record_schema": "article_v2",
        "_origin_schema": origin,
        "_pilot_original": legacy,
        "_missing_fields": missing_fields,
    }


def normalize_rows(source: Path, expected_count: int | None = None) -> tuple[list[dict], dict]:
    """Check identity and preserve all method/evidence items."""
    rows = []
    seen_numbers: set[int] = set()
    seen_ids: set[str] = set()
    origins: Counter[str] = Counter()
    methods = evidence = 0
    with source.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                raise ValueError(f"Blank JSONL line: {line_number}")
            item = normalize_record(json.loads(line))
            number, identifier = item["essay_no"], item["essay_id"]
            if not isinstance(number, int) or number in seen_numbers or identifier in seen_ids:
                raise ValueError(f"Duplicate or invalid identity on line {line_number}")
            seen_numbers.add(number)
            seen_ids.add(identifier)
            origins[item["_origin_schema"]] += 1
            methods += len(item["methods"])
            evidence += sum(len(method["evidence"]) for method in item["methods"])
            rows.append(item)
    if expected_count is not None and len(rows) != expected_count:
        raise ValueError(f"Expected {expected_count}, got {len(rows)}")
    if not rows:
        raise ValueError("Empty input")
    rows.sort(key=lambda row: row["essay_no"])
    return rows, {"records": len(rows), "origin_schemas": dict(origins),
                  "methods": methods, "evidence_indices": evidence}


def atomic_jsonl(rows: list[dict], output: Path) -> str:
    """Replace only a complete output snapshot; never touch input records."""
    output.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    descriptor, name = tempfile.mkstemp(dir=output.parent, prefix=f".{output.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            for row in rows:
                chunk = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                handle.write(chunk)
                digest.update(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, output)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-count", type=int)
    args = parser.parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    if not source.is_file():
        parser.error(f"Input not found: {source}")
    if source == output or output.suffix != ".jsonl":
        parser.error("Output must be a distinct .jsonl file")
    rows, stats = normalize_rows(source, args.expected_count)
    stats["output_sha256"] = atomic_jsonl(rows, output)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
