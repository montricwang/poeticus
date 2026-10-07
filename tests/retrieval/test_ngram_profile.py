import json

from scripts.retrieval.ngram_profile import (
    count_ngram_occurrences,
    profile_chunks,
)


def _write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_count_ngram_occurrences_respects_punctuation_boundaries():
    counts = count_ngram_occurrences(
        "片片轻鸥，落晚沙。",
        min_n=2,
        max_n=3,
    )

    assert counts == {2: 5, 3: 3}


def test_profile_chunks_counts_terms_without_building_index(tmp_path):
    path = tmp_path / "chunks.jsonl"
    _write_jsonl(
        path,
        [
            {"text": "片片轻鸥，落晚沙。"},
            {"text": "春水碧于天。"},
        ],
    )

    result = profile_chunks(
        path,
        min_n=2,
        max_n=3,
        expected_chunks=2,
    )

    assert result["chunks"] == 2
    assert result["ngram_occurrences"] == {"2": 9, "3": 6}
    assert result["total_ngram_occurrences"] == 15
    assert result["average_ngram_occurrences_per_chunk"] == 7.5
    assert result["zero_term_chunks"] == 0
