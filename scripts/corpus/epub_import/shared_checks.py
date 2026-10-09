"""供单册与批量 EPUB 导入工具共用的来源保全检查。

本模块不能导入任何导入命令入口；特别是只输出元数据的
批量预检，不应递归加载 CLI。"""
import json
from collections import defaultdict
from pathlib import Path

from .pipeline.normalize import get_output_form, resolve_mapping


NON_EXPORTABLE_WARNING_TYPES = frozenset({
    "unclassified_after_notes",
    "unclassified_before_inserted_author",
    "ambiguous_reference_after_verse",
})


def load_map(path: Path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def collect_missing_glyphs(poems, glyph_map):
    """找出尚未识别的来源图片，同时保留它们的原始位置。"""
    missing = defaultdict(set)
    for poem in poems:
        for warning in poem.get("warnings", []):
            if warning["type"] != "inline_image":
                continue
            src = warning["src"]
            mapping = resolve_mapping(src, glyph_map)
            if get_output_form(mapping) is None:
                missing[warning["html"]].add(src)
    return missing
