import argparse
import warnings
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import epub

from ..extractor.extractor import extract_sections
from ..epub.reader import parse_toc

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

DEFAULT_EPUB = Path("data/raw/历代名家词集精华录.epub")
DEFAULT_OUTPUT = Path("data/reports/epub_dom_audit.md")


def collect_links(node):
    """取得目录节点下的所有链接，不包含总评。"""
    if node["title"].strip() == "总评":
        return []

    links = []

    if node.get("href"):
        links.append(node["href"])

    for child in node.get("children", []):
        links.extend(collect_links(child))

    return links


def is_frontmatter(title):
    title = title.replace(" ", "").replace("　", "")
    return title.startswith(("书名页", "目录", "导读", "出版说明", "凡例"))


def analyze_html(book, html_name):
    """检查真实 DOM，并计算当前 Parser 的抽取结果。"""
    item = book.get_item_with_href(html_name)

    if item is None:
        return None

    soup = BeautifulSoup(item.get_content(), "lxml")

    headings = soup.find_all(["h1", "h2", "h3"])
    paragraphs = soup.find_all("p")

    # 与当前 Parser 保持一致
    sections = extract_sections(book, html_name)

    candidates = [
        section for section in sections if section["heading"].strip() != "总评"
    ]

    empty_sections = [
        section["heading"]
        for section in candidates
        if not any(section[key] for key in ("text", "annotations", "commentaries"))
    ]

    # 当前 Parser 遇到首个 h2 后才开始收集 p
    before_h2 = 0
    seen_h2 = False

    for tag in soup.find_all(["h2", "p"]):
        if tag.name == "h2":
            seen_h2 = True
        elif not seen_h2 and tag.get_text(strip=True):
            before_h2 += 1

    # 当前 Parser 可能忽略只有图片、没有文字的段落
    image_only = sum(
        1 for p in paragraphs if p.find("img") and not p.get_text(strip=True)
    )

    # XHTML 中实际可供目录锚点定位的目标
    anchors = {tag["id"] for tag in soup.find_all(attrs={"id": True})}

    anchors.update(tag["name"] for tag in soup.find_all("a", attrs={"name": True}))

    return {
        "h1": len(soup.find_all("h1")),
        "h2": len(soup.find_all("h2")),
        "h3": len(soup.find_all("h3")),
        "p": len(paragraphs),
        "images": len(soup.find_all("img")),
        "candidates": len(candidates),
        "before_h2": before_h2,
        "image_only": image_only,
        "empty_sections": empty_sections,
        "anchors": anchors,
        "heading_samples": [
            f"{tag.name}: {tag.get_text(' ', strip=True)[:45]}" for tag in headings[:3]
        ],
    }


def analyze_group(book, group, cache):
    """汇总一个正集、卷、补遗或其他目录分组。"""
    links = collect_links(group)

    references = defaultdict(list)

    for href in links:
        html_name, _, fragment = href.partition("#")
        references[html_name].append(unquote(fragment))

    total_h2 = 0
    total_candidates = 0
    issues = []

    for html_name, fragments in references.items():
        if html_name not in cache:
            cache[html_name] = analyze_html(book, html_name)

        info = cache[html_name]

        if info is None:
            issues.append(f"`{html_name}`：XHTML 不存在")
            continue

        total_h2 += info["h2"]
        total_candidates += info["candidates"]

        reasons = []

        if info["h2"] == 0:
            reasons.append(
                f"没有 h2（h1={info['h1']}，h3={info['h3']}，p={info['p']}）"
            )

        unique_targets = set(fragments)

        if len(unique_targets) != info["candidates"]:
            reasons.append(
                f"不同目录定位 {len(unique_targets)} 处，"
                f"Parser 候选 {info['candidates']} 条"
            )

        if info["before_h2"]:
            reasons.append(f"首个 h2 前有 {info['before_h2']} 个文字段落")

        if info["image_only"]:
            reasons.append(f"{info['image_only']} 个纯图片段落")

        if info["empty_sections"]:
            examples = "、".join(info["empty_sections"][:3])
            reasons.append(f"空作品段落：{examples}")

        missing_anchors = [
            fragment
            for fragment in fragments
            if fragment and fragment not in info["anchors"]
        ]

        if missing_anchors:
            reasons.append(f"{len(missing_anchors)} 个目录锚点不存在")

        if reasons:
            detail = "；".join(reasons)

            samples = " / ".join(info["heading_samples"])

            issues.append(
                f"- `{html_name}`：{detail}"
                + (f"\n  - 标题示例：{samples}" if samples else "")
            )

    return {
        "links": len(links),
        "files": len(references),
        "h2": total_h2,
        "candidates": total_candidates,
        "issues": issues,
    }


def build_report(book, toc, book_filter=None):
    lines = [
        "# EPUB DOM 结构检查",
        "",
        "检查依据：EPUB 完整目录与实际 XHTML。",
        "",
        "Parser 候选：按照当前 extract_sections() 规则取得的段落，"
        "不代表已经确认的词作数量。",
        "",
        "目录引用数与候选数不一致仅表示需要复核，不能直接判定为漏抽。",
        "",
    ]

    cache = {}
    checked_books = 0
    total_issues = 0

    for volume in toc:
        title = volume["title"]

        if book_filter:
            if title != book_filter:
                continue
        elif "词集" not in title:
            # 本轮只检查词集，暂不检查词话、词谱等
            continue

        checked_books += 1

        lines.extend(
            [
                f"## {title}",
                "",
                "| 目录分组 | 目录链接 | XHTML | h2 | Parser 候选 | 异常文件 |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )

        book_issues = []

        for group in volume.get("children", []):
            name = group["title"]

            if is_frontmatter(name) or name == "总评":
                continue

            result = analyze_group(book, group, cache)
            total_issues += len(result["issues"])

            lines.append(
                f"| {name.replace('|', '/')} "
                f"| {result['links']} "
                f"| {result['files']} "
                f"| {result['h2']} "
                f"| {result['candidates']} "
                f"| {len(result['issues'])} |"
            )

            if result["issues"]:
                book_issues.append((name, result["issues"]))

        lines.append("")

        if book_issues:
            lines.append("### 待复核文件")
            lines.append("")

            for name, issues in book_issues:
                lines.append(f"**{name}**")
                lines.append("")
                lines.extend(issues)
                lines.append("")

    if book_filter and not checked_books:
        raise ValueError(f"找不到分册：{book_filter}")

    lines.extend(
        [
            "---",
            "",
            f"检查分册：{checked_books}",
            f"检查不同 XHTML：{len(cache)}",
            f"异常文件记录：{total_issues}",
            "",
            "注意：同一 XHTML 可能被不同分组引用，因此异常记录数不一定等于不同文件数。",
        ]
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--epub",
        type=Path,
        default=DEFAULT_EPUB,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    parser.add_argument(
        "--book",
        help="仅检查指定分册，必须与 EPUB 顶层目录名称一致",
    )

    args = parser.parse_args()

    book = epub.read_epub(str(args.epub))
    toc = parse_toc(book.toc)

    report = build_report(book, toc, args.book)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")

    print(f"DOM 检查完成：{args.output}")


if __name__ == "__main__":
    main()
