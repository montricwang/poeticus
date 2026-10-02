from dataclasses import dataclass, field


@dataclass
class DocumentNode:
    """
    XHTML DOM 的中间表示。

    注意：
    这里保存事实，不做语义判断。
    """

    tag: str

    text: str = ""

    attrs: dict = field(default_factory=dict)

    style: dict = field(default_factory=dict)

    children: list["DocumentNode"] = field(default_factory=list)

    source: dict = field(default_factory=dict)


@dataclass
class Document:
    """
    一个 XHTML 文档。
    """

    path: str

    root: DocumentNode
