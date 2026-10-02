from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

from .models import DocumentNode, Document


def parse_node(element, source):
    """
    将 BeautifulSoup Tag 转换为 DocumentNode。

    不判断语义。
    """

    if isinstance(element, NavigableString):
        text = str(element).strip()

        if not text:
            return None

        return DocumentNode(
            tag="text",
            text=text,
            source=source,
        )

    if not isinstance(element, Tag):
        return None

    children = []

    for child in element.children:
        node = parse_node(
            child,
            source,
        )

        if node:
            children.append(node)

    return DocumentNode(
        tag=element.name,
        attrs=dict(element.attrs),
        children=children,
        source=source,
    )


def build_document(
    html_name,
    html_content,
):
    soup = BeautifulSoup(
        html_content,
        "lxml",
    )

    root = parse_node(
        soup.html,
        {
            "file": html_name,
        },
    )

    return Document(
        path=html_name,
        root=root,
    )
