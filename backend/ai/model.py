import logging
import os

from langsmith.wrappers import wrap_openai
from openai import APIError, OpenAI
from pydantic import BaseModel

from backend.ai.prompt_loader import compose_prompt
from backend.ai.context import PoemContext, format_poem_context
from backend.config import (
    LLM_BASE_URL,
    LLM_MAX_OUTPUT_TOKENS,
    LLM_MAX_RETRIES,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


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
            # 整首赏析关闭 DeepSeek 的默认推理模式，避免隐藏推理耗尽
            # 输出 Token 预算并导致 finish_reason=length。
            extra_body={"thinking": {"type": "disabled"}},
        )
    except APIError as exc:
        raise RuntimeError("DeepSeek API 调用失败") from exc

    if not response.choices:
        raise ValueError("模型没有返回任何候选结果")

    choice = response.choices[0]

    if choice.finish_reason != "stop":
        # 日志只记录完成状态，不回显原文、用户输入或模型响应。
        logger.warning(
            "analysis_completion_incomplete finish_reason=%s",
            choice.finish_reason,
        )
        raise ValueError("模型未正常完成生成")

    if not choice.message.content:
        logger.warning("analysis_completion_empty")
        raise ValueError("模型返回了空内容")

    try:
        return PoemAnalysis.model_validate_json(choice.message.content)
    except ValueError:
        logger.warning("analysis_response_schema_invalid")
        raise


