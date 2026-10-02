"""Import local glyph_review_backup.json directly into per-volume glyph maps.

The backup is a private user's editorial work, never a repository fixture.
Verify the filename/volume for every 001-049 ID against the preflight report
so that even identical-looking glyphs cannot accidentally be misassigned.
"""
import json
from pathlib import Path

from .pipeline.glyph_mapping import codepoint, load_map, parse_form, save_map
from .pipeline.normalize import is_ids_form
from .review_glyphs import glyph_sites


SCHEMA = "poeticus-glyph-review-v1"


def import_review_backup(backup_path, report_path, map_dir, *, partial=False):
    backup = json.loads(Path(backup_path).read_text(encoding="utf-8-sig"))
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    if backup.get("schema") != SCHEMA:
        raise ValueError(f"不支持的备份格式；期望 {SCHEMA}")
    if report.get("kind") != "private-epub-import-preflight":
        raise ValueError("预检报告类型不匹配，需使用 --all --check 生成的报告")

    cases = glyph_sites(report)
    expected = [
        {"id": f"{idx:03d}", "slug": case["slug"], "src": case["src"]}
        for idx, case in enumerate(cases, 1)
    ]
    records = backup.get("records")
    values = backup.get("values")
    if not isinstance(records, list) or records != expected:
        raise ValueError(
            "备份编号/分册/图片文件名与当前预检报告不一致；"
            "禁止将图片字映射到错误作品"
        )
    if not isinstance(values, dict) or set(values) != {
        item["id"] for item in expected
    }:
        raise ValueError("备份缺少编号，或包含预检之外的编号")

    pending = {}
    still_blank, ids_only = [], []
    for record in expected:
        number, slug, src = record["id"], record["slug"], record["src"]
        value = values[number]
        if not isinstance(value, dict):
            raise ValueError(f"编号 {number} 的字形记录格式不正确")
        source = parse_form(value.get("source_form"))
        display = parse_form(value.get("display_form"))
        if not source:
            if display:
                raise ValueError(f"{number}: 缺失原始字形却填写了替代字")
            still_blank.append(number)
            continue
        if len(source) != 1 and not is_ids_form(source):
            raise ValueError(f"{number}: 原始字形应为单字或 IDS，不可填词组")
        if display and len(display) != 1:
            raise ValueError(f"{number}: 替代字形必须是单个 Unicode 字符")
        if is_ids_form(source) and not display:
            ids_only.append(number)
        filename = Path(map_dir) / f"{slug.replace('-', '_')}.json"
        entry = {
            "source_form": source, "source_codepoint": codepoint(source),
            "display_form": display, "display_codepoint": codepoint(display),
            "status": "reviewed",
        }
        pending.setdefault(filename, {})[src] = entry

    if still_blank and not partial:
        raise RuntimeError(
            "还有 " + str(len(still_blank)) +
            " 个编号未填写原始字形：" + ", ".join(still_blank) +
            "。可填完后重新运行，或用 --partial 分批导入"
        )

    # Validate every map before touching any private file.
    updates = {}
    for filename, entries in pending.items():
        current = load_map(filename)
        for src, entry in entries.items():
            old = current.get(src)
            if old is not None and old != entry:
                raise RuntimeError(f"已有 glyph 映射与备份冲突：{filename} / {src}")
        updates[filename] = {**current, **entries}
    for filename, mapping in updates.items():
        save_map(filename, mapping)
    return {
        "mapped": sum(len(entry) for entry in pending.values()),
        "unfilled": still_blank,
        "ids_only": ids_only,
        "map_files": len(updates),
    }
