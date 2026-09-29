import os
import json
from collections.abc import Iterator
from dotenv import load_dotenv
from openai import OpenAI, APIError
from pydantic import BaseModel
from langsmith.wrappers import wrap_openai
from prompt_loader import compose_prompt


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


def answer_with_evidence(
    poem: str, question: str, selection: str | None, evidences: list
) -> str:
    """根据检索到的候选证据回答文学问题。"""
    materials = []

    for index, item in enumerate(evidences[:3], start=1):
        source = (
            item.source.title if item.source and item.source.title else "来源未注明"
        )
        materials.append(
            {
                "id": f"E{index}",
                "source": source,
                "text": item.text[:1800],
                "status": item.status,
            }
        )

    response = client.chat.completions.create(
        model="deepseek-flash",
        messages=[
            {
                "role": "system",
                "content": compose_prompt(
                    "evidence_answer",
                    "output_style",
                ),
            },
            {
                "role": "user",
                "content": (
                    f"当前诗歌：\n{poem}\n\n"
                    f"选区：{selection or '无'}\n"
                    f"问题：{question}\n\n"
                    "候选证据：\n" + json.dumps(materials, ensure_ascii=False)
                ),
            },
        ],
    )

    if not response.choices:
        raise RuntimeError("模型没有返回答案")

    choice = response.choices[0]
    if choice.finish_reason != "stop" or not choice.message.content:
        raise RuntimeError("模型未正常完成证据分析")

    return choice.message.content


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
                    "content": compose_prompt(
                        "analyze_poem",
                        "output_style",
                    ),
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


def _chat_messages(poem: str, question: str, selection: str | None) -> list[dict]:
    """普通聊天和流式聊天共用同一套消息模板。"""
    context = f"诗歌原文：\n{poem}"

    if selection:
        context += f"\n\n用户选中的原文：\n{selection}"

    context += f"\n\n用户的问题：\n{question}"

    return [
        {
            "role": "system",
            "content": compose_prompt(
                "chat",
                "output_style",
            ),
        },
        {
            "role": "user",
            "content": context,
        },
    ]


def chat_about_poem(poem: str, question: str, selection: str | None = None) -> str:
    """原有非流式接口继续使用，不影响 /chat 和现有 Graph 测试。"""
    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=_chat_messages(poem, question, selection),
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


def stream_chat_about_poem(
    poem: str, question: str, selection: str | None = None
) -> Iterator[str]:
    """直接转发模型真实生成的增量文本；不做假打字动画。"""
    stream = None
    finish_reason = None
    parts: list[str] = []
    try:
        stream = client.chat.completions.create(
            model="deepseek-flash",
            messages=_chat_messages(poem, question, selection),
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.delta.content:
                parts.append(choice.delta.content)
                yield choice.delta.content
            if choice.finish_reason is not None:
                finish_reason = choice.finish_reason
    except APIError as exc:
        raise RuntimeError("DeepSeek 流式生成失败") from exc
    finally:
        if stream is not None:
            stream.close()

    if finish_reason != "stop":
        raise ValueError(f"模型未正常完成生成：{finish_reason}")
    if not "".join(parts).strip():
        raise ValueError("模型返回了空内容")


if __name__ == "__main__":
    try:
        analysis = analyze_poem(
            "风卷珠帘自上钩，萧萧乱叶报新秋。独携纤手上高楼。\n缺月向人舒窈窕，三星当户照绸缪。香生雾縠见纤柔。"
        )
    except (ValueError, RuntimeError) as exc:
        print(f"赏析失败：{exc}")
    else:
        print(analysis.model_dump_json(indent=2))
