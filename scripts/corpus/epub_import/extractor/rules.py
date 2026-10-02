"""Scoped semantic rules for the *poetry anthologies* in this EPUB.

This module intentionally does not encode suite relationships, tune history or
textual scholarship. Source markup remains available in the private EPUB.
"""
import re
from bs4 import NavigableString, Tag

CHRONOLOGY = re.compile(r"[（(]\d{4}[）)]$")
# The anthology's explicit editorial omission marker, not authored verse.
# Keep original text; downstream schema policy is a separate decision.
INLINE_EDITORIAL_GAP = re.compile(r"[（(]\s*以下缺\s*[）)]")
HE_ZHU_ALIAS_NOTE = re.compile(r"^(?P<tune>[^，,]+)[，,]\s*亦名\s*(?P<alias>.+)$")
# Only explicit document labels confirmed by the 15-volume audit.
EDITORIAL_HEADINGS = {"总评"}
NON_POEMS = {"欧阳修词集": {"西湖念语"}}

# A manual check of the *private* source on 2026-10-02 established that
# these two runs are extended scholarly commentary after a ◆ paragraph.
# Match original XHTML + work-start block + paragraph block range so no other
# work in this volume (or even the same file) acquires inferred commentary.
# If the source layout changes, fail closed instead of inventing attribution.
VERIFIED_ZHOU_COMMENTARY_RUNS = {
    ("text00241.html", 2): range(20, 39),     # 少年游, 19 paragraphs
    ("text00241.html", 504): range(511, 513),  # 红林檎近, 2 paragraphs
}


def is_verified_zhou_commentary(collection, html_name, work_block, block, classes):
    if collection != "周邦彦词集":
        return False
    run = VERIFIED_ZHOU_COMMENTARY_RUNS.get((html_name, work_block))
    if run is None or block not in run:
        return False
    allowed = {"kindle-cn-ref", "kindle-cn-para-no-indent"}
    return not classes or classes <= allowed



def is_inline_styled_span(span):
    """Whether the EPUB markup marks a span as distinct from normal type."""
    return bool(
        span.get("style")
        or any(cls in {"kindle-cn-kai", "kaiti", "small"}
               or cls.startswith("font") for cls in span.get("class", []))
    )


# Scoped human-review evidence for the particular commercial EPUB layout.
# Do not infer 'author's note' from font1 globally: other font1 spans can
# represent editorial glosses or simply typesetting.
# The second case is only a candidate; authorship has not been established.
INLINE_AUTHOR_NOTE_REVIEWS = {
    ("辛弃疾词集", "text00278.html", 135): "user_identified_author_note",
    ("黄庭坚词集", "text00214.html", 679): "possible_author_note",
}


def is_pagination_kaiti_continuation(span):
    """A kaiti span used for verse split by an EPUB page marker.

    Requires an immediately preceding empty page anchor and no meaningful
    content after the span apart from layout <br> nodes. This does not classify
    generic kaiti text or other styled spans as verse.
    """
    if span.name != "span" or "kaiti" not in span.get("class", []):
        return False
    previous = span.previous_sibling
    while previous is not None and not str(previous).strip():
        previous = previous.previous_sibling
    if (previous is None or getattr(previous, "name", None) != "a"
            or not re.fullmatch(
                r"page\d+", previous.get("id", "")
            ) or previous.get_text("", strip=True)):
        return False
    after = span.next_sibling
    while after is not None:
        if getattr(after, "name", None) == "br" or not str(after).strip():
            after = after.next_sibling
        else:
            return False
    return True


def is_non_poem(collection, heading):
    name = heading.strip()
    return name in EDITORIAL_HEADINGS or name in NON_POEMS.get(collection, set())


def is_chronology(tag, text):
    """Chronological labels precede the next work, not the previous poem."""
    return ("kindle-cn-para-no-indent1" in tag.get("class", [])
            and bool(CHRONOLOGY.search(text)) and len(text) < 55)


def is_separate_title(tag, collection):
    """In Liu Yong, some titles use a centered Kai paragraph after the h2."""
    css = set(tag.get("class", []))
    return ("柳永" in collection and
            {"kindle-cn-para-center", "kindle-cn-kai"}.issubset(css))


def is_preface(tag, collection):
    css = set(tag.get("class", []))
    if "kindle-cn-ref2" in css:
        return True
    if "kindle-cn-ref" in css:
        # In some volumes these same classes occur in introductions. This
        # predicate is only applied *within* a work, before its first verse.
        return True
    if {"kindle-cn-para-2em-indent", "kindle-cn-kai"}.issubset(css):
        return any(x in collection for x in ("苏轼", "辛弃疾", "黄庭坚"))
    return False


def _heading_inline_text(node):
    """Retain glyph positions even when images are nested inside a subtitle."""
    pieces = []
    for child in node.descendants:
        if isinstance(child, NavigableString):
            pieces.append(str(child))
        elif isinstance(child, Tag) and child.name == "img":
            pieces.append("{{glyph:" + (child.get("src") or "missing-src") + "}}")
        elif isinstance(child, Tag) and child.name == "br":
            pieces.append("\n")
    return "".join(pieces).strip()


def heading_components(tag):
    """Read heading runs in source order, keeping inline glyphs in place."""
    pieces = []
    pending = ""

    for child in tag.children:
        if isinstance(child, NavigableString):
            pending += str(child)
        elif isinstance(child, Tag) and child.name == "br":
            if pending.strip():
                pieces.append(pending.strip())
            pending = ""
        elif isinstance(child, Tag) and child.name == "img":
            glyph = "{{glyph:" + (child.get("src") or "missing-src") + "}}"
            if pending.strip() or not pieces:
                pending += glyph
            else:
                # A direct glyph after a subtitle belongs to that subtitle.
                pieces[-1] += glyph
        elif isinstance(child, Tag):
            if pending.strip():
                pieces.append(pending.strip())
                pending = ""
            value = _heading_inline_text(child)
            if value:
                # A line break can occur *inside* a single wrapping span.
                # Keep the original run order instead of turning tune + title
                # into one multiline tune (observed in Na Lan's appended ci).
                pieces.extend(part.strip() for part in value.split("\n") if part.strip())
    if pending.strip():
        pieces.append(pending.strip())
    return pieces


def interpret_heading(tag, collection):
    """Return (displayed_tune, title, issues); '又' resolved in conversion."""
    parts = heading_components(tag)
    issues = []
    if not parts:
        return None, None, [{"type": "empty_heading"}]
    if len(parts) > 2:
        issues.append({"type": "ambiguous_heading_parts", "parts": parts})
    first = parts[0]
    # Do not discard a third or later heading fragment silently.
    second = "\n".join(parts[1:]) if len(parts) > 1 else None
    if "贺铸" in collection and second:
        # The small-print portion may also supply an alternate name:
        # "旧调，亦名另一调". Use the primary tune for this minimal Poem.
        # A tune alias dictionary is a separate, later enrichment task.
        alias_note = HE_ZHU_ALIAS_NOTE.fullmatch(second)
        if alias_note:
            return alias_note.group("tune").strip(), first, issues
        return second, first, issues
    return first, second, issues
