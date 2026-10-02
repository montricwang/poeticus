"""DOM analysis layer for EPUB import.

This module only extracts structural evidence from XHTML.
It does not decide poem semantics such as tune, title, preface, or commentary.
"""

from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass
class DOMBlock:
    tag: str
    text: str
    classes: list[str]
    element_id: str | None = None


class DOMAnalyzer:
    """Convert XHTML into semantic-neutral DOM blocks."""

    def analyze(self, html: str) -> list[DOMBlock]:
        soup = BeautifulSoup(html, "lxml")
        blocks = []

        for element in soup.find_all(["h1", "h2", "h3", "p"]):
            text = element.get_text("", strip=True)
            if not text and not element.find("img"):
                continue

            blocks.append(
                DOMBlock(
                    tag=element.name,
                    text=text,
                    classes=element.get("class", []),
                    element_id=element.get("id"),
                )
            )

        return blocks
