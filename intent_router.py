from typing import Literal, NotRequired, TypedDict

from langgraph.graph import StateGraph, START, END
from openai import APIError
from pydantic import BaseModel, ValidationError

from main import client, chat_about_poem


# 1. 定义意图分类结果


class IntentResult(BaseModel):
    intent: Literal[
        "text_reading",
        "source_lookup",
        "needs_clarification",
    ]
    reason: str


# 2. 定义 Graph 中共享的数据
class RouterState(TypedDict):
    poem: str
    question: str

    # 前端已经支持选区，Graph 现在也接受这份信息。
    selection: NotRequired[str | None]

    # 以下字段由节点逐步产生。
    intent: NotRequired[str]
    reason: NotRequired[str]
    next_step: NotRequired[str]
    reply: NotRequired[str]


# 3. 调用 DeepSeek 进行真实的意图识别
def classify_intent(state: RouterState) -> dict:
    system_prompt = """
你是古典诗歌阅读系统的意图分类器。
你的任务不是回答用户的问题，而是判断下一步
应该直接分析原文、查询资料，还是请求用户澄清。

只能选择以下三种类型：

text_reading：
可以根据当前诗歌原文和选区进行解释。
包括白话翻译、字词在本诗中的含义、炼字、
意象、情绪及章法分析。
用户选中词语后说“没听说过”“这什么意思”，
通常也属于这一类。

source_lookup：
需要查询原文之外的资料，包括作者身份、
作品背景、版本、词语的历史义项、
典故出处和历代评论。
即使你知道答案，只要用户要求文献出处，
仍然应该选择 source_lookup。

needs_clarification：
缺少继续处理所必需的信息。
例如用户问“这个词从哪来的”，
但没有选区，也无法从问题中确定具体指哪个词。

判断原则：
1. 先结合选区理解“这个词”“这句话”等指代。
2. 问题本身明确时，不要因为没有选区而要求澄清。
3. 对普通口语表达，应尽量理解用户的实际意图。
4. 只有无法可靠确定用户所指的对象或要求时，
   才选择 needs_clarification。
5. 不要编造诗歌作者、典故或文献出处。

特别注意字词类问题的区别：

询问字词在当前诗歌中的意思、表达效果和文学含义，
属于 text_reading。

询问汉字读音、多音字读法、词典义项或历史音韵，
属于 source_lookup，因为需要字典等外部知识。

例如：
选中“縠”，问“这个字怎么读？”
→ source_lookup

选中“绸缪”，问“这个词在这里是什么意思？”
→ text_reading

选中“绸缪”，问“这个词在古代有哪些义项？”
→ source_lookup

只返回 JSON，包含 intent 和 reason。

示例：
{
    "intent": "needs_clarification",
    "reason": "用户没有说明具体指哪个词，也没有提供选区"
}
""".strip()

    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"当前诗歌：\n{state['poem']}\n\n"
                        f"当前选区：\n"
                        f"{state.get('selection') or '（未选择任何原文）'}\n\n"
                        f"用户问题：\n{state['question']}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=512,
            extra_body={"thinking": {"type": "disabled"}},
        )
    except APIError as exc:
        raise RuntimeError("意图识别 API 调用失败") from exc

    if not response.choices:
        raise RuntimeError("模型没有返回分类结果")

    choice = response.choices[0]

    if choice.finish_reason != "stop":
        raise RuntimeError(
            f"模型提前停止：finish_reason={choice.finish_reason}，"
            f"content={choice.message.content!r}，"
            f"usage={response.usage}"
        )

    if not choice.message.content:
        raise RuntimeError(f"模型返回空内容：usage={response.usage}")

    try:
        decision = IntentResult.model_validate_json(choice.message.content)
    except ValidationError as exc:
        raise RuntimeError("意图分类结果不符合 Schema") from exc

    return {
        "intent": decision.intent,
        "reason": decision.reason,
    }


# 4. 根据分类结果选择后续节点
def route_intent(
    state: RouterState,
) -> Literal[
    "text_reading",
    "source_lookup",
    "needs_clarification",
]:
    intent = state.get("intent")

    if intent in (
        "text_reading",
        "source_lookup",
        "needs_clarification",
    ):
        return intent

    raise ValueError(f"缺少有效的意图分类结果：{intent!r}")


# 5. 暂时只确认进入了哪个分支
def direct_answer(state: RouterState) -> dict:
    answer = chat_about_poem(
        poem=state["poem"],
        question=state["question"],
        selection=state.get("selection"),
    )

    return {
        "next_step": "direct_answer",
        "reply": answer,
    }


def source_lookup(state: RouterState) -> dict:
    return {
        "next_step": "source_lookup",
        "reply": (
            "这个问题需要核对词典或相关文献。"
            "当前版本尚未接入查询工具，"
            "因此暂时无法提供经过核实的答案。"
        ),
    }


def clarify_user(state: RouterState) -> dict:
    """向用户请求完成当前问题所必需的信息。"""
    return {
        "next_step": "needs_clarification",
        "reply": "你具体指诗中的哪个词或哪句话？可以选中原文，或者直接告诉我。",
    }


# 6. 构造并编译 LangGraph
builder = StateGraph(RouterState)

builder.add_node("classify_intent", classify_intent)
builder.add_node("direct_answer", direct_answer)
builder.add_node("source_lookup", source_lookup)
builder.add_node("clarify_user", clarify_user)

builder.add_edge(START, "classify_intent")


builder.add_conditional_edges(
    "classify_intent",
    route_intent,
    {
        "text_reading": "direct_answer",
        "source_lookup": "source_lookup",
        "needs_clarification": "clarify_user",
    },
)

builder.add_edge("direct_answer", END)
builder.add_edge("source_lookup", END)
builder.add_edge("clarify_user", END)

graph = builder.compile()


# 7. 用两个问题观察真实执行过程
if __name__ == "__main__":
    poem = (
        "风卷珠帘自上钩，萧萧乱叶报新秋。"
        "独携纤手上高楼。"
        "缺月向人舒窈窕，三星当户照绸缪。"
        "香生雾縠见纤柔。"
    )

    cases = [
        {
            "question": "这个词从哪来的？",
            "selection": "三星当户",
            "expected": "source_lookup",
        },
        {
            "question": "这个词从哪来的？",
            "selection": None,
            "expected": "needs_clarification",
        },
        {
            "question": "这个词我没听说过。",
            "selection": "绸缪",
            "expected": "text_reading",
        },
        {
            "question": "这是什么意思？",
            "selection": None,
            "expected": "needs_clarification",
        },
    ]

    for case in cases:
        result = graph.invoke(
            {
                "poem": poem,
                "question": case["question"],
                "selection": case["selection"],
            }
        )

        actual = result["intent"]
        expected = case["expected"]

        print(f"\n问题：{case['question']}")
        print(f"选区：{case['selection']}")
        print(f"预期：{expected}")
        print(f"实际：{actual}")
        print(f"结果：{'PASS' if actual == expected else 'FAIL'}")
        print(f"理由：{result['reason']}")

        if result.get("reply"):
            print(f"澄清：{result['reply']}")
