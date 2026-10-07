import pytest

from scripts.retrieval.faiss_full_index import (
    assert_compatible_manifest,
    build_signature,
    index_dir_name,
    source_signature,
)


def embedding_manifest(**overrides):
    manifest = {
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "model_fingerprint": "abc123",
        "input_sha256": "deadbeef",
        "chunk_policy": "sentence",
        "embedding_dimension": 1024,
        "dtype": "float16",
        "normalized": True,
        "completed_chunks": 4_822_054,
    }
    manifest.update(overrides)
    return manifest


def test_index_dir_name_exposes_material_parameters(tmp_path):
    artifact = tmp_path / "qwen_sentence_1024"
    assert index_dir_name(
        artifact,
        nlist=512,
        pq_m=256,
        pq_bits=8,
    ) == "qwen_sentence_1024_ivfpq_nlist512_m256_b8"


def test_source_signature_keeps_row_mapping_identity():
    assert source_signature(embedding_manifest()) == {
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "model_fingerprint": "abc123",
        "input_sha256": "deadbeef",
        "chunk_policy": "sentence",
        "embedding_dimension": 1024,
        "dtype": "float16",
        "normalized": True,
        "completed_chunks": 4_822_054,
    }


def test_build_signature_records_serving_contract():
    signature = build_signature(
        embedding_manifest(),
        nlist=512,
        pq_m=256,
        pq_bits=8,
        nprobe=64,
        training_vectors=50_000,
    )

    assert signature["engine"] == "faiss_IndexIVFPQ"
    assert signature["pq_m"] == 256
    assert signature["nprobe"] == 64
    assert signature["training_vectors"] == 50_000
    assert (
        signature["row_id_contract"]
        == "faiss_id == embedding_global_row == chunk_jsonl_logical_row"
    )


@pytest.mark.parametrize(
    "overrides,kwargs",
    [
        ({"normalized": False}, {}),
        ({"embedding_dimension": 1000}, {"pq_m": 256}),
        ({}, {"nlist": 0}),
        ({}, {"training_vectors": 0}),
    ],
)
def test_build_signature_rejects_invalid_configuration(overrides, kwargs):
    params = {
        "nlist": 512,
        "pq_m": 256,
        "pq_bits": 8,
        "nprobe": 64,
        "training_vectors": 50_000,
    }
    params.update(kwargs)

    with pytest.raises(ValueError):
        build_signature(
            embedding_manifest(**overrides),
            **params,
        )


def test_assert_compatible_manifest_detects_parameter_drift():
    signature = build_signature(
        embedding_manifest(),
        nlist=512,
        pq_m=256,
        pq_bits=8,
        nprobe=64,
        training_vectors=50_000,
    )
    existing = {**signature, "pq_m": 128}

    with pytest.raises(ValueError, match="pq_m"):
        assert_compatible_manifest(existing, signature)
