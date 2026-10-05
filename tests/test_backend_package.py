"""The new backend modules and old public imports point to the same implementation."""

import importlib


def test_legacy_imports_resolve_to_new_package(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    import api
    import main
    import intent_router
    import poem_context
    import prompt_loader
    assert api is importlib.import_module("backend.app")
    assert api.chat is importlib.import_module("backend.api.chat").chat
    assert api.chat_stream is importlib.import_module("backend.api.chat").chat_stream
    assert api.analyze is importlib.import_module("backend.api.analysis").analyze
    assert api.health is importlib.import_module("backend.api.service").health
    assert main is importlib.import_module("backend.ai.model")
    assert intent_router is importlib.import_module("backend.ai.graph")
    assert poem_context is importlib.import_module("backend.ai.context")
    assert prompt_loader is importlib.import_module("backend.ai.prompt_loader")


def test_prompt_templates_resolve_from_backend():
    from backend.ai.prompt_loader import load_prompt
    assert load_prompt("chat").strip()
    assert load_prompt("agent_decide").strip()
