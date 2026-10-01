import warnings
from pathlib import Path

from ebooklib import epub
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def inspect_html(epub_path: Path, target_html: str):

    book = epub.read_epub(str(epub_path))

    item = book.get_item_with_href(target_html)

    if item is None:
        print("not found:", target_html)
        return

    html = item.get_content()

    soup = BeautifulSoup(html, "lxml")

    targets = (
        "宋孝宗淳熙三年",
        "淳熙丙申至日",
        "淮左名都",
        "淳熙十三年丙午",
    )

    for tag in soup.find_all(["h1", "h2", "p"]):
        text = tag.get_text(" ", strip=True)

        if text in ("扬州慢", "一萼红") or any(text.startswith(t) for t in targets):
            print(
                "\n",
                tag.name,
                repr(text[:100]),
                "\n属性:",
                tag.attrs,
                "\n父节点:",
                tag.parent.name,
                tag.parent.attrs,
            )

    print("=== Headings ===")

    for tag in soup.find_all(["h1", "h2", "h3"]):
        print(tag.name, ":", tag.get_text(strip=True))

    print("\n=== Paragraphs ===")

    for p in soup.find_all("p")[:30]:
        text = p.get_text(strip=True)

        if text:
            print(text)


if __name__ == "__main__":
    epub_path = Path("data/raw/历代名家词集精华录.epub")

    for html_name in ["text00264.html"]:
        print(f"\n===== {html_name} =====")
        inspect_html(epub_path, html_name)
    # 苏轼词作正文从 text00204.html 开始
