import os
import json
import logging
from collections.abc import Iterator
from openai import OpenAI, APIError
from pydantic import BaseModel
from langsmith.wrappers import wrap_openai
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

logger = logging.getLogger(__name__)

from backend.ai.prompt_loader import compose_prompt
from backend.ai.context import PoemContext, format_poem_context
from backend.config import (
    LLM_BASE_URL,
    LLM_MAX_OUTPUT_TOKENS,
    LLM_MAX_RETRIES,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
)


class Gloss(BaseModel):
    term: str
    explanation: str


class PoemAnalysis(BaseModel):
    translation: str
    glosses: list[Gloss]
    commentary: str


api_key = os.environ["LLM_API_KEY"]
client = wrap_openai(
    OpenAI(
        api_key=api_key,
        base_url=LLM_BASE_URL,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )
)


def answer_with_evidence(
    poem: str,
    question: str,
    selection: str | None,
    evidences: list,
    context: PoemContext | None = None,
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
        model=LLM_MODEL,
        max_tokens=LLM_MAX_OUTPUT_TOKENS,
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
                    f"{format_poem_context(context)}"
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


def analyze_poem(poem: str, context: PoemContext | None = None) -> PoemAnalysis:
    """调用模型，返回经过校验的诗歌赏析。"""
    if not poem.strip():
        raise ValueError("诗歌原文不能为空")

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_OUTPUT_TOKENS,
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
                    "content": (
                        f"{format_poem_context(context)}"
                        f"诗歌原文：\n{poem}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
            # Unlike the Agent route, analysis previously left DeepSeek's
            # default reasoning enabled: the 1200-token budget could be
            # consumed by hidden reasoning, yielding finish_reason=length.
            extra_body={"thinking": {"type": "disabled"}},
        )
    except APIError as exc:
        raise RuntimeError("DeepSeek API 调用失败") from exc

    if not response.choices:
        raise ValueError("模型没有返回任何候选结果")

    choice = response.choices[0]

    if choice.finish_reason != "stop":
        # Do not log or echo poem text, user input, or model response.
        logger.warning("analysis_completion_incomplete finish_reason=%s", choice.finish_reason)
        raise ValueError("模型未正常完成生成")

    if not choice.message.content:
        logger.warning("analysis_completion_empty")
        raise ValueError("模型返回了空内容")

    try:
        return PoemAnalysis.model_validate_json(choice.message.content)
    except ValueError:
        logger.warning("analysis_response_schema_invalid")
        raise


def _chat_messages(
    poem: str,
    question: str,
    selection: str | None,
    context: PoemContext | None,
) -> list[ChatCompletionMessageParam]:
    """普通聊天和流式聊天共用同一套消息模板。"""

    context_block = f"{format_poem_context(context)}诗歌原文：\n{poem}"

    if selection:
        context_block += f"\n\n用户选中的原文：\n{selection}"

    context_block += f"\n\n用户的问题：\n{question}"

    system_message: ChatCompletionSystemMessageParam = {
        "role": "system",
        "content": compose_prompt(
            "chat",
            "output_style",
        ),
    }

    user_message: ChatCompletionUserMessageParam = {
        "role": "user",
        "content": context_block,
    }

    return [system_message, user_message]


def chat_about_poem(
    poem: str,
    question: str,
    selection: str | None = None,
    *,
    context: PoemContext | None = None,
) -> str:
    """原有非流式接口继续使用，不影响 /chat 和现有 Graph 测试。"""
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_OUTPUT_TOKENS,
            messages=_chat_messages(poem, question, selection, context),
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
    poem: str,
    question: str,
    selection: str | None = None,
    *,
    context: PoemContext | None = None,
) -> Iterator[str]:
    """直接转发模型真实生成的增量文本；不做假打字动画。"""
    stream = None
    finish_reason = None
    parts: list[str] = []
    try:
        stream = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_OUTPUT_TOKENS,
            messages=_chat_messages(poem, question, selection, context),
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
