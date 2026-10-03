"""Convert private EPUB intermediate records into reader and source records.

Original records are never mutated. Source positions are Unicode code-point
offsets, NOT JavaScript UTF-16 offsets. Modern annotations/commentaries stay
only in the private intermediate JSON and never enter the public repository.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

EXPLICIT_GAP = re.compile(r"（以下缺[^（）]{0,24}）")
SOUTHERN_TANG_AUTHORS = frozenset({"李煜", "李璟"})
LI_COLLECTION = "李清照词集"


@dataclass(frozen=True)
class ConvertedPoem:
    reader: dict[str, Any]
    source: dict[str, Any]
    actions: tuple[str, ...]


def _arrange_segments(record, originals):
    """Return reader segments, source index mapping and applied actions.

    Mapping value: (reader index, prefix length in reader segment, removed_LF).
    """
    output, mapping, actions = [], {}, []
    if record.get("collection") == LI_COLLECTION:
        if not originals or not originals[0].strip() or not originals[-1].strip():
            raise ValueError(f"{record['id']}: 李清照首尾空段待复核")
        group = ""
        for index, piece in enumerate(originals):
            if not piece.strip():
                if not group:
                    raise ValueError(f"{record['id']}: 李清照连续空段待复核")
                output.append(group)
                group = ""
                continue
            mapping[index] = (len(output), len(group), False)
            group += piece
        if group:
            output.append(group)
        actions.append("join_li_qingzhao_lines")
    else:
        remove_newlines = record.get("author") in SOUTHERN_TANG_AUTHORS
        for index, piece in enumerate(originals):
            if not piece:
                raise ValueError(f"{record['id']}: 非李清照词出现空正文元素")
            mapping[index] = (len(output), 0, remove_newlines)
            output.append(piece.replace("\n", "") if remove_newlines else piece)
        if remove_newlines and any("\n" in piece for piece in originals):
            actions.append("strip_southern_tang_lf")
    if not output or not any(s.strip() for s in output):
        raise ValueError(f"{record['id']}: 正文为空")
    return output, mapping, tuple(actions)


def _map_range(originals, rendered, mapping, index, start, end):
    if not isinstance(index, int) or not 0 <= index < len(originals):
        raise ValueError("来源段落编号无效")
    text = originals[index]
    if (not isinstance(start, int) or not isinstance(end, int)
            or not 0 <= start < end <= len(text)):
        raise ValueError("来源注记范围无效")
    if index not in mapping:
        raise ValueError("不能定位到被丢弃的空段")
    segment, prefix, remove_newlines = mapping[index]
    def rebased(i):
        return prefix + i - (text[:i].count("\n") if remove_newlines else 0)
    left, right = rebased(start), rebased(end)
    quote = text[start:end].replace("\n", "") if remove_newlines else text[start:end]
    if rendered[segment][left:right] != quote:
        raise ValueError("转换后正文位置与来源片段不一致")
    return segment, left, right, quote


def _source_digest(record):
    fields = {
        key: record.get(key)
        for key in ("id", "author", "tune", "title", "yusheng", "collection", "source")
    }
    fields["content"] = {
        key: record["content"].get(key, [])
        for key in ("text", "prefaces", "inline_notes")
    }
    packed = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()


def convert_record(record: dict, order: int) -> ConvertedPoem:
    if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
        raise ValueError("来源作品缺少有效 ID")
    content = record.get("content")
    if not isinstance(content, dict):
        raise ValueError(f"{record['id']}: content 不是对象")
    originals = content.get("text")
    if (not isinstance(originals, list)
            or any(not isinstance(piece, str) for piece in originals)):
        raise ValueError(f"{record['id']}: content.text 不是字符串数组")
    if order < 1 or any("{{glyph:" in p for p in originals):
        raise ValueError(f"{record['id']}: 原书顺序或图片字数据无效")
    rendered, mapping, actions = _arrange_segments(record, originals)
    source_notes = content.get("inline_notes", [])
    prefaces = content.get("prefaces", [])
    if (not isinstance(source_notes, list) or not isinstance(prefaces, list)
            or any(not isinstance(p, str) for p in prefaces)):
        raise ValueError(f"{record['id']}: 词序或行内注记格式无效")
    notes = []
    for note in source_notes:
        if not isinstance(note, dict):
            raise ValueError(f"{record['id']}: 行内注记不是对象")
        idx, begin, finish = note.get("paragraph_index"), note.get("start"), note.get("end")
        segment, left, right, quote = _map_range(
            originals, rendered, mapping, idx, begin, finish
        )
        if originals[idx][begin:finish] != note.get("text"):
            raise ValueError(f"{record['id']}: 原始注记文字不匹配")
        notes.append({
            "kind": note.get("kind", "inline_note_candidate"),
            "origin": note.get("origin", "unverified"),
            "boundary": note.get("boundary", "unknown"),
            "segment_index": segment, "start": left, "end": right,
            "quote": quote, "text_version": 1,
            "source_position": {
                "paragraph_index": idx, "start": begin, "end": finish,
                "source_html": note.get("source_html"),
                "source_block": note.get("source_block"),
            },
        })
    lacunae = []
    for index, piece in enumerate(originals):
        for match in EXPLICIT_GAP.finditer(piece):
            segment, left, right, quote = _map_range(
                originals, rendered, mapping, index, match.start(), match.end()
            )
            lacunae.append({
                "kind": "explicit_gap", "segment_index": segment,
                "start": left, "end": right, "quote": quote, "text_version": 1,
                "source_position": {
                    "paragraph_index": index, "start": match.start(), "end": match.end(),
                },
            })
    reader = {
        "source_record_id": record["id"], "source_order": order,
        "collection": record.get("collection") or "",
        "author": record.get("author") or None,
        "cipai": record.get("tune"), "title": record.get("title"),
        "yusheng": record.get("yusheng"),
        "body_segments": rendered, "prefaces": prefaces,
        "inline_notes": notes, "lacunae": lacunae,
        "review_status": "imported_unreviewed", "text_version": 1,
    }
    source = {
        "source_record_id": record["id"],
        "source_title": record.get("source") or "历代名家词集精华录",
        "source_edition": None,
        "source_locator": record.get("source_locator"),  # Future #62; never guess
        "original_segments": originals, "original_inline_notes": source_notes,
        "source_sha256": _source_digest(record),
    }
    return ConvertedPoem(reader, source, actions)


def convert_corpus(data: object) -> list[ConvertedPoem]:
    if not isinstance(data, list):
        raise ValueError("全量 JSON 顶层必须是数组")
    seen: set[str] = set()
    result = []
    for order, record in enumerate(data, 1):
        item = convert_record(record, order)
        key = item.reader["source_record_id"]
        if key in seen:
            raise ValueError(f"重复来源 ID：{key}")
        seen.add(key)
        result.append(item)
    return result
