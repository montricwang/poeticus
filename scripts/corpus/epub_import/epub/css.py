"""Inspect EPUB typography without treating CSS as literary semantics.

This is a *static* cascade approximation, not browser getComputedStyle().
Unsupported at-rules/selectors and unavailable stylesheets are reported.
"""

from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

import cssselect2
import soupsieve
import tinycss2

TYPOGRAPHY = (
    "font-family", "font-size", "font-weight", "font-style", "font-variant",
    "color", "text-align", "text-indent", "letter-spacing", "line-height",
    "white-space", "vertical-align", "display",
)
INHERITED = set(TYPOGRAPHY) - {"vertical-align", "display"}


def declarations(source):
    result = []
    for decl in tinycss2.parse_declaration_list(source, skip_comments=True, skip_whitespace=True):
        if decl.type != "declaration" or decl.lower_name not in TYPOGRAPHY:
            continue
        value = tinycss2.serialize(decl.value).strip()
        if value:
            result.append((decl.lower_name, value, bool(decl.important)))
    return result


def local_href(parent_name, href):
    """Resolve a relative EPUB resource path, rejecting external/parent escapes."""
    split = urlsplit(href or "")
    if split.scheme or split.netloc or not split.path:
        return None
    path = unquote(split.path).replace("\\", "/")
    parts = list(PurePosixPath(parent_name).parent.parts)
    for piece in path.split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(piece)
    return "/".join(parts)


class StyleResolver:
    """Evaluate linked/embedded CSS declarations using selector specificity."""

    def __init__(self, book):
        self.book = book
        self.sheets = {}
        self.problems = set()

    def _parse_sheet(self, text, origin):
        rules = []
        for node in tinycss2.parse_stylesheet(text, skip_comments=True, skip_whitespace=True):
            if node.type == "at-rule":
                # Media, @import, @supports and font-face are not evaluated.
                self.problems.add(f"{origin}: 未解释 @{node.lower_at_keyword}")
                continue
            if node.type != "qualified-rule":
                continue
            css = tinycss2.serialize(node.prelude).strip()
            props = declarations(node.content)
            if not props:
                continue
            try:
                selectors = cssselect2.compile_selector_list(css)
                # Keep the selector as one string only if not comma-separated.
                # Split via tinycss2 tokens to avoid splitting inside :not(...).
                groups = []
                current = []
                for token in node.prelude:
                    if token.type == "literal" and token.value == ",":
                        groups.append(tinycss2.serialize(current).strip())
                        current = []
                    else:
                        current.append(token)
                groups.append(tinycss2.serialize(current).strip())
                if len(groups) != len(selectors):
                    raise ValueError("selector count mismatch")
            except (cssselect2.SelectorError, ValueError) as exc:
                self.problems.add(f"{origin}: 跳过选择器 {css[:80]} ({exc})")
                continue
            for selector, compiled in zip(groups, selectors):
                if compiled.pseudo_element:
                    continue
                rules.append((selector, compiled.specificity, props))
        return rules

    def for_document(self, soup, html_name):
        """Return stylesheet rules in document order and paths used."""
        ordered = []
        paths = []
        for element in soup.find_all(["link", "style"]):
            if element.name == "style":
                origin = f"{html_name}#style"
                ordered.extend((origin, *rule) for rule in self._parse_sheet(element.get_text(), origin))
                paths.append(origin)
                continue
            rel = element.get("rel", [])
            if not any(str(x).lower() == "stylesheet" for x in rel):
                continue
            path = local_href(html_name, element.get("href"))
            if path is None:
                self.problems.add(f"{html_name}: 外部或无效样式表 {element.get('href')}")
                continue
            if path not in self.sheets:
                item = self.book.get_item_with_href(path)
                if item is None:
                    self.problems.add(f"{html_name}: 找不到样式表 {path}")
                    self.sheets[path] = []
                else:
                    content = item.get_content().decode("utf-8-sig", errors="replace")
                    self.sheets[path] = self._parse_sheet(content, path)
            ordered.extend((path, *rule) for rule in self.sheets[path])
            paths.append(path)
        return DocumentStyles(ordered, paths, self.problems)


class DocumentStyles:
    def __init__(self, rules, paths, problems):
        self.rules = rules
        self.paths = paths
        self.problems = problems
        self.cache = {}
        self.sources = {}

    def style(self, tag):
        """Selected CSS declarations with inheritance; values are not converted to px."""
        key = id(tag)
        if key in self.cache:
            return self.cache[key]

        parent = getattr(tag, "parent", None)
        inherited = {}
        if getattr(parent, "name", None):
            inherited = {k: v for k, v in self.style(parent).items() if k in INHERITED}

        winners = {}
        for index, (origin, selector, specificity, props) in enumerate(self.rules):
            try:
                matches = soupsieve.match(selector, tag)
            except Exception as exc:
                self.problems.add(f"选择器无法匹配：{selector[:80]} ({type(exc).__name__})")
                continue
            if not matches:
                continue
            for name, value, important in props:
                priority = (int(important), 0, specificity, index)
                if name not in winners or priority >= winners[name][0]:
                    winners[name] = (priority, value, f"{origin}: {selector}")

        for name, value, important in declarations(tag.get("style", "")):
            priority = (int(important), 1, (0, 0, 0), len(self.rules))
            if name not in winners or priority >= winners[name][0]:
                winners[name] = (priority, value, "inline style")

        output = dict(inherited)
        sources = {k: f"继承自 {parent.name}" for k in inherited} if getattr(parent, "name", None) else {}
        for name, (_priority, value, origin) in winners.items():
            if value == "inherit":
                continue
            if value in ("initial", "unset"):
                output.pop(name, None)
                sources.pop(name, None)
            else:
                output[name] = value
                sources[name] = origin
        self.cache[key] = output
        self.sources[key] = sources
        return output

    def provenance(self, tag):
        self.style(tag)
        return self.sources[id(tag)]