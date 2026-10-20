"""定义提供给模型的工具 Schema，并根据检索服务配置选择可用工具。"""

from openai.types.chat import ChatCompletionFunctionToolParam


# 定义向模型公开的证据查询工具及其参数格式。
TOOLS: list[ChatCompletionFunctionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_allusion",
            "description": (
                "查询中国古典诗词中的人物故事、掌故、神话传说和典故性短语的出处或含义。"
                "适合回答‘这个典故是什么故事/什么意思’；"
                "如果用户明确问‘借了谁哪一句诗、化用了哪段前代文本’，"
                "不要用本工具，应优先使用 search_predecessor_texts。"
                "不要用于整句诗文的全文相似检索、作品创作年代、作者生平、"
                "诗中人物身份或普通文学赏析。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": (
                            "真正需要查询的典故词语或短语。"
                            "优先使用最短且有辨识度的锚点；"
                            "不要机械地把整句诗、整段选区作为查询词。"
                        ),
                    }
                },
                "required": ["term"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_reference",
            "description": (
                "从外部诗词知识来源查询一句或短句可能对应的前代诗文、成句或化用候选。"
                "适合核对已有外部 reference evidence；"
                "返回结果只是候选，可能包含当前作品或后代作品，"
                "必须结合作者年代和文本关系判断。"
                "不适合解释人物故事型典故，也不能保证识别高度压缩或反用。"
                "若 search_predecessor_texts 可用，同一个文本来源问题不要先用本工具重复试探；"
                "只有本地 Corpus Tool 不可用，或已有明确理由需要外部 reference evidence 时再使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": (
                            "真正要比较来源的诗句或短句。"
                            "优先只提交目标短句，不要机械地提交整首诗。"
                        ),
                    }
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
    },
]

# 本地诗词语料检索工具，根据服务配置决定是否向模型开放。
TEXT_RETRIEVAL_TOOL: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": "search_predecessor_texts",
        "description": (
            "在 Poeticus 自建古典诗词 Corpus 中检索可能对应当前文本的前代候选。"
            "用户问‘借了谁哪一句诗、化用了哪段前代文本、和哪一句前代文本有关’时，"
            "应优先使用本工具，即使目标短语同时带有典故色彩。"
            "适合寻找近似成句、改写、拆取重组和长尾互文；"
            "这是全文检索候选发现，不等于已经证明引用或化用。"
            "普通赏析、作者生平和人物故事型典故不要调用。"
            "如果第一轮结果不足，而问题仍然是文本来源，"
            "可以换一个更有辨识度的文本锚点再检索一次。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": (
                        "真正需要寻找前代文本的目标诗句或短片段。"
                        "优先保留有辨识度的原文；不要机械提交整首作品，"
                        "也不要把自己猜测的出处改写成 Query。"
                    ),
                }
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
}


DOCUMENT_RETRIEVAL_TOOL: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": (
            "从本地《人间词话》《白雨斋词话》《乐府指迷》《碧鸡漫志》检索历代词学评论的原文。"
            "用户询问词论、词家评价、词学概念、风格比较、文学批评史或要求词话原文证据时优先使用。"
            "检索人物本名可能漏掉字、号（如周邦彦/美成、姜夔/白石）；"
            "请在 queries 中提供一到两条包含可能别称或关键评语的扩展查询，原始用户问题会自动保留。"
            "文献只是候选材料，不等于它已经充分支持结论。"
            "普通典故故事查询使用 lookup_allusion；查前代诗句化用使用 search_predecessor_texts，"
            "不要混淆词话评论和诗句相似性。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "一至两条互补的检索表达，适当包含字号、词学术语；不要杜撰别名对应关系。",
                    "minItems": 1, "maxItems": 2,
                }
            },
            "required": ["queries"],
            "additionalProperties": False,
        },
    },
}


# CNKGraph external capabilities are experimental non-commercial research tools.
# Do not register them for anonymous production visitors without separate permission.
CNKGRAPH_RESEARCH_TOOLS: list[ChatCompletionFunctionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "analyze_ci_meter",
            "description": (
                "按 CNKGraph 钦谱与龙谱检查一首词的词牌体式、平仄和押韵疑点。"
                "适合用户问‘这首词押韵吗、是否合词谱、有何变格’时使用。"
                "默认直接使用当前阅读作品正文，不要机械重复提交原诗。"
                "后世词谱形式符合与宋代实际合乐是不同概念，"
                "此工具不能单独证明词在宋代是否可唱，也不能代替词学文献。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tune_name": {
                        "type": "string",
                        "description": "作品所属词牌名称，如‘醉花间’或‘念奴娇’，不能填作品副题。",
                    },
                    "content": {
                        "type": "string",
                        "description": "可选：只有分析非当前阅读作品时才提供完整词正文；默认使用当前作品。",
                    },
                },
                "required": ["tune_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_classical_books",
            "description": (
                "从外部古籍库中检索含指定关键词的书、卷和短原文上下文；"
                "适合查‘哪本古书记过这句话、某个词学概念见于何书’。"
                "提供候选的书卷与可回查 ID，不能据字面命中断定原始出处或学术结论。"
                "要找本地已导入的词话研究评论优先用 search_documents；"
                "典故故事优先用 lookup_allusion；诗句化用优先用 search_predecessor_texts。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "准确且有区分度的古文短语或关键词，不要提交整篇文章。",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
]


def available_tools(
    retrieval_enabled: bool,
    document_enabled: bool = False,
    cnkgraph_research_enabled: bool = False,
) -> list[ChatCompletionFunctionToolParam]:
    """根据检索服务的启用状态，返回本轮可向模型提供的工具。"""

    tools = list(TOOLS)
    if retrieval_enabled:
        tools.append(TEXT_RETRIEVAL_TOOL)
    if document_enabled:
        tools.append(DOCUMENT_RETRIEVAL_TOOL)
    if cnkgraph_research_enabled:
        tools.extend(CNKGRAPH_RESEARCH_TOOLS)
    return tools
