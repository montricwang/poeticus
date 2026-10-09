"""将 font1 行内 span 保留为候选注记，不直接丢弃词正文。

CSS 类名只说明视觉样式，不足以判定历史作者归属。
原段落保持解析器扁平化后的原文，来源区间与归属证据单独保存。"""
from bs4 import Tag

from .blocks import SourceBlock, _class_list
from .rules import INLINE_AUTHOR_NOTE_REVIEWS
from .schema import InlineNoteCandidate


_QUOTE_OPEN = ("“", "「", "『", "‘", '"')


def inspect_inline_font1(
    element: Tag, text: str, block: SourceBlock, collection: str,
    tune: str | None, paragraph_index: int,
) -> tuple[list[InlineNoteCandidate], list[dict[str, object]]]:
    """返回已分类正文块内 span 的记录与 warning。

    span 可能只包住引文的开头，或不包含引文标点。
    偏移量相对于 paragraph_text() 输出的扁平文本，不是 DOM 位置。
    如果无法唯一定位片段，应保守地产生 warning，而不是猜测。
    """
    records: list[InlineNoteCandidate] = []
    warnings: list[dict[str, object]] = []
    candidates = [
        node for node in element.find_all("span")
        if "font1" in _class_list(node)
    ]
    review = INLINE_AUTHOR_NOTE_REVIEWS.get(
        (collection, block.html, block.ordinal)
    )
    for span in candidates:
        span_text = span.get_text("", strip=True)
        if (not span_text or span.find(["img", "br"])
                or text.count(span_text) != 1):
            warnings.append({
                "type": "inline_note_offset_review",
                **block.location(), "paragraph_index": paragraph_index,
                "span_class": "font1",
                "reason": "non_unique_or_complex_markup",
            })
            continue
        start = text.index(span_text)
        end = start + len(span_text)
        after = text[end:].lstrip()
        citation_spills = (
            span_text.rstrip().endswith(("：", ":"))
            and after.startswith(_QUOTE_OPEN)
        )
        attribution = "unverified"
        if review == "user_identified_author_note" and tune == "西江月":
            attribution = "confirmed_author_in_reviewed_source"
        # 黄庭坚分册中的相似标记只作为候选证据，不能据此声称是作者自注。
        record: InlineNoteCandidate = {
            "kind": "inline_note_candidate",
            "origin": attribution,
            "source_html": block.html,
            "source_block": block.ordinal,
            "paragraph_index": paragraph_index,
            "start": start,
            "end": end,
            "text": span_text,
            "span_class": "font1",
            "boundary": (
                "citation_continues_outside_span"
                if citation_spills else "span_text_only"
            ),
            "punctuation_outside_span": after.startswith((
                "。", "！", "？", "；", "，", ".", "!", "?", ";", ",",
            )),
            "body_retains_note": True,
        }
        records.append(record)
        if citation_spills:
            warnings.append({
                "type": "inline_note_boundary_review",
                **block.location(),
                "paragraph_index": paragraph_index,
                "start": start, "end": end,
                "reason": "quoted_text_follows_note_span",
            })
    return records, warnings
