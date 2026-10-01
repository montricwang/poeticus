"""Extract annotated ci poems from the scoped author volumes of an EPUB.

The input DOM is interpreted using evidence from the all-volume layout profile;
non-poem editorial material is intentionally excluded from output.
"""
import argparse
import json
import warnings
from dataclasses import asdict
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import epub

from inspect_epub import parse_toc
from schema import Poem, PoemContent
from semantic_rules import (interpret_heading, is_chronology, is_non_poem,
                            is_preface, is_separate_title)

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
        if src:
            img.replace_with(f"{{{{glyph:{src}}}}}")
            image_warnings.append({"type": "inline_image", "html": html_name,
                                   "src": src, "category": category, "status": "unresolved"})
    for br in node.find_all("br"):
        br.replace_with("[EPUB_BR]")
    result = node.get_text("", strip=True).replace("[EPUB_BR]", "\n").strip()
    return result, image_warnings


def extract_sections(book, html_name, collection=""):
    item = book.get_item_with_href(html_name)
    if item is None:
        raise ValueError(f"Not found: {html_name}")
    soup = BeautifulSoup(raw_xhtml(item), "lxml")
    sections = []
    current = None
    discarded = False
    has_verse = False
    for element in soup.find_all(["h2", "p"]):
        if element.name == "h2":
            if current:
                sections.append(current)
            heading = element.get_text("", strip=True)
            discarded = is_non_poem(collection, heading)
            current = None
            has_verse = False
            if discarded:
                continue
            tune, title, issues = interpret_heading(element, collection)
            for image in element.find_all("img"):
                src = image.get("src")
                if not src:
                    continue
                glyph = f"{{{{glyph:{src}}}}}"
                category = "title" if title and glyph in title else "tune"
                issues.append({"type": "inline_image", "html": html_name,
                               "src": src, "category": category, "status": "unresolved"})
            current = {"heading": heading, "tune": tune, "title": title,
                       "text": [], "prefaces": [], "annotations": [],
                       "commentaries": [], "warnings": issues,
                       "html": html_name, "anchor": element.get("id")}
            continue
        if discarded or current is None:
            continue
        preview = element.get_text("", strip=True)
        if not preview and not element.find("img"):
            continue
        if is_chronology(element, preview):
            # Editorial chronological label for the *next* heading.
            continue
        if preview.startswith("◎"):
            category = "annotations"
        elif preview.startswith("◆"):
            category = "commentaries"
        elif not has_verse and is_separate_title(element, collection):
            if current["title"]:
                current["warnings"].append({"type": "multiple_titles", "html": html_name})
            else:
                current["title"] = preview
            continue
        elif not has_verse and is_preface(element, collection):
            category = "prefaces"
        else:
            category = "text"
            has_verse = True
        text, image_warnings = paragraph_text(element, html_name, category)
        if text:
            current[category].append(text)
        current["warnings"].extend(image_warnings)
    if current:
        sections.append(current)
    return sections


def convert_to_poem(section, index, author_slug, author_name, collection, previous_tune=None):
    tune = section["tune"]
    issues = list(section["warnings"])
    if tune == "又":
        if previous_tune:
            tune = previous_tune
        else:
            tune = None
            issues.append({"type": "unresolved_tune_repeat", "html": section["html"],
                           "anchor": section["anchor"]})
    return Poem(
        id=f"{author_slug}-{index:03d}", author=author_name,
        tune=tune, title=section["title"],
        content=PoemContent(
            text=section["text"], prefaces=section["prefaces"],
            annotations=section["annotations"], commentaries=section["commentaries"],
        ),
        collection=collection, source="历代名家词集精华录", warnings=issues,
    )


def find_toc_group(nodes, title):
    for node in nodes:
        if node["title"] == title:
            return node.get("children", [])
        found = find_toc_group(node.get("children", []), title)
        if found is not None:
            return found
    return None


def toc_documents(nodes):
    """Flatten TOC descendants while excluding editorial/front-matter branches."""
    ignored = {"书名页", "目录", "总评", "出版说明", "凡例"}
    for node in nodes:
        title = node["title"].strip()
        if title in ignored or title.startswith(("导读", "导　读")):
            continue
        if node.get("href"):
            yield node["href"].split("#", 1)[0]
        yield from toc_documents(node.get("children", []))


def extract_collection(book, toc, group_name, author_slug, author_name):
    entries = find_toc_group(toc, group_name)
    if entries is None:
        raise ValueError(f"未找到词集：{group_name}")
    files = list(dict.fromkeys(toc_documents(entries)))
    poems = []
    previous_tune = None
    for html_name in files:
        for section in extract_sections(book, html_name, collection=group_name):
            poem = convert_to_poem(section, len(poems) + 1, author_slug,
                                   author_name, group_name, previous_tune)
            if poem.tune and poem.tune != "又":
                previous_tune = poem.tune
            poems.append(poem)
    return poems, files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--toc", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--epub", type=Path,
                        default=Path("data/raw/历代名家词集精华录.epub"))
    args = parser.parse_args()
    book = epub.read_epub(str(args.epub))
    poems, files = extract_collection(book, parse_toc(book.toc), args.toc,
                                      args.slug, args.author)
    if not poems:
        raise RuntimeError("没有抽取到任何作品")
    directory = Path("data/output")
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / (args.slug.replace("-", "_") + ".json")
    output.write_text(json.dumps([asdict(p) for p in poems], ensure_ascii=False,
                                 indent=2), encoding="utf-8")
    print(f"处理 XHTML：{len(files)} 个；抽取作品：{len(poems)} 首；输出：{output}")


if __name__ == "__main__":
    main()
