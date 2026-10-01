import json
from dataclasses import asdict
from pathlib import Path
import argparse

from bs4 import BeautifulSoup
from ebooklib import epub
from inspect_epub import parse_toc

from schema import Poem, PoemContent


def extract_sections(book, html_name):
    item = book.get_item_with_href(html_name)

    if item is None:
        raise ValueError(f"Not found: {html_name}")

    soup = BeautifulSoup(item.get_content(), "lxml")

    sections = []

    current = None

    for element in soup.find_all(["h2", "p"]):
        if element.name == "h2":
            if current:
                sections.append(current)

            current = {
                "heading": element.get_text(strip=True),
                "text": [],
                "annotations": [],
                "commentaries": [],
                "warnings": [],
            }

        elif element.name == "p" and current:
            raw_text = element.get_text(strip=True)

            if raw_text:
                category = classify_paragraph(raw_text)

                warnings = preserve_inline_images(
                    element,
                    html_name,
                    category,
                )
                current["warnings"].extend(warnings)

                text = element.get_text(strip=True)
                current[category].append(text)

    if current:
        sections.append(current)

    return sections


def preserve_inline_images(element, html_name, category):
    warnings = []

    for img in element.find_all("img"):
        src = img.get("src")

        if not src:
            continue

        placeholder = f"{{{{glyph:{src}}}}}"
        img.replace_with(placeholder)

        warnings.append(
            {
                "type": "inline_image",
                "html": html_name,
                "src": src,
                "category": category,
                "status": "unresolved",
            }
        )

    return warnings


def classify_paragraph(text):

    if text.startswith("◎"):
        return "annotations"

    if text.startswith("◆"):
        return "commentaries"

    return "text"


def convert_to_poem(section, index, author_slug, author_name, collection):
    return Poem(
        id=f"{author_slug}-{index:03d}",
        author=author_name,
        title_raw=section["heading"],
        content=PoemContent(
            text=section["text"],
            annotations=section["annotations"],
            commentaries=section["commentaries"],
        ),
        collection=collection,
        source="历代名家词集精华录",
        warnings=section["warnings"],
    )


def find_toc_group(nodes, title):
    for node in nodes:
        if node["title"] == title:
            return node.get("children", [])

        found = find_toc_group(node.get("children", []), title)

        if found is not None:
            return found

    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--toc", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--slug", required=True)

    args = parser.parse_args()

    epub_path = Path("data/raw/历代名家词集精华录.epub")
    book = epub.read_epub(str(epub_path))

    # 1. 根据目录定位词集
    toc = parse_toc(book.toc)
    entries = find_toc_group(toc, args.toc)

    if entries is None:
        raise ValueError(f"未找到词集：{args.toc}")

    # 2. 获取 XHTML，去重并保留顺序
    html_names = list(
        dict.fromkeys(
            entry["href"].split("#")[0]
            for entry in entries
            if entry.get("href") and entry["title"] != "总评"
        )
    )

    # 3. 通用作品抽取
    poems = []

    for html_name in html_names:
        sections = extract_sections(book, html_name)

        if not sections:
            print(f"WARNING: {html_name} 未抽取到作品")

        for section in sections:
            if section["heading"].strip() == "总评":
                print(f"跳过非作品：{html_name}（总评）")
                continue

            poem = convert_to_poem(
                section,
                len(poems) + 1,
                args.slug,
                args.author,
                args.toc,
            )
            poems.append(poem)

    if not poems:
        raise RuntimeError("没有抽取到任何作品")

    # 4. 保存 Extraction 结果
    output_dir = Path("data/output")
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = args.slug.replace("-", "_") + ".json"
    output_path = output_dir / filename

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(
            [asdict(p) for p in poems],
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"处理 XHTML：{len(html_names)} 个")
    print(f"抽取作品：{len(poems)} 首")
    print(f"输出文件：{output_path}")
