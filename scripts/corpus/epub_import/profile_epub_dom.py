import argparse
import re
import warnings
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import epub

from inspect_epub import parse_toc

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

EPUB_PATH = Path("data/raw/历代名家词集精华录.epub")
OUTPUT_PATH = Path("data/reports/epub_dom_profile.md")

YEAR_PATTERN = re.compile(r"[（(]\d{4}[）)]$")


def collect_hrefs(node):
    hrefs = []

    if node.get("href"):
        hrefs.append(node["href"])

    for child in node.get("children", []):
        hrefs.extend(collect_hrefs(child))

    return hrefs


def classify_content(tag, text):
    """只识别可观察的文字特征，不直接推断文学含义。"""
    if not text and tag.find("img"):
        return "纯图片"

    if text.startswith("◎"):
        return "◎ 开头"

    if text.startswith("◆"):
        return "◆ 开头"

    if len(text) <= 50 and YEAR_PATTERN.search(text):
        return "短句 + 四位年份"

    if not text:
        return "空段落"

    return "其他文字"


def make_sample(text, html_name):
    text = " ".join(text.split())
    text = text.replace("|", r"\|")

    return f"`{html_name}`：{text[:70]}"


def inspect_document(book, html_name, stats, totals):
    item = book.get_item_with_href(html_name)

    if item is None:
        totals["missing"].append(html_name)
        return

    soup = BeautifulSoup(item.get_content(), "lxml")
    blocks = soup.find_all(["h1", "h2", "h3", "p"])

    seen_h2 = False

    for index, tag in enumerate(blocks):
        if tag.name != "p":
            totals[tag.name] += 1

            if tag.name == "h2":
                seen_h2 = True

            continue

        text = tag.get_text(" ", strip=True)
        css_class = " ".join(tag.get("class", [])) or "无 class"
        feature = classify_content(tag, text)

        # 同一种 class 内，再按文字特征分组
        key = (css_class, feature)

        record = stats[key]
        record["count"] += 1

        if not seen_h2:
            record["before_first_h2"] += 1

        if index > 0 and blocks[index - 1].name == "h2":
            record["after_h2"] += 1

        if index + 1 < len(blocks) and blocks[index + 1].name == "h2":
            record["before_next_h2"] += 1

        sample = make_sample(text, html_name)

        if len(record["samples"]) < 3 and sample not in record["samples"]:
            record["samples"].append(sample)

        totals["p"] += 1


def new_record():
    return {
        "count": 0,
        "before_first_h2": 0,
        "after_h2": 0,
        "before_next_h2": 0,
        "samples": [],
    }


def profile_volume(book, volume):
    hrefs = collect_hrefs(volume)

    html_files = list(
        dict.fromkeys(
            href.split("#")[0]
            for href in hrefs
            if href.split("#")[0].endswith((".html", ".xhtml"))
        )
    )

    stats = defaultdict(new_record)
    totals = {
        "h1": 0,
        "h2": 0,
        "h3": 0,
        "p": 0,
        "missing": [],
    }

    for html_name in html_files:
        inspect_document(book, html_name, stats, totals)

    lines = [
        f"## {volume['title']}",
        "",
        f"XHTML：{len(html_files)}；"
        f"h1：{totals['h1']}；"
        f"h2：{totals['h2']}；"
        f"h3：{totals['h3']}；"
        f"p：{totals['p']}",
        "",
        "| CSS class | 文字特征 | 数量 | 首个 h2 前 | 紧接 h2 | 紧邻下个 h2 |",
        "|---|---|---:|---:|---:|---:|",
    ]

    for (css_class, feature), info in sorted(
        stats.items(),
        key=lambda pair: -pair[1]["count"],
    ):
        lines.append(
            f"| {css_class} "
            f"| {feature} "
            f"| {info['count']} "
            f"| {info['before_first_h2']} "
            f"| {info['after_h2']} "
            f"| {info['before_next_h2']} |"
        )

    lines.extend(["", "### 各类段落样例", ""])

    for (css_class, feature), info in sorted(
        stats.items(),
        key=lambda pair: -pair[1]["count"],
    ):
        lines.append(f"**{css_class} / {feature}**")

        for sample in info["samples"]:
            lines.append(f"- {sample}")

        lines.append("")

    if totals["missing"]:
        lines.append("未找到的 XHTML：" + "、".join(totals["missing"]))
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epub", type=Path, default=EPUB_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--book", help="只分析指定分册")

    args = parser.parse_args()

    book = epub.read_epub(str(args.epub))
    toc = parse_toc(book.toc)

    lines = [
        "# EPUB DOM 特征画像",
        "",
        "按分册统计 XHTML 中的标签、CSS class、文字形态与位置。",
        "",
        "注意：这些是结构特征，不等于已经确认的内容类别。",
        "",
    ]

    matched = 0

    for volume in toc:
        if volume["title"] == "总目录":
            continue

        if args.book and volume["title"] != args.book:
            continue

        matched += 1
        lines.append(profile_volume(book, volume))

    if not matched:
        raise ValueError(f"没有找到分册：{args.book}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(f"DOM 特征报告已生成：{args.output}")
    print(f"分析分册：{matched}")


if __name__ == "__main__":
    main()
