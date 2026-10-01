import json
import warnings
from pathlib import Path

from ebooklib import ITEM_DOCUMENT, epub
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def inspect_images(epub_path: Path):
    book = epub.read_epub(str(epub_path))

    images = []

    for item in book.get_items_of_type(ITEM_DOCUMENT):
        html_name = item.get_name()
        soup = BeautifulSoup(item.get_content(), "lxml")

        for img in soup.find_all("img"):
            parent = img.parent

            images.append(
                {
                    "html": html_name,
                    "src": img.get("src"),
                    "alt": img.get("alt"),
                    "title": img.get("title"),
                    "width": img.get("width"),
                    "height": img.get("height"),
                    "parent_tag": parent.name if parent else None,
                    "context": (
                        parent.get_text(" ", strip=True)[:200] if parent else ""
                    ),
                }
            )

    return images


if __name__ == "__main__":
    epub_path = Path("data/raw/历代名家词集精华录.epub")

    result = inspect_images(epub_path)

    output_path = Path("data/reports/epub_images.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"找到图片引用：{len(result)} 处")
    print(f"报告已保存：{output_path}")

    for item in result[:10]:
        print("=" * 60)
        print(f"HTML: {item['html']}")
        print(f"src: {item['src']}")
        print(f"alt: {item['alt']}")
        print(f"context: {item['context']}")
