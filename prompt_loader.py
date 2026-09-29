"""集中加载和组合 Prompt 模板。"""

from functools import lru_cache
from pathlib import Path


PROMPT_ROOT = Path(__file__).resolve().parent / "prompts"
PROMPT_FILES = {
    "output_style": "common/output_style.md",
    "agent_decide": "agent_decide.md",
    "analyze_poem": "analyze_poem.md",
    "chat": "chat.md",
    "evidence_answer": "evidence_answer.md",
}


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """根据注册名称读取 Prompt，避免任意文件路径。"""
    if name not in PROMPT_FILES:
        raise ValueError(f"未知 Prompt：{name}")

    path = PROMPT_ROOT / PROMPT_FILES[name]
    return path.read_text(encoding="utf-8").strip()


def compose_prompt(*names: str) -> str:
    """按顺序组合任务提示词与公共规则。"""
    return "\n\n".join(load_prompt(name) for name in names)
