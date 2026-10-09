from scripts.corpus.bert_ccpoem_embedding_build import (
    fingerprint_model_dir,
    run_signature,
)


def test_bert_ccpoem_signature_records_clause_pooling():
    signature = run_signature(
        input_sha256="corpus",
        model_fingerprint="model",
        shard_size=10_000,
        expected_chunks=123,
    )

    assert signature["chunk_policy"] == "clause"
    assert signature["embedding_dimension"] == 512
    assert signature["pooling"] == "mean_content_tokens_excluding_special"


def test_bert_ccpoem_fingerprint_tracks_model_files(tmp_path):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "vocab.txt").write_text("甲\n乙\n", encoding="utf-8")
    (tmp_path / "pytorch_model.bin").write_bytes(b"weights")

    first = fingerprint_model_dir(tmp_path)
    (tmp_path / "vocab.txt").write_text("甲\n乙\n丙\n", encoding="utf-8")
    second = fingerprint_model_dir(tmp_path)

    assert first != second
