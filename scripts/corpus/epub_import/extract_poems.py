import json
from dataclasses import asdict
from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import epub

from schema import Poem, PoemContent


def extract_sections(epub_path: Path, html_name: str):

    book = epub.read_epub(str(epub_path))

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


def convert_to_poem(section, index, author):

    return Poem(
        id=f"{author}-{index:03d}",
        author="温庭筠",
        title_raw=section["heading"],
        content=PoemContent(
            text=section["text"],
            annotations=section["annotations"],
            commentaries=section["commentaries"],
        ),
        collection="温庭筠词集",
        source="历代名家词集精华录",
        warnings=section["warnings"],
    )


if __name__ == "__main__":
    result = extract_sections(
        Path("data/raw/历代名家词集精华录.epub"), "text00005.html"
    )

    poems = []

    for i, section in enumerate(result, start=1):
        poems.append(convert_to_poem(section, i, "wen-tingyun"))

    with open("data/output/wen_tingyun.json", "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in poems], f, ensure_ascii=False, indent=2)

    for item in poems[:3]:
        print("=" * 20)
        print(item.title_raw)

        print("正文:")
        for p in item.content.text[:2]:
            print(p)
