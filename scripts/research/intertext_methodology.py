"""Prepare and review INTERTEXT method records without rereading whole essays.

Private outputs are kept outside the public Poeticus repository. The model/human
reviewer supplies decisions explicitly; this script never invents classifications.
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

VERSION = 1
KEY_RE = re.compile(r"^[a-z][a-z0-9-]{1,47}$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(value)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    values = []
    with path.open(encoding="utf-8") as file:
        for line_no, line in enumerate(file, 1):
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")
            values.append(item)
    return values


def jsonl_text(values: list[dict]) -> str:
    return "".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in values)


def extract_intertext(rows: list[dict]) -> list[dict]:
    results = []
    seen = set()
    for essay in rows:
        essay_no = essay["essay_no"]
        for index, method in enumerate(essay.get("methods", [])):
            if method.get("code") != "INTERTEXT":
                continue
            path = method.get("argument_path", "").strip()
            if not path:
                continue
            identifier = f"{essay_no:04d}:m{index}"
            if identifier in seen:
                raise ValueError(f"Duplicate record {identifier}")
            seen.add(identifier)
            evidence = method.get("evidence", [])
            if not isinstance(evidence, list):
                raise ValueError(f"{identifier}: evidence must be a list")
            results.append({
                "record_id": identifier,
                "essay_no": essay_no,
                "essay_id": essay["essay_id"],
                "method_index": index,
                "method_code": "INTERTEXT",
                "argument_path": path,
                "evidence": evidence,
                "essay_context": {
                    field: essay.get(field, "")
                    for field in ("analysis_target", "core_argument",
                                  "special_observation", "transferable",
                                  "limitations", "author_vs_ai")
                },
                "critic": essay.get("critic", ""),
                "poet": essay.get("poet", ""),
                "work": essay.get("work", ""),
                "source": essay.get("source", {}),
            })
    return results


def paths(output: Path) -> tuple[Path, Path, Path]:
    return (output / "intertext-source.jsonl",
            output / "intertext-coding.jsonl",
            output / "intertext-taxonomy.json")


def require_private(output: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    output = output.resolve()
    if output == repo or repo in output.parents:
        raise ValueError("Research data must be stored outside the public Git repository")


def export(input_path: Path, output: Path, expected: int = 949) -> dict:
    require_private(output)
    source, coding, taxonomy = paths(output)
    rows = extract_intertext(read_jsonl(input_path))
    if len(rows) != expected:
        raise ValueError(f"Expected {expected} INTERTEXT records, got {len(rows)}")
    data = jsonl_text(rows)
    if source.exists():
        if source.read_text(encoding="utf-8") != data:
            raise ValueError("Existing source snapshot differs; use a new output directory")
    else:
        if coding.exists() or taxonomy.exists():
            raise ValueError("Coding exists without source snapshot")
        atomic_text(source, data)
    if not coding.exists():
        atomic_text(coding, "")
    if not taxonomy.exists():
        rebuild_taxonomy(output)
    report = {
        "schema_version": VERSION,
        "source_input": str(input_path.resolve()),
        "source_input_sha256": digest(input_path),
        "export_sha256": digest(source),
        "record_count": len(rows),
        "coding_count": len(read_jsonl(coding)),
        "note": "Each row is a method instance, not a complete essay.",
    }
    manifest = output / "source-manifest.json"
    if manifest.exists():
        old = json.loads(manifest.read_text(encoding="utf-8"))
        if old["export_sha256"] != report["export_sha256"]:
            raise ValueError("Existing manifest identifies a different export")
    else:
        atomic_json(manifest, report)
    return report


def verify_decision(decision: dict, source: dict) -> None:
    if decision.get("record_id") != source["record_id"]:
        raise ValueError("Decision ID does not match source")
    actions = decision.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError(f"{source['record_id']}: actions must be a nonempty list")
    seen = set()
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("Each action must be an object")
        key = action.get("key")
        if not isinstance(key, str) or not KEY_RE.fullmatch(key):
            raise ValueError(f"Invalid action key: {key!r}")
        if key in seen:
            raise ValueError(f"Repeated action key for {source['record_id']}: {key}")
        seen.add(key)
        for field in ("name", "input", "operation", "inference", "boundary"):
            if not isinstance(action.get(field), str) or not action[field].strip():
                raise ValueError(f"{source['record_id']}/{key}: missing {field}")
        refs = action.get("evidence_refs")
        if not isinstance(refs, list) or not all(
            type(i) is int and 0 <= i < len(source["evidence"]) for i in refs
        ):
            raise ValueError(f"{source['record_id']}/{key}: invalid evidence_refs")
    if not isinstance(decision.get("rationale"), str) or not decision["rationale"].strip():
        raise ValueError(f"{source['record_id']}: rationale required")
    uncertainty = decision.get("uncertainty", "")
    if not isinstance(uncertainty, str):
        raise ValueError("uncertainty must be a string")


def rebuild_taxonomy(output: Path) -> dict:
    source_path, coding_path, taxonomy_path = paths(output)
    source = {row["record_id"]: row for row in read_jsonl(source_path)}
    reviewed = read_jsonl(coding_path)
    categories: dict[str, dict] = {}
    seen_records = set()
    for decision in reviewed:
        record_id = decision["record_id"]
        if record_id not in source or record_id in seen_records:
            raise ValueError(f"Unknown or duplicate coding record: {record_id}")
        seen_records.add(record_id)
        verify_decision(decision, source[record_id])
        for action in decision["actions"]:
            key, name = action["key"], action["name"]
            if key not in categories:
                categories[key] = {
                    "key": key,
                    "name": name,
                    "status": "provisional",
                    "definition": "",
                    "inclusion_criteria": "",
                    "exclusion_criteria": "",
                    "occurrences": 0,
                    "representative_record_ids": [],
                }
            entry = categories[key]
            if entry["name"] != name:
                raise ValueError(f"Different names for action {key}")
            entry["occurrences"] += 1
            if len(entry["representative_record_ids"]) < 6:
                entry["representative_record_ids"].append(record_id)
    old = {}
    if taxonomy_path.exists():
        old = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    previous = {item["key"]: item for item in old.get("categories", [])}
    for key, entry in categories.items():
        if key in previous:
            for field in ("definition", "inclusion_criteria", "exclusion_criteria", "status"):
                entry[field] = previous[key].get(field, entry[field])
    overview = {
        "schema_version": VERSION,
        "method_code": "INTERTEXT",
        "status": "provisional; manual definitions and cross-case review pending",
        "source_sha256": digest(source_path),
        "source_count": len(source),
        "reviewed_count": len(reviewed),
        "unreviewed_count": len(source) - len(reviewed),
        "categories": sorted(categories.values(), key=lambda item: (-item["occurrences"], item["key"])),
    }
    atomic_json(taxonomy_path, overview)
    return overview


def add_decisions(output: Path, incoming: list[dict], revise: bool = False) -> dict:
    source_path, coding_path, _ = paths(output)
    source = {item["record_id"]: item for item in read_jsonl(source_path)}
    existing = read_jsonl(coding_path)
    by_id = {item["record_id"]: item for item in existing}
    if len(by_id) != len(existing):
        raise ValueError("Duplicate record IDs in coding file")
    incoming_ids = set()
    for item in incoming:
        identifier = item.get("record_id")
        if identifier not in source or identifier in incoming_ids:
            raise ValueError(f"Unknown or duplicate decision ID: {identifier}")
        incoming_ids.add(identifier)
        verify_decision(item, source[identifier])
        if identifier in by_id and not revise:
            raise ValueError(f"Already coded: {identifier}; use --revise to replace")
        by_id[identifier] = item
    ordered = [by_id[row["record_id"]] for row in read_jsonl(source_path) if row["record_id"] in by_id]
    atomic_text(coding_path, jsonl_text(ordered))
    overview = rebuild_taxonomy(output)
    return {"added_or_revised": len(incoming), "reviewed_count": overview["reviewed_count"],
            "remaining": overview["unreviewed_count"], "categories": len(overview["categories"])}


def show_next(output: Path, limit: int, start: int) -> list[dict]:
    source_path, coding_path, _ = paths(output)
    coded = {item["record_id"] for item in read_jsonl(coding_path)}
    rows = [item for item in read_jsonl(source_path) if item["record_id"] not in coded]
    if start < 0 or limit < 1:
        raise ValueError("--start must be >= 0 and --limit must be > 0")
    return rows[start:start + limit]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "next", "add", "rebuild", "status"))
    parser.add_argument("--input", type=Path, help="Reviewed 1505-essay private JSONL (export only)")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=949)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--decisions-json", help="JSON array of reviewed decisions (add only)")
    parser.add_argument("--decisions-file", type=Path, help="Private JSON file with decisions (add only)")
    parser.add_argument("--revise", action="store_true")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    require_private(output)
    if args.command == "export":
        if args.input is None:
            parser.error("export requires --input")
        result = export(args.input, output, args.expected_count)
    elif args.command == "next":
        result = show_next(output, args.limit, args.start)
    elif args.command == "add":
        if bool(args.decisions_json) == bool(args.decisions_file):
            parser.error("add requires exactly one of --decisions-json or --decisions-file")
        decisions = json.loads(args.decisions_json) if args.decisions_json else json.loads(
            args.decisions_file.read_text(encoding="utf-8"))
        if not isinstance(decisions, list) or not decisions:
            parser.error("Expected a nonempty JSON array of decisions")
        result = add_decisions(output, decisions, args.revise)
    elif args.command == "rebuild":
        result = rebuild_taxonomy(output)
    else:
        result = rebuild_taxonomy(output)
        result = {key: result[key] for key in ("source_count", "reviewed_count",
                                              "unreviewed_count")}
        result["category_counts"] = dict(Counter(
            item["key"] for row in read_jsonl(paths(output)[1])
            for item in row["actions"]))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
