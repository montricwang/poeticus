"""跨模块运行参数与 API 限制的唯一配置来源。"""

import os

from dotenv import load_dotenv

load_dotenv()


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


# 公开聊天契约：后端校验是最终权威；前端只通过 /api/capabilities
# 读取浏览器真正需要知道的那一小部分，不再保存重复常量。
AI_MAX_POEM_CHARS = 12000
CHAT_MAX_QUESTION_CHARS = 1200
CHAT_MAX_SELECTION_CHARS = 3000
CHAT_MAX_HISTORY_TURNS = 6
CHAT_MAX_HISTORY_MESSAGES = CHAT_MAX_HISTORY_TURNS * 2
CHAT_MAX_HISTORY_MESSAGE_CHARS = 4000
CHAT_MAX_HISTORY_TOTAL_CHARS = 12000

# LLM 运行参数：Railway 可以覆盖部署期参数而无需改代码；
# 所有模型调用都只引用这里解析后的值。
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("POETICUS_LLM_MODEL", "deepseek-flash")
LLM_MAX_OUTPUT_TOKENS = _bounded_int(
    "POETICUS_LLM_MAX_OUTPUT_TOKENS",
    1200,
    128,
    2048,
)
LLM_TIMEOUT_SECONDS = 30.0
LLM_MAX_RETRIES = 0

# 单次用户请求最多执行这么多次真实工具调用。
AGENT_MAX_TOOL_CALLS = 2
