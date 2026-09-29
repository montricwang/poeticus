"""作品元数据：进入 AI 上下文的最小字段集。"""

from pydantic import BaseModel


class PoemContext(BaseModel):
    id: str
    title: str
    author: str | None = None
    dynasty: str | None = None
    review_status: str | None = None


def format_poem_context(context: PoemContext | None) -> str:
    """生成供 LLM 使用的作品上下文；未提供时返回空字符串。"""
    if context is None:
        return ""
    author = context.author or "未核实"
    dynasty = context.dynasty or "未核实"
    text = (
        "作品上下文：\n"
        f"题名：{context.title}\n"
        f"作者：{author}\n"
        f"时代：{dynasty}\n\n"
    )
    if context.review_status == "imported_unreviewed":
        text += (
            "当前作品正文尚未完成全面校勘。不要将其文字、标点或版本描述为已经核实；"
            "如用户要求文献依据，应说明需要进一步查证。普通赏析不必主动重复此说明。"
        )
    return text
