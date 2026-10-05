"""按图片字核对编号（001、002……）导出私人来源段落。

必须与 review_glyphs.glyph_sites() 使用完全相同的来源顺序，确保每个段落
对应到图版里已经展示的同一张图片。输出含受版权保护正文，只能留在本地，
生成的 HTML 绝不能提交。
"""
import base64
import html
import re
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

from ..extractor.blocks import iter_source_blocks
from ..extractor.extractor import extract_sections, raw_xhtml
from .review_glyphs import _epub_image, glyph_sites


GLYPH_TOKEN = re.compile(r"\[\[GLYPH_(\d{3})\]\]")


def _marked_paragraph(block, source_indexes, target):
    """按与 paragraph_text() 相近的方式扁平化来源，同时保留图片位置。"""
    root = BeautifulSoup(str(block.element), "lxml").find(block.tag)
    for image in root.find_all("img"):
        src = image.get("src", "")
        index = source_indexes.get(src)
        if index is None:
            image.replace_with("[未列入本次预检的图片]")
        else:
            image.replace_with(f"[[GLYPH_{index:03d}]]")
    for br in root.find_all("br"):
        br.replace_with("[EPUB_BR]")
    flat = root.get_text("", strip=True).replace("[EPUB_BR]", "\n").strip()
    escaped = html.escape(flat)

    def style_marker(match):
        number = int(match.group(1))
        label = f"〔图片字 {number:03d}〕"
        cls = "target" if number == target else "other"
        return f'<mark class="{cls}">{label}</mark>'

    return GLYPH_TOKEN.sub(style_marker, escaped)


def collect_glyph_paragraphs(report, book):
    """收集所有未解决图片字的块级出现位置，并保留重复出现。

    同一图片可能出现在多个 XHTML，也可能在一个段落里重复出现。
    每个目标来源块按图片字编号渲染一次，同时保留块内所有图片位置。
    """
    cases = glyph_sites(report)
    pages = defaultdict(list)
    for idx, case in enumerate(cases, 1):
        for page in case["pages"]:
            pages[(case["collection"], page)].append((idx, case["src"]))
    found = defaultdict(list)
    for (collection, page), wanted in pages.items():
        source = book.get_item_with_href(page)
        if source is None:
            raise ValueError(f"原 EPUB 缺少 XHTML：{page}")
        soup = BeautifulSoup(raw_xhtml(source), "lxml")
        blocks = list(iter_source_blocks(soup, page))
        index_for_src = {src: idx for idx, src in wanted}
        positions = defaultdict(list)
        latest_heading = ""
        for block in blocks:
            if block.tag in {"h1", "h2", "h4"}:
                latest_heading = block.text
            sources = [node.get("src") for node in block.element.find_all("img")]
            for src in dict.fromkeys(sources):
                idx = index_for_src.get(src)
                if idx is None:
                    continue
                occurrences = sources.count(src)
                positions[idx].append({
                    "html": page, "block": block.ordinal,
                    "tag": block.tag, "heading": latest_heading,
                    "occurrences": occurrences,
                    "paragraph": _marked_paragraph(block, index_for_src, idx),
                })
        for idx, src in wanted:
            if not positions[idx]:
                raise RuntimeError(
                    f"预检记录 {page} / {src}，但找不到包含该图片的 h1/h2/h4/p。"
                )
            found[idx].extend(positions[idx])
    return cases, dict(found)


def _image_data_uri(book, case):
    images = [
        _epub_image(book, page, case["src"]) for page in case["pages"]
    ]
    available = [image for image in images if image is not None]
    if not available:
        return None
    if len(set(available)) > 1:
        raise RuntimeError(
            f"{case['collection']} / {case['src']} "
            "同名图片在不同 XHTML 的内容不一致"
        )
    ext = Path(case["src"]).suffix.lower()
    mime = {
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    }.get(ext, "application/octet-stream")
    return f"data:{mime};base64," + base64.b64encode(available[0]).decode("ascii")


def render_contexts_html(report, book):
    """生成包含完整段落并高亮图片字的自包含离线 HTML。"""
    cases, sites = collect_glyph_paragraphs(report, book)
    cards = []
    for i, case in enumerate(cases, 1):
        uri = _image_data_uri(book, case)
        img = (
            f'<img src="{uri}" alt="图片字 {i:03d}">' if uri else
            "<span>图片资源未找到</span>"
        )
        contexts = []
        for position in sites[i]:
            title = html.escape(position["heading"] or "（未检测到上级标题）")
            contexts.append(
                '<div class="source"><div class="meta"><code>' +
                html.escape(position["html"]) + "</code> · 源块 " +
                str(position["block"]) + " · " +
                html.escape(position["tag"]) + " · " +
                "所在标题：" + title +
                (f" · 本块重复 {position['occurrences']} 次"
                 if position["occurrences"] > 1 else "") +
                '</div><p class="paragraph">' + position["paragraph"] +
                "</p></div>"
            )
        cards.append(
            f'<section id="glyph-{i:03d}" class="card">'
            '<div class="heading"><span class="number">' + f"{i:03d}" +
            '</span><div class="pic">' + img +
            '</div><div><strong>' + html.escape(case["collection"]) +
            '</strong><div><code>' + html.escape(case["src"]) +
            '</code></div><div class="hint">' + str(len(sites[i])) +
            ' 个源段落（各处均保留）</div></div></div>' +
            "".join(contexts) + '</section>'
        )
    nav = " ".join(
        f'<a href="#glyph-{i:03d}">{i:03d}</a>'
        for i in range(1, len(cases) + 1)
    )
    return (
        '<!doctype html><html lang="zh-CN"><head>'
        '<meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width,initial-scale=1">'
        '<title>清商｜图片字在原书中的完整段落</title>'
        '<style>:root{color-scheme:light}body{font:15px/1.65 '
        'system-ui,"Noto Sans CJK SC",sans-serif;background:#f6f7f9;'
        'color:#242424;margin:0}.container{max-width:1020px;'
        'margin:0 auto;padding:25px 18px 70px}h1{font-size:24px}'
        '.note{color:#555}.jump{display:flex;flex-wrap:wrap;gap:8px;'
        'margin:24px 0}.jump a{background:white;border:1px solid #ddd;'
        'padding:3px 8px;border-radius:5px;color:#264b70;text-decoration:none}'
        '.card{padding:18px;background:white;border:1px solid #ddd;'
        'border-radius:10px;margin:16px 0;scroll-margin-top:20px}'
        '.heading{display:flex;align-items:center;gap:15px}'
        '.number{font-size:22px;font-weight:750}.pic{width:70px;height:70px;'
        'display:grid;place-items:center;background:#f8f8f8}'
        '.pic img{width:65px;height:65px;object-fit:contain;'
        'image-rendering:pixelated}.hint,.meta{color:#666;font-size:13px}'
        '.source{margin:14px 0 0;border-top:1px solid #eee;padding-top:10px}'
        '.paragraph{font-size:17px;line-height:2.2;white-space:pre-wrap;'
        'overflow-wrap:anywhere;margin:8px 0 0}'
        'mark{border-radius:3px;padding:2px 4px}'
        'mark.target{background:#fce9a0;color:#503b00;font-weight:700}'
        'mark.other{background:#e7edf5;color:#37516b}'
        '</style></head><body><div class="container">'
        '<h1>清商 · 图片字在原书中的完整段落</h1>'
        '<p class="note">这份资料直接从你的本地 EPUB 提取。'
        '黄色标记为当前编号的图片字；蓝色标记为同段其他待辨认图片。'
        '标记不是汉字识别结果，只代表它在原文中的位置。'
        '按编号定位，复制整段即可在其他词集或字统网对照。'
        '<strong>含版权文本及原书图片，仅限本地查阅，不要公开上传。</strong>'
        '</p><nav class="jump">' + nav + '</nav>' +
        "".join(cards) + '</div></body></html>'
    )


def write_contexts(report, book, output_path):
    output_path = Path(output_path)
    markup = render_contexts_html(report, book)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markup, encoding="utf-8")
    return output_path
