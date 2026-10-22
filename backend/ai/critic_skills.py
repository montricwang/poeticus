"""Poeticus Critic 的本地分析方法目录和只读加载入口。"""

from pathlib import Path

from openai.types.chat import ChatCompletionFunctionToolParam


_SKILL_ROOT = Path(__file__).resolve().parents[1] / "skills" / "critic"

# 这是对模型公开的唯一 Skill 目录；文件版本由开发侧决定，不对模型开放切换。
SKILL_CATALOG: dict[str, str] = {
    "TEXT_WORD": "字词释义、局部句法、词义歧义与炼字的实际表达效果。",
    "PROSODY": "韵脚、平仄、句逗、词谱与其他可核的声律问题。",
    "IMAGE": "意象、色彩、声响、动静、感官和画面组织。",
    "STRUCTURE": "全篇分层、伏笔、转折、照应、铺叙与结尾。",
    "NARRATIVE": "发话者、人物视角、动作、梦境、回忆与叙述顺序。",
    "TIME_SPACE": "时间、地点、方位、远近与今昔、虚实场景的切换。",
    "ALLUSION": "核实典故、旧语或故事的出处、原义及本篇用法。",
    "INTERTEXT": "不同作品间的用句、唱和、改写、同题比较与互文。",
    "CONTEXT": "判断哪些题序、风俗、作者或社会背景有助于解释词句。",
    "HISTORY": "历史事件、人物、系年、地理、制度及版本来源的事实核验。",
    "ALLEGORY": "比兴、象征、寄托及其证据桥梁和竞争解释。",
    "AESTHETICS": "从具体写法论证含蓄、清空、悲壮等审美效果。",
    "COUNTERFACTUAL": "对换字、删句、改序等假设进行受控比较，检验分析结论。",
    "DEBATE": "辨析真实存在的异说，比较证据、前提与结论强度。",
}

def skill_catalog_prompt() -> str:
    """向 Agent 提供简短方法索引，始终与加载工具共享一份目录。"""

    entries = "\n".join(f"- {name}：{description}" for name, description in SKILL_CATALOG.items())
    return (
        "你有以下文学批评 Skill 可按需使用；这是分析方法目录，而非事实资料来源：\n"
        f"{entries}\n\n"
        "处理需要具体文学分析方法的问题时，优先判断哪一两类方法可以改善论证；"
        "若适合且本轮开放 load_critic_skills，可按需读取完整方法指导，随后结合诗文和查证工具进行分析。"
        "已经能够可靠解决的简单事实、直接释义和一般问答无需加载。"
        "不要机械覆盖全部类别，不要反复加载已读方法；如果需要原典、系年或版本证据，"
        "仍须使用适合的检索工具，不能把 Skill 当成史料。"
    )


SKILL_TOOL: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": "load_critic_skills",
        "description": (
            "读取 Poeticus 已公开目录中的文学批评方法全文。"
            "仅选择确实有助于当前问题的 Skill，可组合互补方法；"
            "不要重复加载已读方法。这是分析指导，而非文献证据。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skills": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(SKILL_CATALOG)},
                    "minItems": 1,
                    "maxItems": 3,
                    "uniqueItems": True,
                    "description": "这次确实需要的 1–3 个互补分析方法名称，不必穷举全部类别。",
                }
            },
            "required": ["skills"],
            "additionalProperties": False,
        },
    },
}


def validate_skill_names(value: object) -> tuple[str, ...]:
    """校验模型参数；仅允许公开目录中的名称，绝不接收文件路径。"""

    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= 3
        or any(not isinstance(name, str) or name not in SKILL_CATALOG for name in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError("Skill 名称必须是目录内 1–3 个不重复的方法")
    return tuple(value)


def load_critic_skills(names: tuple[str, ...]) -> dict[str, object]:
    """从随代码部署的静态文件读取 Skill 正文；不读取用户或外部研究目录。"""

    if not names or len(names) > 3 or len(set(names)) != len(names):
        raise ValueError("无效的 Skill 列表")
    results: list[dict[str, str]] = []
    for name in names:
        if name not in SKILL_CATALOG:
            raise ValueError(f"未知 Skill：{name}")
        path = _SKILL_ROOT / f"{name.lower()}.md"
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError(f"Skill 文件无法读取：{name}") from exc
        if not content:
            raise ValueError(f"Skill 内容为空：{name}")
        results.append({"name": name, "content": content})
    return {"status": "ok", "skills": results}
