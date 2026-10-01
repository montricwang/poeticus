"""Scoped semantic rules for the *poetry anthologies* in this EPUB.

This module intentionally does not encode suite relationships, tune history or
textual scholarship. Source markup remains available in the private EPUB.
"""
import re
from bs4 import NavigableString, Tag

CHRONOLOGY = re.compile(r"[（(]\d{4}[）)]$")
NON_POEMS = {"欧阳修词集": {"西湖念语"}}


def is_non_poem(collection, heading):
    return heading in NON_POEMS.get(collection, set())


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


def heading_components(tag):
    """Keep text separated by actual child nodes; never guess a tune prefix."""
    pieces = []
    for child in tag.children:
        if isinstance(child, NavigableString):
            value = str(child).strip()
            if value:
                pieces.append(value)
        elif isinstance(child, Tag) and child.name == "img":
            # An image may encode a character continuing the preceding title.
            if child.get("src"):
                glyph = f"{{{{glyph:{child['src']}}}}}"
                if pieces:
                    pieces[-1] += glyph
                else:
                    pieces.append(glyph)
        elif isinstance(child, Tag) and child.name not in ("a", "br"):
            value = child.get_text("", strip=True)
            # Rare headings have an image-based character after the subtitle.
            for image in child.find_all("img"):
                value += f"{{{{glyph:{image.get('src', '')}}}}}"
            if value:
                pieces.append(value)
        elif isinstance(child, Tag) and child.name == "a" and child.get_text(strip=True):
            pieces.append(child.get_text("", strip=True))
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
    second = parts[1] if len(parts) > 1 else None
    if "贺铸" in collection and second:
        # He Zhu altered tune names: the original tune follows as small print.
        return second, first, issues
    return first, second, issues
