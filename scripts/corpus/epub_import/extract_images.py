import warnings
from pathlib import Path, PurePosixPath


from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import epub

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def extract_referenced_images(
    epub_path: Path,
    html_name: str,
    output_dir: Path,
    only_srcs: set[str] | None = None,
):
    book = epub.read_epub(str(epub_path))

    html_item = book.get_item_with_href(html_name)

    if html_item is None:
        raise ValueError(f"Not found: {html_name}")

    soup = BeautifulSoup(html_item.get_content(), "lxml")

    output_dir.mkdir(parents=True, exist_ok=True)

    extracted = set()

    for img in soup.find_all("img"):
        src = img.get("src")

        if not src:
            continue

        image_path = str(PurePosixPath(html_name).parent / PurePosixPath(src))

        if only_srcs is not None and src not in only_srcs:
            continue

        image_item = book.get_item_with_href(image_path)

        if image_item is None:
            print(f"找不到图片：{image_path}")
            continue

        filename = PurePosixPath(image_path).name
        output_path = output_dir / filename

        output_path.write_bytes(image_item.get_content())
        extracted.add(image_path)

        print(f"提取：{filename}")

    print(f"\n共提取 {len(extracted)} 张不同图片")


if __name__ == "__main__":
    extract_referenced_images(
        epub_path=Path("data/raw/历代名家词集精华录.epub"),
        html_name="text00005.html",
        output_dir=Path("data/raw/extracted_images/text00005"),
    )
