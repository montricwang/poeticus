"""Benchmark the long-lived local Retrieval Serving runtime.

The report separates cold-start resource growth from warm request latency.
It is intentionally diagnostic, not a production load test.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import NotRequired, TypedDict

from pydantic import ConfigDict, TypeAdapter, with_config

from backend.data_paths import RETRIEVAL_CORPUS_ROOT, RETRIEVAL_REPORTS_ROOT


from backend.retrieval.serving import RetrievalServingRuntime, ServingSearchResult
from scripts.retrieval.run_serving import (
    DEFAULT_DATA_ROOT,
    DEFAULT_MODEL_ROOT,
    default_paths,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = ROOT / "evals/retrieval_increment_cases.json"
DEFAULT_REPORT_ROOT = RETRIEVAL_REPORTS_ROOT
class BenchmarkContext(TypedDict):
    author: str | None
    dynasty: str | None


class BenchmarkInput(TypedDict):
    poem: str
    context: BenchmarkContext


class BenchmarkTarget(TypedDict):
    author: str
    text: str


@with_config(ConfigDict(extra="allow"))
class BenchmarkCase(TypedDict):
    id: str
    input: BenchmarkInput
    target: BenchmarkTarget
    retrieval_query: str
    current_match_text: str


class DenseTiming(TypedDict):
    encode_ms: float
    ann_ms: float
    metadata_ms: float
    total_ms: NotRequired[float]
    queries: NotRequired[int]


class LexicalTiming(TypedDict):
    total_ms: float


class ChannelTimings(TypedDict):
    dense_sentence: DenseTiming
    dense_clause: DenseTiming
    bm25_sentence: LexicalTiming


class ServingTimings(TypedDict):
    current_alias_lookup_ms: float
    orchestration_ms: float
    total_ms: float
    channels: ChannelTimings


class SampleStats(TypedDict):
    p50: float
    p95: float
    min: float
    max: float


class MemorySample(TypedDict):
    stage: str
    rss_mib: float


class MemoryReport(TypedDict):
    samples: list[MemorySample]
    steady_rss_mib: float


class BenchCaseSummary(TypedDict):
    case_id: str
    query: str
    query_count: int
    target: BenchmarkTarget
    target_visible: bool
    timings: dict[str, SampleStats]
    candidate_preview: list[dict[str, object]]


class UncachedCaseSummary(TypedDict):
    case_id: str
    query: str
    resolved_current_work_ids: list[str]
    target_visible: bool
    timings: dict[str, float]
    candidates: list[dict[str, object]]


class ConcurrencySummary(TypedDict):
    requests: int
    wall_ms: float
    individual_p50_ms: float
    individual_p95_ms: float
    throughput_rps: float | None


class MetadataBuild(TypedDict):
    build_seconds: float
    database_gib: float


class BenchmarkReport(TypedDict):
    schema_version: str
    created_at: str
    system: dict[str, object]
    config: dict[str, object]
    startup_profile: dict[str, object]
    memory: MemoryReport
    disk: dict[str, int]
    metadata_build: MetadataBuild | None
    cases: list[BenchCaseSummary]
    uncached_cases: list[UncachedCaseSummary] | None
    concurrency: ConcurrencySummary
    note: str


_CASES_ADAPTER = TypeAdapter(list[BenchmarkCase])
_TIMINGS_ADAPTER = TypeAdapter(ServingTimings)
_METADATA_ADAPTER = TypeAdapter(MetadataBuild)


DEFAULT_CASE_IDS = (
    "longtail_luyou_dufu_gull",
    "transformed_liqingzhao_fanzhongyan",
    "compressed_jiangkui_dumu_qinglou",
)


def _require_psutil():
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError(
            "Serving Benchmark 需要 psutil；请安装 requirements-retrieval.txt"
        ) from exc
    return psutil


def rss_mib() -> float:
    return _require_psutil().Process().memory_info().rss / (1024 ** 2)


def cpu_model() -> str:
    processor = platform.processor().strip()
    if processor:
        return processor

    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(
            encoding="utf-8",
            errors="ignore",
        ).splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key.strip() in {"model name", "Hardware"}:
                value = value.strip()
                if value:
                    return value
    return "unknown"


def path_size(path: Path) -> int:
    path = path.expanduser().resolve()
    if path.is_file():
        return path.stat().st_size
    if not path.is_dir():
        return 0
    return sum(
        item.stat().st_size
        for item in path.rglob("*")
        if item.is_file()
    )


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("percentile values 不能为空")
    ordered = sorted(values)
    index = max(0, math.ceil(q * len(ordered)) - 1)
    return ordered[index]


def load_cases(path: Path, case_ids: tuple[str, ...]) -> list[BenchmarkCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Benchmark cases 必须是 JSON 对象")
    parsed_cases = _CASES_ADAPTER.validate_python(data.get("cases"))
    by_id = {item["id"]: item for item in parsed_cases}
    missing = [case_id for case_id in case_ids if case_id not in by_id]
    if missing:
        raise ValueError(
            "Benchmark case 不存在："
            + ", ".join(missing)
        )
    return [by_id[case_id] for case_id in case_ids]


def target_visible(result: ServingSearchResult, case: BenchmarkCase) -> bool:
    target = case["target"]
    return any(
        item.author == target["author"]
        and target["text"] in item.text
        for item in result.candidates
    )


def flatten_timings(result: ServingSearchResult) -> dict[str, float]:
    timings = _TIMINGS_ADAPTER.validate_python(result.timings_ms)
    dense_sentence = timings["channels"]["dense_sentence"]
    dense_clause = timings["channels"]["dense_clause"]
    bm25 = timings["channels"]["bm25_sentence"]
    return {
        "current_alias_lookup_ms": timings["current_alias_lookup_ms"],
        "sentence_encode_ms": dense_sentence["encode_ms"],
        "sentence_ann_ms": dense_sentence["ann_ms"],
        "sentence_metadata_ms": dense_sentence["metadata_ms"],
        "clause_encode_ms": dense_clause["encode_ms"],
        "clause_ann_ms": dense_clause["ann_ms"],
        "clause_metadata_ms": dense_clause["metadata_ms"],
        "bm25_ms": bm25["total_ms"],
        "orchestration_ms": timings["orchestration_ms"],
        "total_ms": timings["total_ms"],
    }


def summarize_samples(samples: list[dict[str, float]]) -> dict[str, SampleStats]:
    keys = samples[0].keys()
    return {
        key: {
            "p50": statistics.median(
                sample[key] for sample in samples
            ),
            "p95": percentile(
                [sample[key] for sample in samples],
                0.95,
            ),
            "min": min(sample[key] for sample in samples),
            "max": max(sample[key] for sample in samples),
        }
        for key in keys
    }


def run_case(runtime: RetrievalServingRuntime, case: BenchmarkCase, top_k: int) -> ServingSearchResult:
    return runtime.search(
        case["retrieval_query"],
        current_text=case["input"]["poem"],
        current_author=case["input"]["context"].get("author"),
        target_dynasty=case["input"]["context"].get("dynasty"),
        final_top_k=top_k,
    )


def resolve_current_work_ids(
    work_path: Path,
    cases: list[BenchmarkCase],
) -> dict[str, set[str]]:
    """Resolve excerpt fixtures to corpus Works outside measured latency."""
    resolved: dict[str, set[str]] = {case["id"]: set() for case in cases}
    with work_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            work = json.loads(line)
            author = work.get("author")
            content = work.get("content", "")
            if not isinstance(content, str):
                continue
            for case in cases:
                if author != case["input"]["context"].get("author"):
                    continue
                if case["current_match_text"] in content:
                    resolved[case["id"]].add(work["work_id"])
    return resolved


def run_uncached_cases(runtime: RetrievalServingRuntime, cases: list[BenchmarkCase], work_path: Path, top_k: int) -> list[UncachedCaseSummary]:
    """Measure actual uncached query encoding while excluding fixture self-hits.

    Resolving full Work IDs and scanning the corpus happen outside measured
    request timings. Cache is cleared before each case, never the warm runs.
    """
    current_ids = resolve_current_work_ids(work_path, cases)
    results: list[UncachedCaseSummary] = []
    for case in cases:
        runtime.encoder.clear_cache()
        result = runtime.search(
            case["retrieval_query"],
            current_text=case["input"]["poem"],
            current_author=case["input"]["context"].get("author"),
            target_dynasty=case["input"]["context"].get("dynasty"),
            final_top_k=top_k,
            current_work_ids=current_ids[case["id"]],
        )
        results.append({
            "case_id": case["id"],
            "query": case["retrieval_query"],
            "resolved_current_work_ids": sorted(current_ids[case["id"]]),
            "target_visible": target_visible(result, case),
            "timings": flatten_timings(result),
            "candidates": [
                {"rank": item.rank, "author": item.author,
                 "title": item.title, "text": item.text}
                for item in result.candidates
            ],
        })
    return results


def render_markdown(report: BenchmarkReport) -> str:
    lines = [
        "# Retrieval Serving Benchmark",
        "",
        "> 本报告是本机 diagnostic，不是生产压测。p95 样本量较小时只用于比较，不代表正式 SLO。",
        "",
        "## Cold start / RSS",
        "",
        "| stage | RSS MiB | delta MiB |",
        "| --- | ---: | ---: |",
    ]
    previous = None
    for item in report["memory"]["samples"]:
        delta = (
            0.0
            if previous is None
            else item["rss_mib"] - previous
        )
        lines.append(
            f"| {item['stage']} | {item['rss_mib']:.1f} | {delta:.1f} |"
        )
        previous = item["rss_mib"]

    lines.extend(
        [
            "",
            "## Disk footprint",
            "",
            "| artifact | GiB |",
            "| --- | ---: |",
        ]
    )
    for key, value in report["disk"].items():
        lines.append(
            f"| {key} | {value / (1024 ** 3):.3f} |"
        )

    lines.extend(
        [
            "",
            "## Warm requests",
            "",
            "| case | queries | target visible | total p50 ms | total p95 ms | BM25 p50 ms | sentence ANN p50 ms | clause ANN p50 ms |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in report["cases"]:
        summary = case["timings"]
        lines.append(
            "| "
            + " | ".join(
                [
                    case["case_id"],
                    str(case["query_count"]),
                    str(case["target_visible"]),
                    f"{summary['total_ms']['p50']:.1f}",
                    f"{summary['total_ms']['p95']:.1f}",
                    f"{summary['bm25_ms']['p50']:.1f}",
                    f"{summary['sentence_ann_ms']['p50']:.1f}",
                    f"{summary['clause_ann_ms']['p50']:.1f}",
                ]
            )
            + " |"
        )

    concurrent = report["concurrency"]
    lines.extend(
        [
            "",
            "## Five-request concurrency",
            "",
            f"- wall_ms: {concurrent['wall_ms']:.1f}",
            f"- individual p50_ms: {concurrent['individual_p50_ms']:.1f}",
            f"- individual p95_ms: {concurrent['individual_p95_ms']:.1f}",
            (
                f"- throughput req/s: {concurrent['throughput_rps']:.2f}"
                if concurrent["throughput_rps"] is not None
                else "- throughput req/s: unavailable"
            ),
            "",
            "## Metadata build",
            "",
            (
                f"- build_seconds: {report['metadata_build']['build_seconds']:.1f}"
                if report.get("metadata_build")
                else "- metadata build manifest: unavailable"
            ),
            (
                f"- database_gib: {report['metadata_build']['database_gib']:.3f}"
                if report.get("metadata_build")
                else ""
            ),
            "",
            "## Startup profile",
            "",
            "~~~json",
            json.dumps(
                report["startup_profile"],
                ensure_ascii=False,
                indent=2,
            ),
            "~~~",
            "",
            "## Notes",
            "",
            "- 模型 / FAISS 在 runtime 初始化时只加载一次。",
            "- sentence / clause Dense 共用一个 Qwen encoder；第二个 Dense channel 通常命中 query-vector cache。",
            "- metadata lookup 使用 SQLite primary-key 批量回查，不再扫描 JSONL。",
            "- 并发测试使用同一进程、同一 runtime；当前 encoder / FAISS 有锁，结果用来判断单实例是否足够，不是最终扩展方案。",
        ]
    )

    if report.get("uncached_cases"):
        lines.extend([
            "",
            "## Uncached queries (self-hit excluded)",
            "",
            "| case | current IDs | target visible | total ms | encode ms | sentence ANN ms | clause ANN ms | BM25 ms |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ])
        for item in report["uncached_cases"]:
            timing = item["timings"]
            lines.append(
                "| " + " | ".join([
                    item["case_id"],
                    str(len(item["resolved_current_work_ids"])),
                    str(item["target_visible"]),
                    f"{timing['total_ms']:.1f}",
                    f"{timing['sentence_encode_ms']:.1f}",
                    f"{timing['sentence_ann_ms']:.1f}",
                    f"{timing['clause_ann_ms']:.1f}",
                    f"{timing['bm25_ms']:.1f}",
                ]) + " |"
            )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="测量本地 Retrieval Serving 的资源与延迟"
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
    )
    parser.add_argument(
        "--model-root",
        type=Path,
        default=DEFAULT_MODEL_ROOT,
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES,
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
    )
    parser.add_argument("--device")
    parser.add_argument("--search-k", type=int, default=100)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--include-uncached", action="store_true",
                        help="额外测量清空 Query cache 后的首查，并按完整作品排除 self-hit")
    parser.add_argument("--works", type=Path,
                        default=RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl",
                        help="--include-uncached 使用的来源 Work JSONL")
    parser.add_argument(
        "--output-prefix",
        type=Path,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    psutil = _require_psutil()
    if args.runs <= 0:
        raise SystemExit("--runs 必须为正整数")
    if args.concurrency <= 0:
        raise SystemExit("--concurrency 必须为正整数")

    case_ids = tuple(args.case_ids or DEFAULT_CASE_IDS)
    cases = load_cases(args.cases, case_ids)
    paths = default_paths(
        args.data_root,
        args.model_root,
    )

    memory_samples: list[MemorySample] = [
        {
            "stage": "baseline",
            "rss_mib": rss_mib(),
        }
    ]

    def sample(stage: str) -> None:
        memory_samples.append(
            {
                "stage": stage,
                "rss_mib": rss_mib(),
            }
        )

    runtime = RetrievalServingRuntime(
        paths,
        device=args.device,
        search_k=args.search_k,
        rrf_k=args.rrf_k,
        stage_callback=sample,
    )
    memory_samples.append(
        {
            "stage": "ready",
            "rss_mib": rss_mib(),
        }
    )

    disk = {
        "sentence_faiss": path_size(paths.sentence_faiss_dir),
        "clause_faiss": path_size(paths.clause_faiss_dir),
        "sentence_bm25": path_size(paths.bm25_sentence_dir),
        "metadata_db": path_size(paths.metadata_db),
        "qwen_model": path_size(paths.model_path),
    }
    metadata_manifest_path = paths.metadata_db.with_suffix(
        ".manifest.json"
    )
    metadata_build: MetadataBuild | None = (
        _METADATA_ADAPTER.validate_python(json.loads(
            metadata_manifest_path.read_text(encoding="utf-8")
        ))
        if metadata_manifest_path.is_file()
        else None
    )

    case_reports: list[BenchCaseSummary] = []
    for case in cases:
        warm = run_case(runtime, case, args.top_k)

        samples = []
        visible = target_visible(warm, case)
        candidate_preview = [
            {
                "rank": item.rank,
                "author": item.author,
                "title": item.title,
                "text": item.text,
            }
            for item in warm.candidates
        ]
        for _ in range(args.runs):
            result = run_case(runtime, case, args.top_k)
            samples.append(flatten_timings(result))
            visible = visible or target_visible(result, case)

        case_reports.append(
            {
                "case_id": case["id"],
                "query": case["retrieval_query"],
                "query_count": _TIMINGS_ADAPTER.validate_python(warm.timings_ms)["channels"]["dense_sentence"].get("queries", 0),
                "target": case["target"],
                "target_visible": visible,
                "timings": summarize_samples(samples),
                "candidate_preview": candidate_preview,
            }
        )

    concurrent_cases = [
        cases[index % len(cases)]
        for index in range(args.concurrency)
    ]
    concurrent_started = time.perf_counter()
    with ThreadPoolExecutor(
        max_workers=args.concurrency
    ) as executor:
        futures = [
            executor.submit(
                run_case,
                runtime,
                case,
                args.top_k,
            )
            for case in concurrent_cases
        ]
        concurrent_results = [
            future.result()
            for future in futures
        ]
    concurrent_wall_ms = (
        time.perf_counter() - concurrent_started
    ) * 1000
    individual = [
        result.timings_ms["total_ms"]
        for result in concurrent_results
    ]
    uncached_cases = (
        run_uncached_cases(runtime, cases, args.works, args.top_k)
        if args.include_uncached else None
    )
    memory_samples.append(
        {
            "stage": "post_benchmark",
            "rss_mib": rss_mib(),
        }
    )

    virtual_memory = psutil.virtual_memory()
    swap_memory = psutil.swap_memory()
    disk_usage = psutil.disk_usage(str(paths.metadata_db.parent))
    report: BenchmarkReport = {
        "schema_version": "1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "system": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_model": cpu_model(),
            "cpu_physical": psutil.cpu_count(logical=False),
            "cpu_logical": psutil.cpu_count(logical=True),
            "ram_total_gib": virtual_memory.total / (1024 ** 3),
            "swap_total_gib": swap_memory.total / (1024 ** 3),
            "disk_total_gib": disk_usage.total / (1024 ** 3),
            "disk_free_gib": disk_usage.free / (1024 ** 3),
        },
        "config": {
            "search_k": args.search_k,
            "rrf_k": args.rrf_k,
            "top_k": args.top_k,
            "runs_per_case": args.runs,
            "concurrency": args.concurrency,
            "device_requested": args.device,
        },
        "startup_profile": runtime.startup_profile,
        "memory": {
            "samples": memory_samples,
            "steady_rss_mib": rss_mib(),
        },
        "disk": disk,
        "metadata_build": metadata_build,
        "cases": case_reports,
        "uncached_cases": uncached_cases,
        "concurrency": {
            "requests": args.concurrency,
            "wall_ms": concurrent_wall_ms,
            "individual_p50_ms": statistics.median(individual),
            "individual_p95_ms": percentile(individual, 0.95),
            "throughput_rps": (
                args.concurrency / (concurrent_wall_ms / 1000)
                if concurrent_wall_ms
                else None
            ),
        },
        "note": (
            "这是单机、单进程 diagnostic。p95 样本量较小，"
            "主要用于决定 VPS 资源级别与下一步优化方向。"
        ),
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    prefix = (
        args.output_prefix
        if args.output_prefix
        else DEFAULT_REPORT_ROOT / f"retrieval_serving_{stamp}"
    )
    prefix = prefix.expanduser().resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    md_path = prefix.with_suffix(".md")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(
        render_markdown(report),
        encoding="utf-8",
    )

    print(f"JSON：{json_path}")
    print(f"Markdown：{md_path}")


if __name__ == "__main__":
    main()
