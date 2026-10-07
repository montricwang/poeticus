from backend.retrieval.serving import _dominant_known_dynasty


def test_dominant_known_dynasty_prefers_corpus_majority():
    assert _dominant_known_dynasty(
        {"唐": 12, "唐末宋初": 3}
    ) == "唐"


def test_dominant_known_dynasty_ignores_unknown_labels():
    assert _dominant_known_dynasty(
        {"未知时代": 20, "宋": 4}
    ) == "宋"


def test_dominant_known_dynasty_refuses_top_tie():
    assert _dominant_known_dynasty(
        {"唐": 5, "唐末宋初": 5}
    ) is None


def test_dominant_known_dynasty_returns_none_without_known_label():
    assert _dominant_known_dynasty(
        {"未知时代": 2}
    ) is None
