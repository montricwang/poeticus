from pathlib import Path

from ebooklib import epub
from bs4 import BeautifulSoup


def inspect_html(epub_path: Path, target_html: str):

    book = epub.read_epub(str(epub_path))

    item = book.get_item_with_href(target_html)

    if item is None:
        print("not found:", target_html)
        return

    html = item.get_content()

    soup = BeautifulSoup(html, "lxml")

    print("=== Headings ===")

    for tag in soup.find_all(["h1", "h2", "h3"]):
        print(tag.name, ":", tag.get_text(strip=True))

    print("\n=== Paragraphs ===")

    for p in soup.find_all("p")[:30]:
        text = p.get_text(strip=True)

        if text:
            print(text)


if __name__ == "__main__":
    inspect_html(Path("data/raw/历代名家词集精华录.epub"), "text00204.html")
    # 苏轼词作正文从 text00204.html 开始
