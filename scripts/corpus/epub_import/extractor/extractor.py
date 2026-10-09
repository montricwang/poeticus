"""从指定作者分册中抽取带结构标记的词作。

DOM 解释规则来自全册版式审计；非作品性的编校材料有意不进入正式输出。
"""

import warnings
from typing import Literal, NotRequired, TypedDict

from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

from .schema import InlineNoteCandidate, Poem, PoemContent
from .blocks import SourceBlock, _class_list, _string_attribute, iter_source_blocks
from .inline_notes import inspect_inline_font1
from .rules import (
    INLINE_EDITORIAL_GAP,
    INLINE_AUTHOR_NOTE_REVIEWS,
    interpret_heading,
    is_chronology,
    is_inline_styled_span,
    is_pagination_kaiti_continuation,
    is_non_poem,
    is_preface,
    is_separate_title,
    is_verified_zhou_commentary,
)

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


class CandidateSection(TypedDict):
    """Temporary EPUB extraction state; no editorial attribution is inferred here."""

    heading: str
    tune: str | None
    title: str | None
    yusheng: str | None
    text: list[str]
    prefaces: list[str]
    annotations: list[str]
    commentaries: list[str]
    inline_notes: list[InlineNoteCandidate]
    unknown: list[dict[str, object]]
    blocks: list[dict[str, object]]
    warnings: list[dict[str, object]]
    html: str
    anchor: str | None
    ordinal: int
    chronology: str | None
    inserted: bool
    author_override: str | None
    zone_override: str | None
    zone: NotRequired[str]


def raw_xhtml(item):
    """保留原始 XHTML，并直接按 UTF-8 解码，不猜测字符集。"""
    raw = getattr(item, "content", None)
    if raw is None:
        raw = item.get_content()
    return raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw


def paragraph_text(
    element: Tag, html_name: str, category: str,
) -> tuple[str, list[dict[str, object]]]:
    """保留 <br> 边界与图片占位符，同时不修改原 DOM。"""
    node = BeautifulSoup(str(element), "lxml").find(element.name)
    if not isinstance(node, Tag):
        raise ValueError("无法定位 EPUB 段落节点")
    image_warnings: list[dict[str, object]] = []
    for img in list(node.find_all("img")):
        src = _string_attribute(img, "src")
        img.replace_with("{{glyph:" + (src or "missing-src") + "}}")
        image_warnings.append(
            {
                "type": "inline_image" if src else "missing_image_src",
                "html": html_name,
                "src": src,
                "category": category,
                "status": "unresolved",
            }
        )
    for br in node.find_all("br"):
        br.replace_with("[EPUB_BR]")
    result = node.get_text("", strip=True).replace("[EPUB_BR]", "\n").strip()
    return result, image_warnings


def extract_sections(
    book, html_name: str, collection: str = "",
) -> list[CandidateSection]:
    """把一个 XHTML 转换为带可追踪块证据的候选作品。

    注释之后的未知段落不能静默归入正文；证据与未解决文本继续保留在
    临时 section 与结构化 warning 中。
    """
    item = book.get_item_with_href(html_name)
    if item is None:
        raise ValueError(f"Not found: {html_name}")
    soup = BeautifulSoup(raw_xhtml(item), "lxml")
    sections: list[CandidateSection] = []
    current: CandidateSection | None = None
    discarded = False
    skip_region = False
    has_verse = False
    note_category: Literal["annotations", "commentaries"] | None = None
    category: Literal["text", "prefaces", "annotations", "commentaries"]
    note_classes = None
    note_style = None
    awaiting_supplement = False
    chronology = None
    local_author = None
    local_zone = None

    def add_evidence(
        section: CandidateSection, block: SourceBlock,
        role: str, text: str = "",
    ) -> None:
        section["blocks"].append({**block.location(), "role": role, "text": text})

    source_blocks = list(iter_source_blocks(soup, html_name))
    for block_index, block in enumerate(source_blocks):
        element = block.element
        preview = block.text
        if block.tag == "h1":
            # 同一个 XHTML 内的 h1 可能切换作者，因此读取散文或下一位作者作品前，
            # 必须先结束上一首候选作品。
            if current is not None:
                if current["inserted"] and not current["author_override"]:
                    current["warnings"].append({
                        "type": "missing_inserted_author", "html": html_name,
                        "block": current["ordinal"],
                    })
                sections.append(current)
                current = None
            has_verse = False
            note_category = None
            note_classes = None
            note_style = None
            awaiting_supplement = False
            heading_name = "".join(preview.split())
            scoped = {
                name for label, name in VOLUME_AUTHORS.get(collection, {}).items()
                if heading_name in ("".join(label.split()), name)
            }
            if len(scoped) == 1:
                local_author = scoped.pop()
                skip_region = False
                discarded = False
                local_zone = "main"
            elif "存疑" in preview:
                local_zone = "doubtful"
                skip_region = False
                discarded = False
            elif "补遗" in preview or "辑佚" in preview:
                local_zone = "supplement"
                skip_region = False
                discarded = False
            elif preview.startswith(("导读", "导　读", "总评", "词论")):
                skip_region = True
                discarded = True
            else:
                skip_region = False
                discarded = False
            continue
        is_supplement_heading = (
            "纳兰" in collection and block.tag == "h4"
            and "kindle-cn-heading4" in block.classes
        )
        if block.tag == "h2" or is_supplement_heading:
            if current is not None:
                if current["inserted"] and not current["author_override"]:
                    current["warnings"].append({
                        "type": "missing_inserted_author", "html": html_name,
                        "block": current["ordinal"]
                    })
                sections.append(current)
            if awaiting_supplement and not is_supplement_heading and sections:
                sections[-1]["warnings"].append({
                    "type": "orphan_supplement_marker", "html": html_name
                })
            discarded = skip_region or (
                block.tag == "h2" and is_non_poem(collection, preview)
            )
            current = None
            has_verse = False
            note_category = None
            note_classes = None
            note_style = None
            awaiting_supplement = False
            if discarded:
                continue
            tune, title, yusheng, issues = interpret_heading(element, collection)
            for image in element.find_all("img"):
                src = _string_attribute(image, "src")
                glyph = "{{glyph:" + (src or "missing-src") + "}}"
                category = ("yusheng" if yusheng and glyph in yusheng
                            else "title" if title and glyph in title
                            else "tune")
                issues.append({
                    "type": "inline_image" if src else "missing_image_src",
                    "html": html_name, "src": src,
                    "category": category, "status": "unresolved"
                })
            if is_supplement_heading:
                issues.append({
                    "type": "inserted_author_work", "html": html_name,
                    "block": block.ordinal
                })
            current = {
                "heading": preview, "tune": tune, "title": title,
                "yusheng": yusheng,
                "text": [], "prefaces": [], "annotations": [],
                "commentaries": [], "inline_notes": [],
                "unknown": [], "blocks": [],
                "warnings": issues, "html": html_name,
                "anchor": block.anchor, "ordinal": block.ordinal,
                "chronology": chronology, "inserted": is_supplement_heading,
                "author_override": None if is_supplement_heading else local_author,
                "zone_override": local_zone,
            }
            add_evidence(current, block, "work_start", preview)
            continue
        if block.tag != "p":
            continue
        if is_chronology(element, preview):
            note_classes = None  # A chronology breaks note adjacency.
            chronology = preview
            # 年代标题属于后续作品，不属于上一首。
            if current is not None:
                add_evidence(current, block, "chronology_for_next_work", preview)
            continue
        if "纳兰" in collection and preview == "【附】":
            note_classes = None  # A new author/work marker is a hard boundary.
            awaiting_supplement = True
            if current is not None:
                add_evidence(current, block, "inserted_work_marker", preview)
            continue
        if discarded or current is None:
            continue
        classes = set(block.classes)
        if not preview and not element.find("img"):
            if ("李清照" in collection and has_verse and note_category is None
                    and "kindle-cn-poem-center" in classes):
                current["text"].append("")  # explicit stanza/part separator
                add_evidence(current, block, "stanza_separator")
            else:
                add_evidence(current, block, "layout_only")
            continue
        if "page-break" in classes:
            add_evidence(current, block, "layout_only")
            continue
        if any("picture-txt" in css for css in classes):
            add_evidence(current, block, "figure_caption", preview)
            note_classes = None  # prevents merging across a figure boundary
            continue
        if current["inserted"] and not has_verse and not current["author_override"]:
            if "kindle-cn-para-right" in classes:
                current["author_override"] = preview
                add_evidence(current, block, "inserted_author", preview)
                continue
            # 纳兰附录中的真实版式有时会在 h4 与右对齐三字署名之间
            # 放一个无样式段落。这个段落应单独视为小序而不是正文，
            # 否则 has_verse 会阻止后续署名识别。
            next_block = next((candidate for candidate in source_blocks[block_index + 1:]
                               if candidate.tag != "p" or candidate.text), None)
            if (next_block and next_block.tag == "p"
                    and "kindle-cn-para-right" in next_block.classes
                    # 2–6 个汉字的人名可以合理视为署名；
                    # 较长的右对齐词句不能据此当成署名。
                    and 2 <= len(next_block.text.strip()) <= 6
                    and all("\u3400" <= ch <= "\u9fff" or ch == "·"
                            for ch in next_block.text.strip())
                    and not preview.startswith(("◎", "◆"))):
                # 原书中这个独立 p 位于居中的 h4 词牌/题头之下、
                # 作者署名之上。这个编排位置足以支持把它识别为短小题序，
                # 即使内容是在说明赠答对象。不要拆分句子，也不要覆盖 h4 里的题目。
                text, image_warnings = paragraph_text(element, html_name, "prefaces")
                current["warnings"].extend(image_warnings)
                if text:
                    current["prefaces"].append(text)
                add_evidence(current, block, "inserted_preface", text)
                continue
        if preview.startswith("◎"):
            category = "annotations"
        elif preview.startswith("◆"):
            category = "commentaries"
        elif not has_verse and is_separate_title(element, collection):
            if current["title"]:
                current["warnings"].append({
                    "type": "multiple_titles", "html": html_name,
                    "block": block.ordinal
                })
            else:
                current["title"] = preview
            add_evidence(current, block, "separate_title", preview)
            continue
        elif not has_verse and is_preface(element, collection):
            category = "prefaces"
        elif note_category is not None:
            # 只有当前段落的直接标记与紧邻上一条注评一致时，才可信地视为续段。
            # 遇到不同 class/style、插图或文档边界时都不能跨过去推断。
            matching_markup = (
                block.classes == note_classes
                and element.get("style", "") == note_style
            )
            text, image_warnings = paragraph_text(element, html_name, note_category)
            current["warnings"].extend(image_warnings)
            verified_commentary = (
                note_category == "commentaries"
                and is_verified_zhou_commentary(
                    collection, html_name, current["ordinal"],
                    block.ordinal, classes,
                )
            )
            if (matching_markup or verified_commentary) and current[note_category]:
                current[note_category][-1] += "\n" + text
                current["warnings"].append({
                    "type": (
                        "verified_commentary_continuation"
                        if verified_commentary else "inferred_note_continuation"
                    ),
                    **block.location(), "category": note_category,
                })
                add_evidence(
                    current, block,
                    ("verified_commentary_continuation"
                     if verified_commentary else "note_continuation"), text,
                )
            else:
                current["unknown"].append({**block.location(), "text": text})
                note_classes = None  # Only adjacent blocks may be continued.
                current["warnings"].append({
                    "type": "unclassified_after_notes", **block.location(),
                    "text": text
                })
                add_evidence(current, block, "unknown", text)
            continue
        elif has_verse and classes.intersection({
            "kindle-cn-ref", "kindle-cn-ref1", "kindle-cn-ref2"
        }):
            # 正文之后使用 reference 样式的材料不能自动归入正文。
            text, image_warnings = paragraph_text(element, html_name, "unknown")
            current["warnings"].extend(image_warnings)
            current["unknown"].append({**block.location(), "text": text})
            current["warnings"].append({
                "type": "ambiguous_reference_after_verse",
                **block.location(), "text": text,
            })
            add_evidence(current, block, "unknown", text)
            continue
        else:
            category = "text"
            has_verse = True

        text, image_warnings = paragraph_text(element, html_name, category)
        if text:
            current[category].append(text)
        current["warnings"].extend(image_warnings)
        add_evidence(current, block, category, text)
        if category == "text" and text:
            records, inline_issues = inspect_inline_font1(
                element, text, block, collection, current["tune"],
                len(current["text"]) - 1,
            )
            current["inline_notes"].extend(records)
            current["warnings"].extend(inline_issues)
        if category in ("annotations", "commentaries"):
            note_category = category
            note_classes = block.classes
            note_style = element.get("style", "")
        elif category == "text":
            note_category = None
        if category == "text":
            # 即使阅读器里看起来与普通文本一样，也要识别显式的编校缺文标记。
            # 当前完整保留原段落；未来带版本意识的 schema 可能单独渲染缺文。
            # offset 与导出时使用同一份 paragraph_text() 扁平文本。
            matches = list(INLINE_EDITORIAL_GAP.finditer(text))
            # 同一段存在多个相同标记时，无法可靠把来源 span 对应到扁平文本 offset；
            # 这种情况下不要臆造包含关系。
            styled_containment = (
                any(
                    is_inline_styled_span(span)
                    and INLINE_EDITORIAL_GAP.search(span.get_text("", strip=True))
                    for span in element.find_all("span")
                ) if len(matches) == 1 else None
            )
            for match in matches:
                current["warnings"].append({
                    "type": "inline_editorial_gap",
                    **block.location(),
                    "category": "text",
                    "start": match.start(), "end": match.end(),
                    "marker": match.group(0),
                    "inside_styled_span": styled_containment,
                    "status": "retained_in_body_pending_schema",
                })
            # 两处来源位置已经人工检查：辛弃疾的一处作者自注，以及黄庭坚的一处候选自注。
            # 两者目前都单独追踪，但绝不从正文段落里直接删除。
            # 将来如果引入结构化行内注记 schema，再决定如何无损地从阅读正文中分离。
            note_review = INLINE_AUTHOR_NOTE_REVIEWS.get(
                (collection, html_name, block.ordinal)
            )
            note_recognized = False
            if (note_review and current["tune"] in {"西江月", "醉落魄"}):
                note_spans = [
                    span for span in element.find_all("span")
                    if "font1" in _class_list(span)
                ]
                if len(note_spans) == 1:
                    note_text = note_spans[0].get_text("", strip=True)
                    if note_text and text.count(note_text) == 1:
                        first = text.index(note_text)
                        current["warnings"].append({
                            "type": ("inline_author_note"
                                     if note_review == "user_identified_author_note"
                                     else "inline_author_note_candidate"),
                            **block.location(),
                            "category": "text",
                            "start": first, "end": first + len(note_text),
                            "text": note_text,
                            "origin": ("author"
                                       if note_review == "user_identified_author_note"
                                       else "unverified"),
                            "status": "retained_in_body_pending_schema",
                        })
                        note_recognized = True
            # 某些分册会用单个 span 包住整段正文，这只是正常排版容器，不是行内注释。
            # 只有普通文本与特殊样式混排，或存在多个样式 run 时，才继续进入复核。
            significant_children = [child for child in element.children
                                    if getattr(child, "name", None)
                                    or str(child).strip()]
            whole_paragraph_span = (
                len(significant_children) == 1
                and getattr(significant_children[0], "name", None) == "span"
            )
            if not whole_paragraph_span:
                for span in element.find_all("span"):
                    # EPUB 分页造成的正文拆分不能误报为注释；
                    # 已经按来源单独核过的 font1 注记也不要再生成通用样式 warning。
                    if is_pagination_kaiti_continuation(span):
                        continue
                    if note_recognized and "font1" in _class_list(span):
                        continue
                    if is_inline_styled_span(span):
                        current["warnings"].append({
                            "type": "inline_body_style_review", **block.location()
                        })
                        break
    if current is not None:
        if current["inserted"] and not current["author_override"]:
            current["warnings"].append({
                "type": "missing_inserted_author", "html": html_name,
                "block": current["ordinal"]
            })
        sections.append(current)
    return sections


def convert_to_poem(
    section: CandidateSection, index: int, author_slug: str,
    author_name: str, collection: str, previous_tune: str | None = None,
) -> Poem:
    tune = section["tune"]
    issues = list(section["warnings"])
    if tune == "又":
        if previous_tune:
            tune = previous_tune
        else:
            tune = None
            issues.append({
                "type": "unresolved_tune_repeat",
                "html": section["html"], "anchor": section["anchor"],
                "block": section.get("ordinal")
            })
    if not section["text"]:
        issues.append({
            "type": "empty_body", "html": section["html"],
            "block": section.get("ordinal")
        })
    if section.get("zone") == "doubtful":
        issues.append({
            "type": "doubtful_attribution", "html": section["html"],
            "block": section.get("ordinal")
        })
    # 没有署名的插入作品绝不能默认归给该分册主作者。
    safe_author = section.get("author_override") or author_name
    if section.get("inserted") and not section.get("author_override"):
        safe_author = ""
    return Poem(
        id=f"{author_slug}-{index:03d}",
        author=safe_author,
        cipai=tune, title=section["title"],
        yusheng_title=section.get("yusheng"),
        content=PoemContent(
            text=section["text"], prefaces=section["prefaces"],
            annotations=section["annotations"],
            commentaries=section["commentaries"],
            inline_notes=section.get("inline_notes", []),
        ),
        collection=collection, source="历代名家词集精华录",
        warnings=issues,
    )


def find_toc_group(nodes, title):
    for node in nodes:
        if node["title"] == title:
            return node.get("children", [])
        found = find_toc_group(node.get("children", []), title)
        if found is not None:
            return found
    return None


# 三个多作者分册使用 TOC 子节点确定作者。
# 绝不能从正文、词牌或前一个 EPUB 文件推断作者。
VOLUME_AUTHORS = {
    "温庭筠词集·韦庄词集": {
        "温庭筠词集": "温庭筠", "韦庄词集": "韦庄"
    },
    "李煜词集（附：李璟词集 冯延巳词集）": {
        "李煜词集": "李煜", "李璟词集": "李璟",
        "冯延巳词集": "冯延巳"
    },
    "晏殊词集·晏幾道词集": {
        "晏殊词集": "晏殊", "晏幾道词集": "晏幾道"
    },
}

SKIP_TOC = {"书名页", "目录", "总评", "出版说明", "凡例", "附录"}


def toc_file_contexts(nodes, group_name, default_author):
    """遍历 TOC 分支，同时保留作者与书目分区信息。"""
    authors = VOLUME_AUTHORS.get(group_name, {})

    def visit(entries, author, zone):
        for node in entries:
            title = node["title"].strip()
            if title in SKIP_TOC or title.startswith(("导读", "导　读")):
                continue
            scoped_author = authors.get(title, author)
            scoped_zone = zone
            if "存疑" in title:
                scoped_zone = "doubtful"
            elif "补遗" in title or "辑佚" in title:
                scoped_zone = "supplement"
            elif title.startswith("附录"):
                scoped_zone = "appendix"
            href = node.get("href")
            if href:
                yield href.split("#", 1)[0], scoped_author, scoped_zone
            yield from visit(node.get("children", []), scoped_author, scoped_zone)

    yield from visit(nodes, default_author, "main")


def toc_documents(nodes):
    """兼容旧调用：拍平 TOC，并省略编校分支。"""
    for name, _, _ in toc_file_contexts(nodes, "", ""):
        yield name


def extract_collection(book, toc, group_name, author_slug, author_name):
    entries = find_toc_group(toc, group_name)
    if entries is None:
        raise ValueError(f"未找到词集：{group_name}")
    file_context = {}
    conflicts = {}
    for file_name, author, zone in toc_file_contexts(
        entries, group_name, author_name
    ):
        previous = file_context.get(file_name)
        if previous is not None and previous != (author, zone):
            conflicts.setdefault(file_name, {previous}).add((author, zone))
        else:
            file_context.setdefault(file_name, (author, zone))
    files = list(file_context)
    poems = []
    # 前一个词牌同时属于特定作者与特定编校区域，
    # 这样可防止插入作者的词牌泄漏到主作者作品。
    previous_tunes = {}
    for html_name in files:
        author, zone = file_context[html_name]
        if html_name in conflicts:
            contexts = conflicts[html_name]
            if len({owner for owner, _ in contexts}) > 1:
                author = ""  # Unresolvable without an in-document author marker.
            if len({area for _, area in contexts}) > 1:
                zone = "unknown"
        for section in extract_sections(book, html_name, collection=group_name):
            section["zone"] = section.get("zone_override") or zone
            effective_author = section.get("author_override") or (
                "" if section.get("inserted") else author
            )
            key = effective_author, section["zone"]
            previous_tune = previous_tunes.get(key)
            if html_name in conflicts:
                section["warnings"].append({
                    "type": "ambiguous_toc_attribution", "html": html_name
                })
            poem = convert_to_poem(
                section, len(poems) + 1, author_slug, effective_author,
                group_name, previous_tune,
            )
            if poem.cipai and effective_author:
                previous_tunes[key] = poem.cipai
            poems.append(poem)
    return poems, files
