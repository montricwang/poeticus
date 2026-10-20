"""Export private Critic method records as a reproducible JSONL view.

Independent ``records/*.json`` remain the source of truth. The exporter never
rewrites them, and the generated corpus belongs outside the public Git repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path

NAME_PATTERN = re.compile(r"(?P<number>\d{4})_.+\.json$")


def collect_records(records_dir: Path, expected_count: int | None) -> tuple[list[dict], dict]:
    """Validate record identities, keeping both original pilot and later schemas."""
    if not records_dir.is_dir():
        raise ValueError(f"Records directory does not exist: {records_dir}")
    files = sorted(records_dir.glob("*.json"))
    if expected_count is not None and len(files) != expected_count:
        raise ValueError(f"Expected {expected_count} records, found {len(files)}")
    if not files:
        raise ValueError("No JSON records found")

    rows: list[dict] = []
    seen_numbers: set[int] = set()
    seen_ids: set[str] = set()
    schemas: Counter[str] = Counter()
    evidence_count = 0
    methods_count = 0
    for path in files:
        match = NAME_PATTERN.fullmatch(path.name)
        if not match:
            raise ValueError(f"Unexpected JSON record filename: {path.name}")
        original = json.loads(path.read_text(encoding="utf-8"))
        number = int(match.group("number"))
        identifier = original.get("essay_id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"Missing essay_id: {path.name}")
        if original.get("essay_no") != number:
            raise ValueError(f"Essay number mismatch: {path.name}")
        if number in seen_numbers or identifier in seen_ids:
            raise ValueError(f"Duplicate essay number or ID: {path.name}")
        seen_numbers.add(number)
        seen_ids.add(identifier)
        if isinstance(original.get("methods"), list) and original["methods"]:
            schema = "article_v2"
            methods_count += len(original["methods"])
            evidence_count += sum(len(m.get("evidence", [])) for m in original["methods"])
        elif isinstance(original.get("moves"), list) and original["moves"]:
            schema = "pilot_v1"
            methods_count += len(original["moves"])
            evidence_count += sum(len(m.get("evidence", [])) for m in original["moves"])
        else:
            raise ValueError(f"Neither supported research card schema: {path.name}")
        schemas[schema] += 1
        rows.append({"_record_schema": schema, **original})
    rows.sort(key=lambda item: item["essay_no"])
    return rows, {
        "record_count": len(rows),
        "schema_counts": dict(sorted(schemas.items())),
        "method_count": methods_count,
        "evidence_count": evidence_count,
        "first_number": rows[0]["essay_no"],
        "last_number": rows[-1]["essay_no"],
    }


def write_export(rows: list[dict], report: dict, destination: Path) -> dict:
    """Write a complete JSONL snapshot atomically, with integrity metadata."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            for row in rows:
                line = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                out.write(line)
                digest.update(line)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return {**report, "sha256": digest.hexdigest(), "size_bytes": destination.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build one JSONL snapshot from private Critic research cards")
    parser.add_argument("--records", type=Path, required=True, help="Private records/ directory")
    parser.add_argument("--output", type=Path, required=True, help="Private destination .jsonl file")
    parser.add_argument("--expected-count", type=int, default=None)
    args = parser.parse_args()
    if args.output.suffix != ".jsonl":
        parser.error("--output must end in .jsonl")
    records = args.records.resolve()
    output = args.output.resolve()
    if output.parent == records:
        parser.error("Keep the merged output outside the source records directory")
    rows, report = collect_records(records, args.expected_count)
    summary = write_export(rows, report, output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
