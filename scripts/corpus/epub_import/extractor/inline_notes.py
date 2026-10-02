"""Retain inline font1 spans as *candidate* notes, never discard verse.

A CSS class identifies a visual run, not its historical authorship. Store the
exact source extent and attribution evidence separately from the original
paragraph, which stays byte-for-byte the parser's flattened text.
"""
from .rules import INLINE_AUTHOR_NOTE_REVIEWS


_QUOTE_OPEN = ("“", "「", "『", "‘", '"')
_QUOTE_LEADS = ("云：", "云:", "曰：", "曰:", "谓：", "谓:")


def inspect_inline_font1(element, text, block, collection, tune, paragraph_index):
    """Return (records, warnings) for spans inside a classified verse block.

    A span may cover only the lead-in to a quotation or omit its punctuation.
    Offsets refer to paragraph_text's flattened output, never to DOM offsets.
    If the text is not uniquely locatable, fail closed to a warning.
    """
    records = []
    warnings = []
    candidates = [
        node for node in element.find_all("span")
        if "font1" in node.get("class", [])
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
            span_text.rstrip().endswith(_QUOTE_LEADS)
            and after.startswith(_QUOTE_OPEN)
        )
        attribution = "unverified"
        if review == "user_identified_author_note" and tune == "西江月":
            attribution = "confirmed_author_in_reviewed_source"
        # Huang's similar markup is intentionally NOT a claim of authorship.
        record = {
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
