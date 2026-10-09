from unittest.mock import Mock

from backend.retrieval.metadata_store import MetadataStore, WorkMetadata
from backend.retrieval.serving import (
    _dominant_known_dynasty,
    _resolve_target_dynasty,
)


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


def _metadata_with_dynasties(
    *dynasties: str,
    author_counts: dict[str, int] | None = None,
) -> Mock:
    metadata = Mock(spec=MetadataStore)
    metadata.read_works.return_value = {
        str(index): WorkMetadata(
            work_id=str(index),
            title=None,
            author=None,
            dynasty=dynasty,
            source_record_id=None,
        )
        for index, dynasty in enumerate(dynasties)
    }
    metadata.author_dynasty_counts.return_value = author_counts or {}
    return metadata


def test_request_dynasty_takes_priority_without_metadata_queries():
    metadata = _metadata_with_dynasties("唐", author_counts={"宋": 10})

    assert _resolve_target_dynasty(
        metadata,
        aliases={"one"},
        target_dynasty="元",
        current_author="某作者",
    ) == ("元", "request")
    metadata.read_works.assert_not_called()
    metadata.author_dynasty_counts.assert_not_called()


def test_alias_majority_takes_priority_over_author():
    metadata = _metadata_with_dynasties("宋", "宋", "唐", author_counts={"唐": 5})

    assert _resolve_target_dynasty(
        metadata,
        aliases={"one", "two", "three"},
        target_dynasty=None,
        current_author="某作者",
    ) == ("宋", "current_alias")
    metadata.author_dynasty_counts.assert_not_called()


def test_ambiguous_alias_dynasty_falls_back_to_author():
    metadata = _metadata_with_dynasties("唐", "宋", author_counts={"宋": 3})

    assert _resolve_target_dynasty(
        metadata,
        aliases={"one", "two"},
        target_dynasty=None,
        current_author="某作者",
    ) == ("宋", "author_corpus")


def test_ambiguous_sources_keep_dynasty_unknown():
    metadata = _metadata_with_dynasties("唐", "宋", author_counts={"唐": 2, "宋": 2})

    assert _resolve_target_dynasty(
        metadata,
        aliases={"one", "two"},
        target_dynasty=None,
        current_author="某作者",
    ) == (None, "unknown")
