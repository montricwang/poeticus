"""Apply reviewed method labels to a separate, private JSONL view.

Neither the per-essay records nor the normalized input is modified. The
review file contains only labels, identifiers, hashes and brief judgements;
EPUB text and individual analyses must remain outside this repository.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

from scripts.research.normalize_critic_methods import atomic_jsonl


def apply_reviews(rows: list[dict], decisions: list[dict]) -> tuple[list[dict], dict]:
    """Validate every decision, then apply only approved labels to a copy."""
    corrected = copy.deepcopy(rows)
    by_number = {row["essay_no"]: row for row in corrected}
    if len(by_number) != len(corrected):
        raise ValueError("Duplicate essay numbers in input")

    seen: set[tuple[int, int]] = set()
    totals: Counter[str] = Counter()
    for decision in decisions:
        number = decision["essay_no"]
        index = decision["method_index"]
        key = (number, index)
        if key in seen:
            raise ValueError(f"Duplicate review: {number}/{index}")
        seen.add(key)
        if index < 1 or number not in by_number:
            raise ValueError(f"Unknown essay or method: {number}/{index}")
        row = by_number[number]
        if row["essay_id"] != decision["essay_id"] or index > len(row["methods"]):
            raise ValueError(f"Review identity mismatch: {number}/{index}")
        method = row["methods"][index - 1]
        digest = hashlib.sha256(method["argument_path"].encode("utf-8")).hexdigest()
        if method["code"] != decision["old_code"] or digest != decision["path_sha256"]:
            raise ValueError(f"Review source changed: {number}/{index}")

        status = decision["status"]
        if status == "approved":
            new_code = decision["new_code"]
            if not isinstance(new_code, str) or not new_code or new_code == method["code"]:
                raise ValueError(f"Invalid replacement: {number}/{index}")
            method["code"] = new_code
        elif status not in ("needs_review", "retained"):
            raise ValueError(f"Unknown review status: {status}")
        totals[status] += 1

    return corrected, dict(totals)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Private normalized JSONL")
    parser.add_argument("--output", type=Path, required=True, help="New private reviewed JSONL")
    parser.add_argument("--reviews", type=Path, default=Path(__file__).with_name("critic_method_reviews_2026-10-21.json"))
    parser.add_argument("--expected-count", type=int, default=1505)
    args = parser.parse_args()
    source, output = args.input.resolve(), args.output.resolve()
    if not source.is_file():
        parser.error(f"Input not found: {source}")
    if source == output or output.suffix != ".jsonl" or output.exists():
        parser.error("Output must be a new, distinct .jsonl file")

    with args.reviews.open(encoding="utf-8") as handle:
        reviews = json.load(handle)
    if reviews.get("schema_version") != 1 or not isinstance(reviews.get("decisions"), list):
        parser.error("Invalid review file")
    with source.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if len(rows) != args.expected_count:
        parser.error(f"Expected {args.expected_count} essays, found {len(rows)}")

    result, stats = apply_reviews(rows, reviews["decisions"])
    digest = atomic_jsonl(result, output)
    print(json.dumps({"essays": len(result), **stats, "output_sha256": digest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
