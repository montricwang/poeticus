"""Profile TOC-linked EPUB XHTML/typography before designing extraction rules.

Outputs aggregate templates and bounded examples; NEVER writes the full source text.
DOM and CSS patterns are evidence, not automatic tune/title/preface labels.
"""

import argparse
import json
import re
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

from bs4 import (
    BeautifulSoup, Comment, Declaration, Doctype, NavigableString,
    ProcessingInstruction, Tag, XMLParsedAsHTMLWarning,
)
from ebooklib import epub

from css_styles import StyleResolver
from inspect_epub import parse_toc

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

EPUB_PATH = Path("data/raw/历代名家词集精华录.epub")
MD_PATH = Path("data/reports/epub_dom_layout_profile.md")
JSON_PATH = Path("data/reports/epub_dom_layout_profile.json")
HEADINGS = {f"h{i}" for i in range(1, 7)}
YEAR_PATTERN = re.compile(r"[（(]\d{4}[）)]$")
SAMPLE_LIMIT = 4
STYLE_KEYS = ("font-family", "font-size", "font-weight", "font-style", "color")
INLINE_TAGS = {"span", "small", "big", "strong", "b", "em", "i", "font", "ruby", "rt", "a", "br", "img", "sup", "sub"}


def gather_links(node):
    if node.get("href"):
        yield node["href"]
    for child in node.get("children", []):
        yield from gather_links(child)


def volume_files(volume):
    """File -> top-level TOC groups; each XHTML is analyzed only once per volume."""
    found = defaultdict(set)
    for group in volume.get("children", []):
        for href in gather_links(group):
            name = unquote(href.split("#", 1)[0])
            if name.lower().endswith((".html", ".xhtml")):
                found[name].add(group["title"])
    if volume.get("href"):
        name = unquote(volume["href"].split("#", 1)[0])
        if name.lower().endswith((".html", ".xhtml")):
            found[name].add("分册")
    return {key: sorted(values) for key, values in found.items()}


def css_class(tag):
    return ".".join(tag.get("class", [])) or "(none)"


def node_label(tag):
    return f"{tag.name}.{css_class(tag)}" if tag.get("class") else tag.name


def compact(text, limit=85):
    text = " ".join(text.split())
    return text[:limit] + ("…" if len(text) > limit else "")


def typography(style):
    return {k: style[k] for k in STYLE_KEYS if k in style}


def content_runs(heading, styles):
    """Preserve each text run's nearest styled element, not get_text() flattening."""
    runs = []
    for node in heading.descendants:
        if isinstance(node, NavigableString):
            value = str(node).strip()
            if not value:
                continue
            owner = node.parent
            style = styles.style(owner)
            runs.append({
                "text": compact(value, 110),
                "element": node_label(owner),
                "style": typography(style),
                "style_sources": {k: styles.provenance(owner).get(k) for k in STYLE_KEYS if k in style},
            })
        elif isinstance(node, Tag) and node.name == "br":
            runs.append({"text": "↵", "element": "br", "style": {}, "style_sources": {}})
        elif isinstance(node, Tag) and node.name == "img":
            runs.append({"text": f"[img:{node.get('src', '')}]", "element": "img", "style": {}, "style_sources": {}})
    return runs


def heading_template(heading, runs, styles):
    """Structural and typographic signature, independent of title wording."""
    root_style = typography(styles.style(heading))
    run_signatures = []
    for run in runs:
        signature = (run["element"], tuple(sorted(run["style"].items())))
        if not run_signatures or run_signatures[-1] != signature:
            run_signatures.append(signature)
    shape = {
        "root": node_label(heading),
        "root_style": root_style,
        "runs": [{"element": x[0], "style": dict(x[1])} for x in run_signatures],
    }
    return json.dumps(shape, ensure_ascii=False, sort_keys=True), shape


def paragraph_feature(tag, text):
    if not text:
        return "纯图片" if tag.find("img") else "空段落"
    if text.startswith("◎"):
        return "◎开头"
    if text.startswith("◆"):
        return "◆开头"
    if len(text) <= 50 and YEAR_PATTERN.search(text):
        return "短句+四位年份"
    return "其他文字"


def add_example(record, example):
    """Keep a few cases, including a contextual '又' or multi-run title."""
    samples = record["samples"]
    if any(x["html"] == example["html"] and x.get("title") == example.get("title") for x in samples):
        return
    if len(samples) < SAMPLE_LIMIT:
        samples.append(example)
    elif example.get("title", "").startswith("又") and not any(x.get("title", "").startswith("又") for x in samples):
        samples[-1] = example


def unhandled_text(soup):
    """Detect text not nested in p or headings, which the existing parser might miss."""
    grouped = Counter()
    samples = {}
    for text in soup.find_all(string=True):
        if (not isinstance(text, NavigableString) or
                isinstance(text, (Comment, Declaration, Doctype, ProcessingInstruction)) or
                not text.strip()):
            continue
        if text.parent.find_parent(["p", *sorted(HEADINGS)]):
            continue
        if text.parent.name in HEADINGS | {"p", "script", "style", "title"}:
            continue
        if text.parent.find_parent(["script", "style", "head"]):
            continue
        name = text.parent.name
        grouped[name] += 1
        samples.setdefault(name, compact(str(text)))
    return grouped, samples


def inspect_document(book, html_name, groups, resolver, templates, paragraphs, coverage):
    item = book.get_item_with_href(html_name)
    if item is None:
        coverage["missing"].append(html_name)
        return
    # EbookLib EpubHtml.get_content() rebuilds the document and may drop the
    # original <head> / CSS links. .content holds the imported XHTML bytes.
    original = getattr(item, "content", None)
    raw = original if original is not None else item.get_content()
    # EPUB XHTML is UTF-8 here. Pass Unicode to Beautiful Soup so a different
    # charset detector cannot silently corrupt short Chinese titles.
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig")
    soup = BeautifulSoup(raw, "lxml")
    styles = resolver.for_document(soup, html_name)
    coverage["files"] += 1
    coverage["linked_css"].update(styles.paths)

    headings = soup.find_all(list(HEADINGS))
    blocks = soup.find_all(["p", *sorted(HEADINGS)])
    coverage["heading_tags"].update(h.name for h in headings)
    heading_seen = False
    for idx, element in enumerate(blocks):
        if element.name in HEADINGS:
            if element.name == "h2":
                heading_seen = True
            runs = content_runs(element, styles)
            key, signature = heading_template(element, runs, styles)
            record = templates.setdefault(key, {"signature": signature, "count": 0, "groups": set(), "samples": []})
            record["count"] += 1
            record["groups"].update(groups)
            add_example(record, {
                "html": html_name,
                "title": compact(element.get_text(" ", strip=True), 130),
                "id": element.get("id"),
                "runs": runs,
            })
            continue
        text = element.get_text(" ", strip=True)
        feature = paragraph_feature(element, text)
        nested = Counter(t.name for t in element.descendants if isinstance(t, Tag) and t.name in INLINE_TAGS)
        style = typography(styles.style(element))
        signature = {"element": node_label(element), "feature": feature, "style": style}
        key = json.dumps(signature, ensure_ascii=False, sort_keys=True)
        record = paragraphs.setdefault(key, {
            "signature": signature, "count": 0, "groups": set(), "before_first_h2": 0,
            "after_heading": 0, "before_heading": 0, "inline_tags": Counter(), "samples": [],
        })
        record["count"] += 1
        record["groups"].update(groups)
        record["inline_tags"].update(nested)
        if not heading_seen:
            record["before_first_h2"] += 1
        if idx > 0 and blocks[idx - 1].name in HEADINGS:
            record["after_heading"] += 1
        if idx + 1 < len(blocks) and blocks[idx + 1].name in HEADINGS:
            record["before_heading"] += 1
        add_example(record, {"html": html_name, "title": compact(text), "inline_tags": dict(nested)})

    stray, examples = unhandled_text(soup)
    coverage["unhandled_tags"].update(stray)
    for name, sample in examples.items():
        coverage["unhandled_samples"].setdefault(name, {"html": html_name, "text": sample})


def finish(records):
    output = []
    for record in sorted(records.values(), key=lambda r: (-r["count"], str(r["signature"]))):
        item = dict(record)
        item["groups"] = sorted(record["groups"])
        if "inline_tags" in item:
            item["inline_tags"] = dict(record["inline_tags"].most_common())
        output.append(item)
    return output


def profile_volume(book, volume, resolver):
    templates, paragraphs = {}, {}
    coverage = {
        "files": 0, "missing": [], "linked_css": set(), "heading_tags": Counter(),
        "unhandled_tags": Counter(), "unhandled_samples": {},
    }
    files = volume_files(volume)
    for html_name, groups in files.items():
        inspect_document(book, html_name, groups, resolver, templates, paragraphs, coverage)
    return {
        "volume": volume["title"],
        "toc_files": len(files),
        "analyzed_files": coverage["files"],
        "missing_files": coverage["missing"],
        "linked_css": sorted(coverage["linked_css"]),
        "heading_tags": dict(coverage["heading_tags"]),
        "heading_templates": finish(templates),
        "paragraph_templates": finish(paragraphs),
        "other_text_tags": dict(coverage["unhandled_tags"].most_common()),
        "other_text_samples": coverage["unhandled_samples"],
    }


def escape_md(s):
    return str(s).replace("|", "\\|").replace("\n", " ").replace("`", "'")


def short_style(style):
    return ", ".join(f"{k}={v}" for k, v in style.items()) or "(未声明)"


def render_md(report):
    lines = [
        "# EPUB DOM 与 CSS 排版画像", "",
        "统计对象：EPUB 目录关联的 XHTML；同一文件在同一分册只扫描一次。", "",
        "提醒：CSS 值仅按静态规则、特异性和继承关系近似求得，不是浏览器实际渲染结果；字体和字号不能单独证明文学语义。", "",
        "## 总览", "",
        "| 分册 | XHTML | 标题总数 | 标题模板 | 段落模板 | CSS |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for v in report["volumes"]:
        lines.append(f"| {escape_md(v['volume'])} | {v['analyzed_files']} | {sum(v['heading_tags'].values())} | {len(v['heading_templates'])} | {len(v['paragraph_templates'])} | {len(v['linked_css'])} |")

    for v in report["volumes"]:
        lines.extend(["", f"## {escape_md(v['volume'])}", "",
                      f"文件：{v['analyzed_files']}；样式表：{', '.join(v['linked_css']) or '无'}", "",
                      "### 标题 DOM + 样式模板", "",
                      "| 模板 | 数量 | 分组 | 子节点 / 排版差异 |",
                      "|---|---:|---|---|"])
        for i, rec in enumerate(v["heading_templates"], 1):
            sig = rec["signature"]
            spans = [f"{x['element']}〔{short_style(x['style'])}〕" for x in sig["runs"]]
            lines.append(f"| H{i}: `{escape_md(sig['root'])}` | {rec['count']} | {escape_md('、'.join(rec['groups'][:5]))} | {escape_md(' → '.join(spans))} |")
        for i, rec in enumerate(v["heading_templates"], 1):
            lines.append(f"\n**H{i} 代表实例**")
            for example in rec["samples"]:
                runs = " / ".join(f"{escape_md(x['text'])} ({escape_md(x['element'])})" for x in example["runs"])
                lines.append(f"- `{example['html']}`：{runs}")
                for run in example["runs"]:
                    if run["style"]:
                        sources = "; ".join(f"{k}: {v} ← {run['style_sources'].get(k)}" for k, v in run["style"].items())
                        lines.append(f"  - {escape_md(run['element'])}：{escape_md(sources)}")
        lines.extend(["", "### 段落模板", "",
                      "| 模板 | 数量 | 首个 h2 前 | 紧接标题 | 紧邻下个标题 | 内嵌标签 | 样例 |",
                      "|---|---:|---:|---:|---:|---|---|"])
        for rec in v["paragraph_templates"]:
            sig = rec["signature"]
            example = rec["samples"][0] if rec["samples"] else {}
            inline = ", ".join(f"{k}:{n}" for k, n in rec["inline_tags"].items())
            lines.append(f"| `{escape_md(sig['element'])}` / {escape_md(sig['feature'])} / {escape_md(short_style(sig['style']))} | {rec['count']} | {rec['before_first_h2']} | {rec['after_heading']} | {rec['before_heading']} | {inline or '-'} | {escape_md(example.get('title', ''))} |")
        if v["other_text_tags"]:
            lines.extend(["", "### 非 p/标题内的文字（需关注）", ""])
            for name, n in v["other_text_tags"].items():
                sample = v["other_text_samples"].get(name, {})
                lines.append(f"- `{name}` {n} 处；`{sample.get('html', '?')}`：{escape_md(sample.get('text', ''))}")
        if v["missing_files"]:
            lines.extend(["", "未找到 XHTML：" + "、".join(v["missing_files"])])
    if report["css_warnings"]:
        lines.extend(["", "## 未完全解释的 CSS", "",
                      "这些情况需要人工复核，不能误认静态样式为最终浏览器样式。", ""])
        lines.extend(f"- {escape_md(w)}" for w in report["css_warnings"])
    return "\n".join(lines) + "\n"


def run(book, toc, book_filter=None):
    resolver = StyleResolver(book)
    volumes = [node for node in toc if node["title"] != "总目录" and
               (book_filter is None or node["title"] == book_filter)]
    if not volumes:
        raise ValueError(f"未找到分册：{book_filter}")
    report = {
        "schema_version": 1,
        "scope": "DOM/CSS structural evidence; not a literary semantic classification",
        "volumes": [profile_volume(book, volume, resolver) for volume in volumes],
        "css_warnings": sorted(resolver.problems),
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epub", type=Path, default=EPUB_PATH)
    parser.add_argument("--output", type=Path, default=MD_PATH, help="Markdown report")
    parser.add_argument("--json-output", type=Path, default=JSON_PATH)
    parser.add_argument("--book", help="仅分析目录中的指定分册")
    args = parser.parse_args()
    book = epub.read_epub(str(args.epub))
    report = run(book, parse_toc(book.toc), args.book)
    for path, content in ((args.output, render_md(report)),
                          (args.json_output, json.dumps(report, ensure_ascii=False, indent=2))):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"报告：{path}")
    print(f"分册：{len(report['volumes'])}；CSS 提醒：{len(report['css_warnings'])}")


if __name__ == "__main__":
    main()