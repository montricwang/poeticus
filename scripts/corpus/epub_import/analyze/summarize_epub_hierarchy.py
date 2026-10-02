import argparse
import json
import re
from pathlib import Path


def author_from_title(title):
    """识别明确写成「某某词集」的作者分组。"""
    match = re.fullmatch(r"([\u3400-\u9fff]{2,6})词集", title)
    return match.group(1) if match else None


def is_frontmatter(title):
    """册级资料，不归入某位作者的作品。"""
    normalized = title.replace(" ", "").replace("　", "")
    return normalized.startswith(("书名页", "目录", "导读", "出版说明", "凡例"))


def is_special(title):
    """单独呈现的补充材料。"""
    return any(word in title for word in ("总评", "存疑", "补遗", "辑佚", "附录"))


def collect_hrefs(node):
    """递归取得节点下全部目录链接。"""
    hrefs = []

    if node.get("href"):
        hrefs.append(node["href"])

    for child in node.get("children", []):
        hrefs.extend(collect_hrefs(child))

    return hrefs


def describe(nodes):
    """统计链接数、独立 XHTML 数和锚点数。"""
    hrefs = []

    for node in nodes:
        hrefs.extend(collect_hrefs(node))

    files = list(dict.fromkeys(href.split("#")[0] for href in hrefs))

    anchors = sum("#" in href for href in hrefs)

    if not files:
        file_info = "无文件"

    elif len(files) <= 3:
        file_info = ", ".join(files)

    else:
        file_info = f"{files[0]} … {files[-1]}"

    return f"{len(hrefs)} 条目录链接，{len(files)} XHTML，{anchors} 个锚点；{file_info}"


def render_part(lines, title, node):
    """输出作者下面的一卷、正集或补充材料。"""
    children = node.get("children", [])

    # 作者词集下通常直接列出大量作品。
    # 如果还混有明确标出的总评等项目，就分开统计。
    if title == "正集" and children:
        ordinary = [child for child in children if not is_special(child["title"])]

        special = [child for child in children if is_special(child["title"])]

        if ordinary:
            lines.append(f"  - 正集：{describe(ordinary)}")

        for child in special:
            lines.append(f"  - {child['title']}：{describe([child])}")
    else:
        lines.append(f"  - {title}：{describe([node])}")


def summarize_book(book):
    """按目录顺序整理一册书中的作者及其分组。"""
    lines = [f"## {book['title']}", ""]

    lines.append(f"全册：{describe([book])}")
    lines.append("")

    frontmatter = []
    other_sections = []
    authors = []

    # 单作者词集可从分册标题推定作者。
    book_author = author_from_title(book["title"])

    current = None

    if book_author:
        current = {
            "name": book_author,
            "origin": "书名推定",
            "parts": [],
        }
        authors.append(current)

    for section in book.get("children", []):
        title = section["title"]
        detected_author = author_from_title(title)

        if detected_author:
            if (
                current is not None
                and current["name"] == detected_author
                and not current["parts"]
            ):
                # 已从书名推定同一作者，直接升级确认
                current["origin"] = "目录明示"
                current["parts"].append(("正集", section))
            else:
                current = {
                    "name": detected_author,
                    "origin": "目录明示",
                    "parts": [("正集", section)],
                }
                authors.append(current)

        elif is_frontmatter(title):
            frontmatter.append(section)

        elif current is not None:
            # 根据目录顺序暂时归到最近的作者。
            current["parts"].append((title, section))

        else:
            other_sections.append(section)

    if frontmatter:
        lines.append("册级资料：" + "、".join(node["title"] for node in frontmatter))
        lines.append("")

    for author in authors:
        lines.append(f"### {author['name']}（{author['origin']}）")
        lines.append("")

        for title, node in author["parts"]:
            render_part(lines, title, node)

        lines.append("")

    # 词史、词话、词谱等不一定包含作者词集分组。
    if other_sections:
        lines.append("### 其他目录分组")
        lines.append("")

        for node in other_sections:
            lines.append(f"- {node['title']}：{describe([node])}")

        lines.append("")

    return "\n".join(lines)


def check_complete(nodes):
    """拒绝使用被截断的旧版目录。"""
    for node in nodes:
        if "truncated" in node.get("title", ""):
            raise ValueError("目录存在截断内容，请重新生成完整结构报告")

        check_complete(node.get("children", []))


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
        default=Path("data/reports/epub_hierarchy.md"),
    )

    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    toc = data["toc"]

    check_complete(toc)

    sections = [
        "# EPUB 分册与作品层级",
        "",
        "注意：部分作者归属根据书名和目录顺序推定，尚未通过 XHTML 正文验证。",
        "",
    ]

    for book in toc:
        if book["title"] == "总目录":
            continue

        sections.append(summarize_book(book))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(sections),
        encoding="utf-8",
    )

    print(f"层级报告已生成：{args.output}")


if __name__ == "__main__":
    main()
