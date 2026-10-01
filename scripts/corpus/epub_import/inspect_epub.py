from pathlib import Path
import argparse
import json

from ebooklib import epub


def inspect_toc(book):

    print("\nTOC:")

    def walk(items, level=0):
        for item in items:
            if isinstance(item, tuple):
                section, children = item
                print("  " * level + section.title)
                walk(children, level + 1)

            else:
                print("  " * level + f"{item.title} -> {item.href}")

    walk(book.toc)


def parse_toc(items):
    result = []

    for item in items:
        if isinstance(item, tuple):
            section, children = item

            result.append({"title": section.title, "children": parse_toc(children)})

        else:
            result.append({"title": item.title, "href": item.href})

    return result


def truncate_toc(nodes, max_children=10):
    """
    截断目录树：
    - 每个节点 children 超过 max_children 时，只保留前 max_children 个
    - 保留一个提示节点说明被截断
    """
    result = []

    for node in nodes:
        new_node = {
            "title": node.get("title"),
            "href": node.get("href"),
            "children": [],
        }

        children = node.get("children", [])

        if len(children) > max_children:
            new_node["children"] = truncate_toc(children[:max_children], max_children)

            new_node["children"].append(
                {
                    "title": f"... truncated ({len(children) - max_children} more children)",
                    "href": None,
                    "children": [],
                }
            )
        else:
            new_node["children"] = truncate_toc(children, max_children)

        result.append(new_node)

    return result


def inspect_epub(epub_path: Path):
    book = epub.read_epub(str(epub_path))

    result = {
        "file": epub_path.name,
        "metadata": {},
        "summary": {},
        "documents": [],
        "toc": [],
    }

    toc = parse_toc(book.toc)

    result["toc"] = truncate_toc(toc, max_children=40)

    title = book.get_metadata("DC", "title")

    if title:
        result["metadata"]["title"] = title[0][0]

    counters = {}

    for item in book.get_items():
        item_type = str(item.get_type())

        counters[item_type] = counters.get(item_type, 0) + 1

        if item_type == "9":  # XHTML
            result["documents"].append(item.get_name())

    result["summary"] = counters

    return result


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument("epub", type=Path, help="Path to epub file")

    parser.add_argument(
        "--output", type=Path, default=Path("data/reports/epub_structure.json")
    )

    args = parser.parse_args()

    report = inspect_epub(args.epub)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("EPUB inspection complete")
    print()
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    print()
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
