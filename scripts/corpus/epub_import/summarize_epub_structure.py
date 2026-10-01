import argparse
import json
from pathlib import Path


def collect_hrefs(node):
    """递归收集当前目录节点及其子节点的链接。"""
    hrefs = []

    if node.get("href"):
        hrefs.append(node["href"])

    for child in node.get("children", []):
        hrefs.extend(collect_hrefs(child))

    return hrefs


def unique_html(hrefs):
    """去除 # 锚点，并按首次出现顺序去重。"""
    return list(dict.fromkeys(href.split("#")[0] for href in hrefs))


def format_files(files):
    """避免把几十个文件名全部打印出来。"""
    if len(files) <= 5:
        return ", ".join(files)

    return ", ".join(files[:2]) + " … " + ", ".join(files[-2:])


def check_complete(nodes):
    """防止把旧版截断目录误当成完整目录。"""
    for node in nodes:
        if "truncated" in node.get("title", ""):
            raise ValueError("目录仍被截断，请重新生成完整的 epub_structure.json")

        check_complete(node.get("children", []))


def summarize(data):
    toc = data["toc"]
    check_complete(toc)

    lines = [
        "# EPUB 结构概览",
        "",
        f"- EPUB：{data['file']}",
        f"- XHTML 总数：{len(data['documents'])}",
        f"- 顶层目录项：{len(toc)}",
        "",
        "说明：目录条目不等于作品数量；锚点链接表示多个目录项可能引用同一个 XHTML。",
        "",
    ]

    for book in toc:
        # 总目录不是独立分册
        if book["title"] == "总目录":
            continue

        book_hrefs = collect_hrefs(book)
        book_files = unique_html(book_hrefs)

        lines.extend(
            [
                f"## {book['title']}",
                "",
                f"目录链接：{len(book_hrefs)}；独立 XHTML：{len(book_files)}",
                "",
                "| 分组 | 目录链接 | XHTML | 锚点链接 | 文件示例 |",
                "|---|---:|---:|---:|---|",
            ]
        )

        for section in book.get("children", []):
            hrefs = collect_hrefs(section)
            files = unique_html(hrefs)
            anchors = sum("#" in href for href in hrefs)

            lines.append(
                f"| {section['title']} "
                f"| {len(hrefs)} "
                f"| {len(files)} "
                f"| {anchors} "
                f"| {format_files(files)} |"
            )

        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/reports/epub_structure.json"),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/reports/epub_structure_summary.md"),
    )

    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))

    report = summarize(data)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")

    print(f"结构报告已生成：{args.output}")


if __name__ == "__main__":
    main()
