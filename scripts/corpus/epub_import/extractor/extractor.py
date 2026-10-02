"""Extract annotated ci poems from the scoped author volumes of an EPUB.

The input DOM is interpreted using evidence from the all-volume layout profile;
non-poem editorial material is intentionally excluded from output.
"""

import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .schema import Poem, PoemContent
from .blocks import iter_source_blocks
from .rules import (
    INLINE_EDITORIAL_GAP,
    interpret_heading,
    is_chronology,
    is_inline_styled_span,
    is_non_poem,
    is_preface,
    is_separate_title,
    is_verified_zhou_commentary,
)

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def raw_xhtml(item):
    """Preserve the original XHTML and decode Chinese without charset guessing."""
    raw = getattr(item, "content", None)
    if raw is None:
        raw = item.get_content()
    return raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw


def paragraph_text(element, html_name, category):
    """Keep <br> boundaries and image placeholders without mutating the DOM."""
    node = BeautifulSoup(str(element), "lxml").find(element.name)
    image_warnings = []
    for img in list(node.find_all("img")):
        src = img.get("src")
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


def extract_sections(book, html_name, collection=""):
    """Convert one XHTML into candidate works with traceable block evidence.

    Unknown post-note paragraphs must not silently become verse. Evidence and
    unresolved text remain in temporary sections and structured warnings.
    """
    item = book.get_item_with_href(html_name)
    if item is None:
        raise ValueError(f"Not found: {html_name}")
    soup = BeautifulSoup(raw_xhtml(item), "lxml")
    sections = []
    current = None
    discarded = False
    skip_region = False
    has_verse = False
    note_category = None
    note_classes = None
    note_style = None
    awaiting_supplement = False
    chronology = None
    local_author = None
    local_zone = None

    def add_evidence(section, block, role, text=""):
        section["blocks"].append({**block.location(), "role": role, "text": text})

    source_blocks = list(iter_source_blocks(soup, html_name))
    for block_index, block in enumerate(source_blocks):
        element = block.element
        preview = block.text
        if block.tag == "h1":
            # An h1 can switch authors within the same XHTML. Close the
            # previous poem before reading prose or the next author's works.
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
            tune, title, issues = interpret_heading(element, collection)
            for image in element.find_all("img"):
                src = image.get("src")
                glyph = "{{glyph:" + (src or "missing-src") + "}}"
                category = "title" if title and glyph in title else "tune"
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
                "text": [], "prefaces": [], "annotations": [],
                "commentaries": [], "unknown": [], "blocks": [],
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
            # A dated heading belongs to subsequent works, not the previous poem.
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
            # Real Na Lan appended works sometimes put an unstyled paragraph
            # between the h4 and a right-aligned three-character byline.
            # Classify that paragraph as a separate preface, not verse:
            # otherwise has_verse prevents the byline from being recognized.
            next_block = next((candidate for candidate in source_blocks[block_index + 1:]
                               if candidate.tag != "p" or candidate.text), None)
            if (next_block and next_block.tag == "p"
                    and "kindle-cn-para-right" in next_block.classes
                    # A 2-6-character Chinese name is credible as a byline;
                    # a long right-aligned verse paragraph is not.
                    and 2 <= len(next_block.text.strip()) <= 6
                    and all("\u3400" <= ch <= "\u9fff" or ch == "·"
                            for ch in next_block.text.strip())
                    and not preview.startswith(("◎", "◆"))):
                # In the source volume the independent p lies *below* the
                # centered h4 tune/heading, but above the author's signature.
                # Editorial placement identifies it as a short prefatory
                # note (题序), even if it describes whom the poem addresses.
                # Do not split its sentences or overwrite a title in h4.
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
            # Continuation is credible only when the direct paragraph markup
            # matches the immediately previous note. Do not infer across a
            # different class/style, an illustration, or a document boundary.
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
            # Reference-styled material after verse is not automatically verse.
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
        if category in ("annotations", "commentaries"):
            note_category = category
            note_classes = block.classes
            note_style = element.get("style", "")
        elif category == "text":
            note_category = None
        if category == "text":
            # Detect an explicit *editorial* lacuna marker even when its span
            # looks identical in a reader. Keep the exact paragraph intact:
            # a future edition-aware schema may render the missing segment.
            # Offsets use the same flattened paragraph_text() that we export.
            matches = list(INLINE_EDITORIAL_GAP.finditer(text))
            # With multiple identical markers, source-to-flattened offsets
            # cannot be assigned to individual spans reliably. Do not invent
            # a containment judgment in that case.
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
            # A lone span wrapping the *entire* verse paragraph is a normal
            # typography container in several volumes, not an inline gloss.
            # Mixed plain/styled text and multiple styled runs remain reviewable.
            significant_children = [child for child in element.children
                                    if getattr(child, "name", None)
                                    or str(child).strip()]
            whole_paragraph_span = (
                len(significant_children) == 1
                and getattr(significant_children[0], "name", None) == "span"
            )
            if not whole_paragraph_span:
                for span in element.find_all("span"):
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
    section, index, author_slug, author_name, collection, previous_tune=None
):
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
    # Never attribute an unsigned inserted work to the volume's main author.
    safe_author = section.get("author_override") or author_name
    if section.get("inserted") and not section.get("author_override"):
        safe_author = ""
    return Poem(
        id=f"{author_slug}-{index:03d}",
        author=safe_author,
        tune=tune, title=section["title"],
        content=PoemContent(
            text=section["text"], prefaces=section["prefaces"],
            annotations=section["annotations"],
            commentaries=section["commentaries"],
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


# The three multi-author volumes use child TOC sections for authorship.
# Never infer the author from a verse, tune name, or a previous EPUB file.
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
    """Walk TOC branches, preserving author and bibliographical section."""
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
    """Compatibility: flatten a TOC and omit editorial branches."""
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
    # The previous tune belongs to a specific author AND editorial area.
    # This prevents an inserted author's tune leaking into the main works.
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
            if poem.tune and effective_author:
                previous_tunes[key] = poem.tune
            poems.append(poem)
    return poems, files
