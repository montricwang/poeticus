"""为尚未识别的 EPUB 图片字生成本地短上下文。

单看图片可能无法区分近似的历史汉字字形，因此只导出占位符附近的极短片段。
这是私人报告，不得提交到公开仓库。
"""
import argparse
import json
import re
from pathlib import Path

from backend.data_paths import EPUB_REPORTS_ROOT, READING_RAW_ROOT

from bs4 import BeautifulSoup
from ebooklib import epub

from ..extractor.extractor import raw_xhtml
from .review_glyphs import glyph_sites


def find_contexts(book, sites, *, window=16, max_examples=2):
    if not 1 <= window <= 60 or not 1 <= max_examples <= 10:
        raise ValueError("window 必须在 1..60；max_examples 必须在 1..10")
    results = []
    for index, site in enumerate(sites, 1):
        examples = []
        for name in site["pages"]:
            item = book.get_item_with_href(name)
            if item is None:
                continue
            soup = BeautifulSoup(raw_xhtml(item), "lxml")
            for block in soup.find_all(["h1", "h2", "h4", "p"]):
                if not any(
                    img.get("src") == site["src"]
                    for img in block.find_all("img")
                ):
                    continue
                # 在复制出来的 DOM 上处理，不修改内存中的 EPUB 原对象。
                fragment = BeautifulSoup(str(block), "lxml")
                element = fragment.find(block.name)
                if element is None:
                    continue
                for image in element.find_all("img"):
                    if image.get("src") == site["src"]:
                        image.replace_with("⟦目标字⟧")
                    else:
                        image.replace_with("⟦其他图片字⟧")
                flattened = re.sub(r"\s+", " ", element.get_text("", strip=False))
                marker = "⟦目标字⟧"
                start = 0
                while len(examples) < max_examples:
                    pos = flattened.find(marker, start)
                    if pos < 0:
                        break
                    before = flattened[max(0, pos - window):pos]
                    after = flattened[pos + len(marker):pos + len(marker) + window]
                    examples.append({
                        "html": name,
                        "block_tag": block.name,
                        "before": before,
                        "after": after,
                    })
                    start = pos + len(marker)
                if len(examples) >= max_examples:
                    break
            if len(examples) >= max_examples:
                break
        results.append({
            "index": index,
            "slug": site["slug"],
            "src": site["src"],
            "examples": examples,
        })
    return results


def render_contexts(items):
    rows = [
        "# EPUB 图片字上下文（本地私有，请勿公开提交）",
        "",
        "只展示目标图片字前后少量文字，帮助手工确认异体字、近形字。"
        "这些片段仍属于原 EPUB 的内容，禁止提交公共仓库。",
        "",
    ]
    for item in items:
        rows.append(
            f"## {item['index']:03d} · {item['slug']} · {item['src']}"
        )
        rows.append("")
        if not item["examples"]:
            rows.append("未定位到文字段落中的该图片。")
        for example in item["examples"]:
            rows.append(
                f"- `{example['html']}` / {example['block_tag']}："
                f"……{example['before']}**⟦目标字⟧**{example['after']}……"
            )
        rows.append("")
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epub", type=Path, default=READING_RAW_ROOT / "历代名家词集精华录.epub")
    parser.add_argument("--report", type=Path, default=EPUB_REPORTS_ROOT / "epub_import_preflight.json")
    parser.add_argument("--output", type=Path, default=EPUB_REPORTS_ROOT / "glyph_contexts_private.md")
    parser.add_argument("--window", type=int, default=16)
    parser.add_argument("--max-examples", type=int, default=2)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if report.get("kind") != "private-epub-import-preflight":
        parser.error("报告不是 --all --check 的预检结果")
    book = epub.read_epub(str(args.epub))
    rows = find_contexts(
        book, glyph_sites(report),
        window=args.window, max_examples=args.max_examples,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_contexts(rows), encoding="utf-8")
    unknown = sum(not r["examples"] for r in rows)
    print(f"生成 {len(rows)} 个字形的邻近文字；未找到段落 {unknown} 处")
    print(f"本地私有报告：{args.output}")


if __name__ == "__main__":
    main()
