"""四部词话 Document Corpus 的离线词项检索基线（#133）。

只读取 poeticus-data 下的私有结构化原文与 Seed Eval；
不调用模型、网络或 Poem Retrieval，不生成线上服务与索引资产。
初始检索单位为 EPUB 提取的 section，检索命中后按其原文键回读。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from backend.data_paths import DATA_ROOT

DATASET_DIR = DATA_ROOT / "document-corpus"
DEFAULT_CORPUS = DATASET_DIR / "normalized/document_sections_extracted.json"
DEFAULT_CASES = DATASET_DIR / "evals/document_rag_seed_v0.1.json"
DEFAULT_REPORT = DATASET_DIR / "evals/results/document_bm25_dev_v0.1.json"
LEXICAL_RE = re.compile(r"[\u3400-\u9fff]+|[a-z0-9]+")
SPACE_RE = re.compile(r"\s+")
K1 = 1.2
B = 0.75


def section_key(section: dict[str, Any]) -> str:
    """同一 EPUB 的 section_id 可跨卷重复，必须连同来源文件一起定位。"""
    return "|".join((section["doc"], section["file"], str(section["section_id"])))


def tokenize(text: str) -> list[str]:
    """基础版仅作 Unicode 归一化，不偷偷加入繁简转换或人物别名。"""
    normalized = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    for match in LEXICAL_RE.finditer(normalized):
        value = match.group()
        if value.isascii():
            tokens.append(value)
        else:
            tokens.extend(value[i : i + size] for size in (2, 3) for i in range(len(value) - size + 1))
    return tokens


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def checked_sections(path: Path) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = read_json(path)
    if not isinstance(raw, list) or not raw:
        raise ValueError("语料必须是非空 section 列表")
    keys: set[str] = set()
    for section in raw:
        for field in ("doc", "file", "section_id", "title", "text"):
            if not isinstance(section.get(field), str) or not section[field].strip():
                raise ValueError(f"缺少有效 section 字段 {field}")
        key = section_key(section)
        if key in keys:
            raise ValueError(f"重复来源定位键: {key}")
        keys.add(key)
    return raw


def checked_cases(path: Path, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dataset = read_json(path)
    if not str(dataset.get("status", "")).startswith("draft"):
        raise ValueError("仅允许对未冻结的 draft Seed Dataset 执行初期试验")
    indexed = {section_key(s): s for s in sections}
    ids: set[str] = set()
    cases = dataset["cases"]
    for case in cases:
        case_id = case["id"]
        if case_id in ids:
            raise ValueError(f"重复题号: {case_id}")
        ids.add(case_id)
        if case["gold_status"] != "gold_checked":
            continue
        for evidence in case["gold_evidence"]:
            key = "|".join((evidence["document"], evidence["epub_xhtml"], str(evidence["epub_section_id"])))
            section = indexed.get(key)
            if section is None:
                raise ValueError(f"{case_id}: Gold 指向不存在的 section: {key}")
            # 仅验证原文片段存在，不依据 Gold 文本生成 Query。
            if SPACE_RE.sub("", evidence["quote"]) not in SPACE_RE.sub("", section["text"]):
                raise ValueError(f"{case_id}: Gold 引文未出现于原文: {key}")
    return cases


class SectionBM25:
    """内存中以原 section 为单位的朴素 BM25，暂不持久化派生索引。"""

    def __init__(self, sections: list[dict[str, Any]]) -> None:
        self.sections = sections
        self.keys = [section_key(s) for s in sections]
        self.counts = [Counter(tokenize(f"{s['title']} {s['text']}")) for s in sections]
        self.lengths = [sum(c.values()) for c in self.counts]
        self.average_length = sum(self.lengths) / len(self.lengths)
        frequencies: Counter[str] = Counter()
        for counts in self.counts:
            frequencies.update(counts.keys())
        count = len(sections)
        self.idf = {
            term: math.log(1 + (count - df + 0.5) / (df + 0.5))
            for term, df in frequencies.items()
        }

    def search(self, question: str, k: int = 5) -> list[tuple[str, float]]:
        query = set(tokenize(question))
        ranked: list[tuple[str, float]] = []
        for key, counts, length in zip(self.keys, self.counts, self.lengths):
            score = 0.0
            for term in query:
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + K1 * (1 - B + B * length / self.average_length)
                score += self.idf[term] * frequency * (K1 + 1) / denominator
            if score > 0:
                ranked.append((key, score))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked[:k]


def grade_case(case: dict[str, Any], ranked: list[tuple[str, float]], k: int) -> dict[str, Any]:
    target = {
        "|".join((g["document"], g["epub_xhtml"], str(g["epub_section_id"])))
        for g in case["gold_evidence"]
    }
    keys = [key for key, _ in ranked]
    found = set(keys) & target
    positions = [i + 1 for i, key in enumerate(keys) if key in target]
    return {
        "case_id": case["id"],
        "question": case["question"],
        "gold_section_count": len(target),
        "matched_gold_section_count": len(found),
        "recall_at_k": len(found) / len(target),
        "hit_at_k": bool(found),
        "all_gold_at_k": target <= set(keys),
        "reciprocal_rank": 1 / min(positions) if positions else 0.0,
        "gold_keys": sorted(target),
        "candidates": [{"rank": rank, "key": key, "score": round(score, 5)}
                       for rank, (key, score) in enumerate(ranked, 1)],
    }


def run(corpus: Path, cases_path: Path, report: Path, k: int = 5) -> dict[str, Any]:
    if k < 1:
        raise ValueError("k 必须 >= 1")
    sections = checked_sections(corpus)
    cases = checked_cases(cases_path, sections)
    development = [
        c for c in cases
        if c["split"] == "development"
        and c["gold_status"] == "gold_checked"
        and c["local_coverage"] == "in_corpus"
    ]
    if not development:
        raise ValueError("没有可运行的 development / in_corpus Gold Cases")
    start = time.perf_counter()
    retriever = SectionBM25(sections)
    build_seconds = time.perf_counter() - start
    start = time.perf_counter()
    results = [grade_case(c, retriever.search(c["question"], k), k) for c in development]
    search_seconds = time.perf_counter() - start
    summary = {
        "cases": len(results),
        "mean_recall_at_k": round(sum(x["recall_at_k"] for x in results) / len(results), 4),
        "hit_at_k": round(sum(x["hit_at_k"] for x in results) / len(results), 4),
        "all_gold_at_k": round(sum(x["all_gold_at_k"] for x in results) / len(results), 4),
        "mrr_at_k": round(sum(x["reciprocal_rank"] for x in results) / len(results), 4),
    }
    payload = {
        "experiment": "document_rag_section_bm25_v0.1",
        "scope": "development_in_corpus_only",
        "retriever": {"name": "python_bm25", "ngram": [2, 3], "unicode": "NFKC",
                      "traditional_simplified_mapping": False,
                      "alias_expansion": False, "k1": K1, "b": B,
                      "search_fields": ["section.title", "section.text"], "k": k},
        "inputs": {
            "corpus": str(corpus.resolve()),
            "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(),
            "cases": str(cases_path.resolve()),
            "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
            "section_count": len(sections),
            "raw_epub_sha256": [
                {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                for path in sorted((DATASET_DIR / "raw").glob("*.epub"))
            ],
        },
        "timing_seconds": {"build": round(build_seconds, 4), "search_total": round(search_seconds, 4)},
        "summary": summary,
        "results": results,
        "limitations": [
            "仅以既有 EPUB section 为单元，尚未测试更细 Chunk",
            "未加入繁简字映射、人物别名和查询改写",
            "Gold 来源由先前人工整理，仍需独立核验版本和录文质量",
            "未运行 Dense、Hybrid、外部 API 或 LLM",
        ],
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    result = run(args.corpus, args.cases, args.output, args.top_k)
    print(f"Document BM25: {result['summary']}")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
