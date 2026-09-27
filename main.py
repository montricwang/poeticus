import os

from dotenv import load_dotenv
from openai import OpenAI, APIError
from pydantic import BaseModel, ValidationError


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
client = OpenAI(api_key=api_key, base_url=base_url)


def parse_analysis(raw: str | None) -> PoemAnalysis:
    """将模型返回的 JSON 字符串解析为业务对象。"""
    if not raw:
        raise ValueError("模型返回了空内容")

    try:
        return PoemAnalysis.model_validate_json(raw)
    except ValidationError as exc:
        raise ValueError("模型输出不符合 PoemAnalysis 结构") from exc


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
            # max_tokens=2000,
        )
    except APIError as exc:
        raise RuntimeError("DeepSeek API 调用失败") from exc

    if not response.choices:
        raise ValueError("模型没有返回任何候选结果")

    choice = response.choices[0]

    if choice.finish_reason != "stop":
        raise ValueError(f"模型未正常完成生成：{choice.finish_reason}")

    return parse_analysis(choice.message.content)


if __name__ == "__main__":
    try:
        analysis = analyze_poem(
            "风卷珠帘自上钩，萧萧乱叶报新秋。独携纤手上高楼。\n缺月向人舒窈窕，三星当户照绸缪。香生雾縠见纤柔。"
        )
    except (ValueError, RuntimeError) as exc:
        print(f"赏析失败：{exc}")
    else:
        print(analysis.model_dump_json(indent=2))
