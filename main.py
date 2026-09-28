import os
from dotenv import load_dotenv
from openai import OpenAI, APIError
from pydantic import BaseModel
from langsmith.wrappers import wrap_openai


class Gloss(BaseModel):
    term: str
    explanation: str


class PoemAnalysis(BaseModel):
    translation: str
    glosses: list[Gloss]
    commentary: str


load_dotenv()

api_key = os.environ["LLM_API_KEY"]
base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
client = wrap_openai(OpenAI(api_key=api_key, base_url=base_url))


def analyze_poem(poem: str) -> PoemAnalysis:
    """调用模型，返回经过校验的诗歌赏析。"""
    if not poem.strip():
        raise ValueError("诗歌原文不能为空")

    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {
                    "role": "system",
                    "content": """
你是一位专业的文学阅读助手。
请分析用户提供的诗歌，只返回以下结构的 JSON，
不要输出 Markdown 或其他文字。

{
    "translation": "完整、自然的现代汉语译文",
    "glosses": [
        {
            "term": "需要解释的词语",
            "explanation": "简洁的释义"
        }
    ],
    "commentary": "简短、自然、有依据的文学赏析"
}

不要编造文献出处。
                    """,
                },
                {
                    "role": "user",
                    "content": poem,
                },
            ],
            response_format={"type": "json_object"},
        )
    except APIError as exc:
        raise RuntimeError("DeepSeek API 调用失败") from exc

    if not response.choices:
        raise ValueError("模型没有返回任何候选结果")

    choice = response.choices[0]

    if choice.finish_reason != "stop":
        raise ValueError(f"模型未正常完成生成：{choice.finish_reason}")

    if not choice.message.content:
        raise ValueError("模型返回了空内容")

    return PoemAnalysis.model_validate_json(choice.message.content)


def chat_about_poem(
    poem: str,
    question: str,
    selection: str | None = None,
) -> str:
    """结合完整诗歌和可选的原文引用，回答用户的问题。"""

    context = f"诗歌原文：\n{poem}"

    if selection:
        context += f"\n\n用户选中的原文：\n{selection}"

    context += f"\n\n用户的问题：\n{question}"

    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一位专业的文学阅读助手。"
                        "请结合用户提供的完整诗歌，直接回答具体问题。"
                        "如果用户引用了某段原文，应优先围绕该段解释，"
                        "但不能脱离整首诗的上下文。"
                        "回答应自然、准确，避免无关的长篇介绍。"
                        "不要编造文献出处、作者信息或历史事实。"
                        "如果问题需要外部文献核实，而你无法确认，"
                        "应明确说明不确定性。"
                    ),
                },
                {
                    "role": "user",
                    "content": context,
                },
            ],
        )
    except APIError as exc:
        raise RuntimeError("DeepSeek API 调用失败") from exc

    if not response.choices:
        raise ValueError("模型没有返回任何候选结果")

    choice = response.choices[0]

    if choice.finish_reason != "stop":
        raise ValueError(f"模型未正常完成生成：{choice.finish_reason}")

    if not choice.message.content:
        raise ValueError("模型返回了空内容")

    return choice.message.content


if __name__ == "__main__":
    try:
        analysis = analyze_poem(
            "风卷珠帘自上钩，萧萧乱叶报新秋。独携纤手上高楼。\n缺月向人舒窈窕，三星当户照绸缪。香生雾縠见纤柔。"
        )
    except (ValueError, RuntimeError) as exc:
        print(f"赏析失败：{exc}")
    else:
        print(analysis.model_dump_json(indent=2))
