"""批量预检并导出私人、尽量无损的 EPUB 中间 JSON。

先完成全部 15 册预检，才允许写入带有来源文字的输出。
批处理期间不交互式询问图片字；未识别字形按来源位置和文件名报告，
以便先核对原图。

本工具产出的是导入阶段的 Poem JSON，不是前端 poem-library 的 Schema。
"""
import json
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import TypedDict

from backend.data_paths import EPUB_REPORTS_ROOT, READING_NORMALIZED_ROOT, READING_RAW_ROOT

from .config import COLLECTIONS
from .extractor.extractor import extract_collection
from .pipeline.normalize import normalize_poem, unresolved_glyphs
from .shared_checks import (
    NON_EXPORTABLE_WARNING_TYPES,
    collect_missing_glyphs,
    load_map,
)


class MissingGlyphSite(TypedDict):
    html: str
    src: str


class BlockingIssue(TypedDict):
    poem_id: str
    type: str


class CollectionPreflight(TypedDict):
    collection: str
    slug: str
    xhtml_count: int
    candidate_poems: int
    glyph_map: str
    missing_glyphs: list[MissingGlyphSite]
    unexportable: list[BlockingIssue]
    warnings_by_type: dict[str, int]
    inline_note_candidates: int


class BatchPreflight(TypedDict):
    kind: str
    format: str
    collections: list[CollectionPreflight]
    total_collections: int
    total_candidate_poems: int
    total_missing_glyph_sites: int
    total_unexportable_issues: int
    ready_to_export: bool


DEFAULT_MAP_DIR = READING_RAW_ROOT / "glyph_maps"
DEFAULT_OUTPUT_DIR = READING_NORMALIZED_ROOT
DEFAULT_REPORT = EPUB_REPORTS_ROOT / "epub_import_preflight.json"


def _write_json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def prepare_batch(book, toc, *, specs=COLLECTIONS, map_dir=DEFAULT_MAP_DIR):
    """每册只在内存中抽取一次，并保留所有独立阻塞项。

    可公开分享的报告不得包含原诗词、题序或注释。
    私人内存字段 records 绝不能被序列化到报告中。
    """
    planned = []
    for collection, author, slug in specs:
        poems, files = extract_collection(book, toc, collection, slug, author)
        if not poems:
            raise RuntimeError(f"{collection}: 没有任何作品候选")
        records = [asdict(poem) for poem in poems]
        stem = slug.replace("-", "_")
        map_path = Path(map_dir) / f"{stem}.json"
        glyph_map = load_map(map_path)
        missing = collect_missing_glyphs(records, glyph_map)
        blocked = []
        counts = Counter()
        for poem in poems:
            warning_kinds = {
                issue.get("type") for issue in poem.warnings
            }
            counts.update(kind for kind in warning_kinds if kind)
            for kind in sorted(
                warning_kinds & (NON_EXPORTABLE_WARNING_TYPES |
                                 {"missing_image_src"})
            ):
                blocked.append({"poem_id": poem.id, "type": kind})
        planned.append({
            "collection": collection,
            "slug": slug, "stem": stem,
            "files": files, "records": records, "glyph_map": glyph_map,
            "map_path": map_path, "missing": missing,
            "blocked": blocked, "warning_counts": counts,
        })
    return planned


def preflight_report(plan) -> BatchPreflight:
    """只输出来源坐标与计数，不输出用户授权文本。"""
    collections: list[CollectionPreflight] = []
    for item in plan:
        glyph_sites: list[MissingGlyphSite] = [
            {"html": html, "src": src}
            for html, srcs in sorted(item["missing"].items())
            for src in sorted(srcs)
        ]
        collection_report: CollectionPreflight = {
            "collection": item["collection"],
            "slug": item["slug"],
            "xhtml_count": len(item["files"]),
            "candidate_poems": len(item["records"]),
            "glyph_map": str(item["map_path"]),
            "missing_glyphs": glyph_sites,
            "unexportable": item["blocked"],
            "warnings_by_type": dict(sorted(item["warning_counts"].items())),
            "inline_note_candidates": sum(
                len(record["content"].get("inline_notes", []))
                for record in item["records"]
            ),
        }
        collections.append(collection_report)
    return {
        "kind": "private-epub-import-preflight",
        "format": "intermediate_poem_not_frontend",
        "collections": collections,
        "total_collections": len(collections),
        "total_candidate_poems": sum(x["candidate_poems"] for x in collections),
        "total_missing_glyph_sites": sum(
            len(x["missing_glyphs"]) for x in collections
        ),
        "total_unexportable_issues": sum(
            len(x["unexportable"]) for x in collections
        ),
        "ready_to_export": not any(
            x["missing_glyphs"] or x["unexportable"] for x in collections
        ),
    }


def normalize_batch(plan):
    """整批数据先在内存中完成 normalize，再提交私人输出文件。"""
    combined = []
    result = []
    ids = set()
    for item in plan:
        normalized = [
            normalize_poem(deepcopy(record), item["glyph_map"])
            for record in item["records"]
        ]
        remaining = list(unresolved_glyphs(normalized))
        if remaining:
            raise RuntimeError(
                f"{item['collection']}: 规范化后仍有 "
                f"{len(remaining)} 处未解决图片字"
            )
        for record in normalized:
            if record["id"] in ids:
                raise RuntimeError(f"重复的作品 ID：{record['id']}")
            ids.add(record["id"])
        combined.extend(normalized)
        result.append({"entry": item, "normalized": normalized})
    return result, combined


def run_batch(book, toc, *, specs=COLLECTIONS,
              map_dir=DEFAULT_MAP_DIR, output_dir=DEFAULT_OUTPUT_DIR,
              report_path=DEFAULT_REPORT, check_only=False) -> tuple[BatchPreflight, list[str]]:
    """返回可分享摘要与输出；若真实导出被阻塞则直接报错。

    --check 始终只输出元数据报告，不输出语料正文。
    被阻断的 --all 导出也只允许写出元数据报告。
    """
    planned = prepare_batch(book, toc, specs=specs, map_dir=map_dir)
    report = preflight_report(planned)
    _write_json_atomic(Path(report_path), report)
    if check_only:
        return report, []

    if not report["ready_to_export"]:
        raise RuntimeError(
            "批量导出已停止，未写入任何正文 JSON。"
            f"缺少图片字映射 {report['total_missing_glyph_sites']} 处；"
            f"不能导出的未分类内容 {report['total_unexportable_issues']} 处。"
            f"先检查无原文预检报告：{report_path}"
        )
    results, combined = normalize_batch(planned)
    directory = Path(output_dir)
    outputs = []
    for item in results:
        stem = item["entry"]["stem"]
        raw_path = directory / f"{stem}.json"
        norm_path = directory / f"{stem}_normalized.json"
        _write_json_atomic(raw_path, item["entry"]["records"])
        _write_json_atomic(norm_path, item["normalized"])
        outputs.extend([str(raw_path), str(norm_path)])
    combined_path = directory / "all_normalized.json"
    manifest_path = directory / "all_manifest.json"
    _write_json_atomic(combined_path, combined)
    _write_json_atomic(manifest_path, {
        "kind": "intermediate_poem_not_frontend",
        "total": len(combined),
        "volumes": [
            {"collection": item["entry"]["collection"],
             "slug": item["entry"]["slug"],
             "count": len(item["normalized"])}
            for item in results
        ],
    })
    outputs.extend([str(combined_path), str(manifest_path)])
    return report, outputs
