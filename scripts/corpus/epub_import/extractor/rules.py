"""仅适用于这套 EPUB 诗词选本的语义规则。

This module intentionally does not encode suite relationships, tune history or
textual scholarship. Source markup remains available in the private EPUB.
"""
import re
from bs4 import NavigableString, Tag

from .blocks import _class_list, _string_attribute

CHRONOLOGY = re.compile(r"[（(]\d{4}[）)]$")
# 这是选本明确使用的编校缺文标记，不属于作者正文。
# 当前保留原文字样，后续 schema 如何表达是另一层决策。
INLINE_EDITORIAL_GAP = re.compile(r"[（(]\s*以下缺\s*[）)]")
HE_ZHU_ALIAS_NOTE = re.compile(r"^(?P<tune>[^，,]+)[，,]\s*亦名\s*(?P<alias>.+)$")
# 只接受 15 册审计中已经确认的明确文档标签。
EDITORIAL_HEADINGS = {"总评"}
NON_POEMS = {"欧阳修词集": {"西湖念语"}}

# 2026-10-02 人工核对私人来源后确认：下面两段是 ◆ 评论之后延续的学术评论。
# 规则同时匹配原始 XHTML、作品起始块和段落范围，避免同册甚至同文件中的
# 其他作品被错误套用评论续接。来源版式一旦变化就直接失败，不臆造归属。
VERIFIED_ZHOU_COMMENTARY_RUNS = {
    ("text00241.html", 2): range(20, 39),     # 少年游, 19 paragraphs
    ("text00241.html", 504): range(511, 513),  # 红林檎近, 2 paragraphs
}


def is_verified_zhou_commentary(
    collection: str, html_name: str, work_block: int, block: int,
    classes: set[str],
) -> bool:
    if collection != "周邦彦词集":
        return False
    run = VERIFIED_ZHOU_COMMENTARY_RUNS.get((html_name, work_block))
    if run is None or block not in run:
        return False
    allowed = {"kindle-cn-ref", "kindle-cn-para-no-indent"}
    return not classes or classes <= allowed



def is_inline_styled_span(span: Tag) -> bool:
    """判断 EPUB 标记是否把某个 span 排成与普通正文不同的样式。"""
    return bool(
        _string_attribute(span, "style")
        or any(cls in {"kindle-cn-kai", "kaiti", "small"}
               or cls.startswith("font") for cls in _class_list(span))
    )


# 下面是针对这套商业 EPUB 版式的人工复核证据。
# 不能把所有 font1 都推断成作者自注：它也可能表示编校注释或普通排版。
# 第二个案例目前只是候选，尚未确认作者归属。
INLINE_AUTHOR_NOTE_REVIEWS = {
    ("辛弃疾词集", "text00278.html", 135): "user_identified_author_note",
    ("黄庭坚词集", "text00214.html", 679): "possible_author_note",
}


def is_pagination_kaiti_continuation(span: Tag) -> bool:
    """识别因 EPUB 分页标记而拆开的正文楷体 span。

    Requires an immediately preceding empty page anchor and no meaningful
    content after the span apart from layout <br> nodes. This does not classify
    generic kaiti text or other styled spans as verse.
    """
    if span.name != "span" or "kaiti" not in _class_list(span):
        return False
    previous = span.previous_sibling
    while previous is not None and not str(previous).strip():
        previous = previous.previous_sibling
    if (not isinstance(previous, Tag) or previous.name != "a"
            or not re.fullmatch(
                r"page\d+", _string_attribute(previous, "id") or ""
            ) or previous.get_text("", strip=True)):
        return False
    after = span.next_sibling
    while after is not None:
        if getattr(after, "name", None) == "br" or not str(after).strip():
            after = after.next_sibling
        else:
            return False
    return True


def is_non_poem(collection: str, heading: str) -> bool:
    name = heading.strip()
    return name in EDITORIAL_HEADINGS or name in NON_POEMS.get(collection, set())


def is_chronology(tag: Tag, text: str) -> bool:
    """年代标签属于后续作品，不属于上一首。"""
    return ("kindle-cn-para-no-indent1" in _class_list(tag)
            and bool(CHRONOLOGY.search(text)) and len(text) < 55)


def is_separate_title(tag: Tag, collection: str) -> bool:
    """柳永分册中有些作品题目位于 h2 后的居中楷体段落。"""
    css = set(_class_list(tag))
    return ("柳永" in collection and
            {"kindle-cn-para-center", "kindle-cn-kai"}.issubset(css))


def is_preface(tag: Tag, collection: str) -> bool:
    css = set(_class_list(tag))
    if "kindle-cn-ref2" in css:
        return True
    if "kindle-cn-ref" in css:
        # 某些分册的导读也会使用相同 class，因此这个判断只在作品内部、
        # 第一段正文出现之前应用。
        return True
    if {"kindle-cn-para-2em-indent", "kindle-cn-kai"}.issubset(css):
        return any(x in collection for x in ("苏轼", "辛弃疾", "黄庭坚"))
    return False


def _heading_inline_text(node: Tag) -> str:
    """即使图片字嵌在副标题内部，也保留它在题头中的位置。"""
    pieces: list[str] = []
    for child in node.descendants:
        if isinstance(child, NavigableString):
            pieces.append(str(child))
        elif isinstance(child, Tag) and child.name == "img":
            pieces.append("{{glyph:" + (_string_attribute(child, "src") or "missing-src") + "}}")
        elif isinstance(child, Tag) and child.name == "br":
            pieces.append("\n")
    return "".join(pieces).strip()


def heading_components(tag: Tag) -> list[str]:
    """按来源顺序读取题头片段，并保留行内图片字位置。"""
    pieces: list[str] = []
    pending = ""

    for child in tag.children:
        if isinstance(child, NavigableString):
            pending += str(child)
        elif isinstance(child, Tag) and child.name == "br":
            if pending.strip():
                pieces.append(pending.strip())
            pending = ""
        elif isinstance(child, Tag) and child.name == "img":
            glyph = "{{glyph:" + (_string_attribute(child, "src") or "missing-src") + "}}"
            if pending.strip() or not pieces:
                pending += glyph
            else:
                # 紧跟副标题的直接图片字属于该副标题。
                pieces[-1] += glyph
        elif isinstance(child, Tag):
            if pending.strip():
                pieces.append(pending.strip())
                pending = ""
            value = _heading_inline_text(child)
            if value:
                # 换行可能发生在同一个外层 span 内。
                # 保留原始片段顺序，不能把“词牌 + 题目”误并成多行词牌；
                # 纳兰附录词中已经观察到这种版式。
                pieces.extend(part.strip() for part in value.split("\n") if part.strip())
    if pending.strip():
        pieces.append(pending.strip())
    return pieces


def interpret_heading(
    tag: Tag, collection: str,
) -> tuple[str | None, str | None, str | None, list[dict[str, object]]]:
    """Return (tune, title, yusheng, warnings); '又' resolved later.

    For He Zhu, the outer heading names an author-coined tune (寓声).
    The small-print run identifies the original tune, optionally followed
    by a separate work title after an explicit layout delimiter.
    """
    parts = heading_components(tag)
    issues: list[dict[str, object]] = []
    if not parts:
        return None, None, None, [{"type": "empty_heading"}]
    first = parts[0]
    if "贺铸" in collection and len(parts) >= 2:
        # 支持下面两种版式：
        #   <h2>寓声<span>原调</span><span>作品题目</span></h2>
        #   <h2>寓声<span>原调　作品题目</span></h2>
        # 只按同一片段中明确的全角空格拆分；普通 ASCII 单空格
        # 不能作为拆分词牌的依据。
        detail = parts[1].strip()
        if "　" in detail:
            split = [segment.strip() for segment in re.split(r"　+", detail)
                     if segment.strip()]
        else:
            split = [detail]
        tune_text = split[0]
        titles = split[1:] + parts[2:]
        title = "\n".join(titles) if titles else None
        if len(titles) > 1:
            issues.append({"type": "ambiguous_heading_parts", "parts": parts})
        # Treat '亦名' as a note about the old tune, not a work title.
        # 当前导入器不因此引入通用 cipai_alias 字段。
        alias_note = HE_ZHU_ALIAS_NOTE.fullmatch(tune_text)
        tune = alias_note.group("tune").strip() if alias_note else tune_text
        return tune, title, first, issues
    if len(parts) > 2:
        issues.append({"type": "ambiguous_heading_parts", "parts": parts})
    # 第三个及之后的题头片段不能静默丢弃。
    second = "\n".join(parts[1:]) if len(parts) > 1 else None
    return first, second, None, issues
