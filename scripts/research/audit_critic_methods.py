"""Audit private Critic cards against their EPUB and select review strata.

Run only in the owner's local research environment. The report and sample
index stay beside the private data; no commentary text enters the Git repo.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import random
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from bs4 import BeautifulSoup


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def import_runner(path: Path):
    spec = importlib.util.spec_from_file_location("private_critic_runner_audit", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot import private reader: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_main(rows: list[dict], manifest: list[dict], epub: Path, runner) -> list[dict]:
    """Reparse source paragraphs once per document and verify every short quote."""
    by_id = {entry["essay_id"]: entry for entry in manifest}
    if len(by_id) != len(manifest) or len(rows) != len(manifest):
        raise ValueError("Manifest/record count or identity mismatch")
    errors: list[dict] = []
    cache: dict = {}
    digest = hashlib.sha256(epub.read_bytes()).hexdigest()
    if any(entry["source_sha256"] != digest for entry in manifest):
        raise ValueError("EPUB differs from manifest source_sha256")
    with ZipFile(epub) as archive:
        for row in rows:
            identifier = row["essay_id"]
            entry = by_id.get(identifier)
            if entry is None:
                errors.append({"essay_no": row["essay_no"], "error": "not in manifest"})
                continue
            try:
                identifiers, paragraphs, signature, parsed_id = runner.parse(
                    {"EPUB文件": entry["epub_file"],
                     "条目锚点": " / ".join(entry["entry_anchors"])},
                    archive, cache,
                )
                if parsed_id != identifier or identifiers != entry["entry_anchors"]:
                    raise ValueError("identity/anchor mismatch")
                if len(paragraphs) != entry["review_paragraph_count"]:
                    raise ValueError("paragraph count mismatch")
                if row["source"]["epub_file"] != entry["epub_file"]:
                    raise ValueError("source file mismatch")
                if row["critic"] != signature.strip("（）() "):
                    raise ValueError("critic signature mismatch")
                if row["work"] != entry["work"]:
                    raise ValueError("work mismatch")
                if row["poet"] != entry["poet"]:
                    # Pilot #3 correctly attributes the joint review to 韩翃 and 柳氏;
                    # the historical manifest accidentally repeated 韩翃.
                    correction = (row["essay_no"] == 3
                                  and entry["poet"] == "韩翃 / 韩翃"
                                  and row["poet"] == "韩翃、柳氏")
                    if not correction:
                        raise ValueError("poet mismatch")
                runner.validate(row, entry, paragraphs)
            except Exception as error:
                errors.append({"essay_no": row["essay_no"], "error": str(error)})
    return errors


def exception_paragraphs(spec: dict, archive: ZipFile) -> list[str]:
    """Apply only the manually documented exception paragraph ranges."""
    html = BeautifulSoup(archive.read("OEBPS/" + spec["body_file"]), "html.parser")
    if Path(spec["start_file"]).name == spec["body_file"]:
        anchor = html.find(id=spec["title_anchor"])
        if anchor is None:
            raise ValueError("exception title anchor absent")
        paragraphs = []
        for sibling in anchor.next_siblings:
            if getattr(sibling, "name", None) in ("h1", "h2", "h3"):
                break
            if getattr(sibling, "name", None) == "p":
                paragraphs.append(sibling)
    else:
        paragraphs = html.find_all("p")
    selected = paragraphs[spec["body_start"] - 1:spec["body_stop"]]
    if spec.get("exclude_signatures"):
        selected = [p for p in selected if "luokuan" not in p.get("class", [])]
    return [p.get_text(" ", strip=True) for p in selected]


def validate_exceptions(epub: Path, spec_path: Path, directory: Path) -> list[dict]:
    """Check the nine supplemental cards separately; do not renumber the pool."""
    specs = json.loads(spec_path.read_text(encoding="utf-8"))
    source_sha = hashlib.sha256(epub.read_bytes()).hexdigest()
    results = []
    with ZipFile(epub) as archive:
        for spec in specs:
            tag = spec.get("record_key", f"{spec['essay_no']:04d}")
            record = json.loads((directory / f"{tag}.json").read_text(encoding="utf-8"))
            try:
                paragraphs = exception_paragraphs(spec, archive)
                source = record["source"]
                if (source["epub_sha256"] != source_sha
                        or source["paragraph_count"] != len(paragraphs)
                        or source["paragraph_sha256"]
                        != [hashlib.sha256(p.encode("utf-8")).hexdigest() for p in paragraphs]):
                    raise ValueError("source/paragraph digest mismatch")
                for method in record["methods"]:
                    for evidence in method["evidence"]:
                        paragraph = paragraphs[evidence["paragraph"] - 1]
                        offset, quote = evidence["char_start"], evidence["quote"]
                        if paragraph[offset:offset + len(quote)] != quote:
                            raise ValueError("source quote mismatch")
                        if hashlib.sha256(paragraph.encode("utf-8")).hexdigest() != evidence["paragraph_sha256"]:
                            raise ValueError("source hash mismatch")
                results.append({"key": tag, "status": "quote_hash_verified", "work": record["work"]})
            except Exception as error:
                results.append({"key": tag, "status": "failed", "error": str(error)})
    return results


def choose_stratified(rows: list[dict], seed: int = 20261021) -> list[dict]:
    """Ensure different critics, entry lengths, schema generations and risks."""
    rng = random.Random(seed)
    authors = Counter(row["critic"] for row in rows)
    chosen: dict[str, dict] = {}
    def take(name: str, candidates: list[dict], count: int) -> None:
        available = [r for r in candidates if r["essay_id"] not in chosen]
        for row in rng.sample(available, min(count, len(available))):
            chosen[row["essay_id"]] = {
                "essay_no": row["essay_no"], "essay_id": row["essay_id"],
                "critic": row["critic"], "poet": row["poet"], "work": row["work"],
                "paragraphs": row["source"]["review_paragraph_count"],
                "method_codes": ",".join(m["code"] for m in row["methods"]),
                "stratum": name, "manual_verdict": "pending", "manual_note": "",
            }

    take("pilot_v1", [r for r in rows if r["_origin_schema"] == "pilot_v1"], 4)
    new = [r for r in rows if r["_origin_schema"] == "article_v2"]
    take("prolific_critic", [r for r in new if authors[r["critic"]] >= 20], 8)
    take("rare_critic", [r for r in new if authors[r["critic"]] <= 2], 8)
    take("long_commentary", [r for r in new if r["source"]["review_paragraph_count"] >= 9], 4)
    take("short_commentary", [r for r in new if r["source"]["review_paragraph_count"] <= 2], 4)
    take("risk_debate_allegory", [
        r for r in new if {"DEBATE", "ALLEGORY"} & {m["code"] for m in r["methods"]}
    ], 4)
    take("rare_method", [
        r for r in new if {"PROSODY", "COUNTERFACTUAL"} & {m["code"] for m in r["methods"]}
    ], 4)
    return sorted(chosen.values(), key=lambda row: row["essay_no"])


def attach_manual_reviews(sample: list[dict], decisions: dict[str, dict]) -> int:
    """Apply human decisions only to sampled essays; never infer a verdict."""
    index = {str(row["essay_no"]): row for row in sample}
    accepted = {"supported_with_caveats", "label_mismatch", "taxonomy_uncertain",
                "critic_overreach_caveated", "unsupported", "uncertain"}
    for key, review in decisions.items():
        if key not in index:
            raise ValueError(f"Manual review {key} is not in the stratified sample")
        if review.get("verdict") not in accepted or not isinstance(review.get("note"), str):
            raise ValueError(f"Malformed manual review: {key}")
        index[key]["manual_verdict"] = review["verdict"]
        index[key]["manual_note"] = review["note"]
    return len(decisions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uniform", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--epub", required=True, type=Path)
    parser.add_argument("--private-runner", required=True, type=Path)
    parser.add_argument("--exception-specs", required=True, type=Path)
    parser.add_argument("--exceptions-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manual-reviews", type=Path, help="Private JSON of human essay_no verdicts")
    args = parser.parse_args()
    rows, manifest = load_jsonl(args.uniform), load_jsonl(args.manifest)
    runner = import_runner(args.private_runner)
    if len(rows) != 1505:
        raise ValueError(f"Unexpected corpus size: {len(rows)}")
    main_errors = validate_main(rows, manifest, args.epub, runner)
    exceptions = validate_exceptions(args.epub, args.exception_specs, args.exceptions_dir)
    sample = choose_stratified(rows)
    reviewed = attach_manual_reviews(sample, json.loads(args.manual_reviews.read_text(encoding="utf-8"))) if args.manual_reviews else 0
    authors = Counter(row["critic"] for row in rows)
    code_counts = Counter(method["code"] for row in rows for method in row["methods"])
    missing_counts = Counter(field for row in rows for field in row["_missing_fields"])
    verdict_counts = Counter(row["manual_verdict"] for row in sample if row["manual_verdict"] != "pending")
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_file = output_dir / "stratified_sample.csv"
    with sample_file.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(sample[0]))
        writer.writeheader()
        writer.writerows(sample)
    exception_verified = sum(item["status"] == "quote_hash_verified" for item in exceptions)
    lines = [
        "# 1505 篇词评方法卡｜第一轮质量审计",
        "",
        "程序逐篇核对原文引文定位；人工判定来自独立审阅记录。两者都不等于 1505 篇观点已获独立事实验证。",
        "",
        f"- 正式记录：{len(rows)}；评论署名字符串：{len(authors)}。",
        f"- 方法观察：{sum(code_counts.values())}；短引索引：{sum(len(m['evidence']) for r in rows for m in r['methods'])}。",
        f"- EPUB 对照记录异常：{len(main_errors)}。",
        f"- 独立补遗：{len(exceptions)}，短引及哈希验证通过 {exception_verified}；**未合入主池**。",
        f"- 分层样本：{len(sample)}；人工语义已审 {reviewed}，未审 {len(sample) - reviewed}；见 stratified_sample.csv。",
        f"- 结构投影缺项：{dict(missing_counts)}；空字段表示原本没有标注，不得解释为否定结论。",
        "",
        "## 评论署名分布（前十）",
        "",
        *[f"- {name}：{count} 篇" for name, count in authors.most_common(10)],
        "",
        "## 方法标签分布（仅初标次数，不是准确率）",
        "",
        *[f"- {name}：{count}" for name, count in code_counts.most_common()],
        "",
        "## 程序发现的主池异常",
        "",
        *(f"- #{item['essay_no']}: {item['error']}" for item in main_errors),
        *([] if main_errors else ["- 无（只表示已设计的结构与原文定位检查未发现异常）"]),
        "",
        "## 七处旧分篇异常：九张独立补遗卡",
        "",
        *[f"- {item['key']}：{item['status']}" + (f"（{item['error']}）" if 'error' in item else "")
          for item in exceptions],
        "",
        "## 人工语义审查",
        "",
        f"已审 {reviewed} 篇、待审 {len(sample) - reviewed} 篇；人工备注见 stratified_sample.csv，完整核读意见单独保存在私有语义报告。",
        "复核重点：方法是否真从赏析推出、引文是否断章取义、评论者假说是否被改写成事实。",
        *[f"- {verdict}：{count} 篇" for verdict, count in sorted(verdict_counts.items())],
        "程序验真≠语义认可；所有初标标签均可能被人工推翻。",
        "完成本次人工判断后，详情见独立私有文件 semantic_review_36.md（该文件由审阅者维护，本脚本不会覆盖）。",
        "",
        "## 边界",
        "",
        "- 保留原始 records/cards、任务池、manifest、checkpoint 和 9 份补遗；不重新编号。",
        "- 目录 #3 的「韩翃 / 韩翃」与已核的「韩翃、柳氏」不一致；保留人工校正署名，不覆盖历史 manifest。",
        "- 该报告与样本仅存私人数据目录，不上传版权受限分析与原文。",
        "",
    ]
    (output_dir / "quality_audit.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "records": len(rows), "authors": len(authors), "methods": sum(code_counts.values()),
        "source_verification_errors": len(main_errors), "exception_cards_verified": exception_verified,
        "exception_cards_total": len(exceptions), "sample": len(sample),
        "semantic_reviewed": reviewed, "semantic_pending": len(sample) - reviewed,
        "missing_fields": dict(missing_counts),
    }, ensure_ascii=False, indent=2))
    return 1 if main_errors or exception_verified != len(exceptions) else 0


if __name__ == "__main__":
    raise SystemExit(main())
