"""
Export EPUB XHTML DOM into JSON.

This script only preserves document structure.
It does not infer poem semantics.
"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ebooklib import epub

from ..epub.reader import parse_toc
from ..document.builder import build_document


def find_toc_group(nodes, title):
    for node in nodes:
        if node["title"] == title:
            return node.get("children", [])

        found = find_toc_group(
            node.get("children", []),
            title,
        )

        if found is not None:
            return found

    return None


def toc_documents(nodes):
    """
    Extract XHTML files from TOC.

    Keep the original order.
    """

    for node in nodes:
        if node.get("href"):
            yield node["href"].split("#", 1)[0]

        yield from toc_documents(node.get("children", []))


def raw_xhtml(item):
    """
    Preserve original XHTML.
    """

    content = getattr(
        item,
        "content",
        None,
    )

    if content is None:
        content = item.get_content()

    if isinstance(content, bytes):
        return content.decode("utf-8-sig")

    return content


def dataclass_to_dict(node):
    """
    Convert recursive dataclass into JSON serializable dict.
    """

    return asdict(node)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--toc",
        required=True,
        help="词集目录名称，例如：温庭筠词集",
    )

    parser.add_argument(
        "--epub",
        type=Path,
        default=Path("data/raw/历代名家词集精华录.epub"),
    )

    parser.add_argument(
        "--output",
        type=Path,
    )

    args = parser.parse_args()

    book = epub.read_epub(str(args.epub))

    toc = parse_toc(book.toc)

    entries = find_toc_group(
        toc,
        args.toc,
    )

    if entries is None:
        raise ValueError(f"未找到词集：{args.toc}")

    html_files = list(dict.fromkeys(toc_documents(entries)))

    documents = []

    for html_name in html_files:
        item = book.get_item_with_href(html_name)

        if item is None:
            continue

        document = build_document(
            html_name,
            raw_xhtml(item),
        )

        documents.append(document)

    output = args.output or Path("data/debug/dom") / f"{args.toc}.json"

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            [dataclass_to_dict(doc) for doc in documents],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"导出 XHTML：{len(documents)} 个")

    print(f"输出：{output}")


if __name__ == "__main__":
    main()
