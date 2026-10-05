"""确认后端正式模块可以直接导入，应用入口只负责组装 FastAPI。"""

import importlib


def test_backend_modules_are_importable(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    app_module = importlib.import_module("backend.app")
    graph_module = importlib.import_module("backend.ai.graph")
    model_module = importlib.import_module("backend.ai.model")
    context_module = importlib.import_module("backend.ai.context")
    prompt_module = importlib.import_module("backend.ai.prompt_loader")

    assert app_module.app is not None
    assert graph_module.graph is not None
    assert model_module.client is not None
    assert context_module.PoemContext is not None
    assert prompt_module.compose_prompt is not None


def test_prompt_templates_resolve_from_backend():
    from backend.ai.prompt_loader import load_prompt

    assert load_prompt("chat").strip()
    assert load_prompt("agent_decide").strip()
