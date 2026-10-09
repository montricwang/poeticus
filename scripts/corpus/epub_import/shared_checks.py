"""Source-preserving checks shared by single and batch EPUB importers.

Importing this module must not import either entrypoint. In particular the
metadata-only batch preflight should never load an importing CLI recursively.
"""
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
    """Find unresolved source images without discarding source positions."""
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
