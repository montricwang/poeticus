#!/usr/bin/env python3
"""Generate Qwen3 embeddings for Poeticus work texts on an AutoDL CUDA instance.

Uploads: this script and qwen_gpu_input.jsonl only.
Outputs: qwen3_all_3491.npy and qwen3_all_3491_manifest.json.
No prompt/instruction is used, matching the local 110-poem document-embedding pilot.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np


def load_input(path: Path) -> tuple[list[str], list[str]]:
    ids, texts = [], []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item.get("id"), str) or not isinstance(item.get("text"), str):
            raise ValueError(f"Invalid id/text in input line {n}")
        if not item["text"].strip():
            raise ValueError(f"Empty text in line {n}")
        ids.append(item["id"])
        texts.append(item["text"])
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source IDs found")
    if not ids:
        raise ValueError("Input contains no poems")
    return ids, texts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("qwen_gpu_input.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument(
        "--model",
        default="Qwen/Qwen3-Embedding-0.6B",
        help="Hugging Face model ID or local path to existing model",
    )
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--check-input", action="store_true", help="Validate input without loading GPU"
    )
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    ids, texts = load_input(args.input)
    input_sha256 = hashlib.sha256(args.input.read_bytes()).hexdigest()
    print(f"Read {len(ids)} poems; input SHA256={input_sha256}", flush=True)
    if args.check_input:
        return

    import torch
    from sentence_transformers import SentenceTransformer

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA GPU not found; refusing accidental CPU inference on paid instance"
        )
    print("GPU:", torch.cuda.get_device_name(0), flush=True)
    print("Torch:", torch.__version__, flush=True)
    print("Model:", args.model, flush=True)
    started = time.perf_counter()
    model = SentenceTransformer(args.model, device="cuda")
    print("Model ready (seconds):", round(time.perf_counter() - started, 1), flush=True)

    start = time.perf_counter()
    vectors = model.encode(
        texts,
        batch_size=args.batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    )
    vectors = np.asarray(vectors, dtype=np.float32)
    expected_dim = 1024
    if vectors.shape != (len(texts), expected_dim):
        raise RuntimeError(
            f"Unexpected result: {vectors.shape}; expected {(len(texts), expected_dim)}"
        )
    if not np.isfinite(vectors).all():
        raise RuntimeError("Result contains NaN/Inf")
    norms = np.linalg.norm(vectors, axis=1)
    print(
        "Raw vector L2 norms:",
        f"min={norms.min():.7f}",
        f"median={np.median(norms):.7f}",
        f"max={norms.max():.7f}",
        f"outside_tolerance={np.count_nonzero(np.abs(norms - 1.0) > 0.0003)}",
        flush=True,
    )
    if np.any(norms < 1e-8):
        raise RuntimeError("One or more vectors have near-zero norm; cannot normalize")
    # SentenceTransformer requests normalization; repeat it in float32 to fix
    # imprecision in the model/runtime, without changing cosine similarity.
    vectors = vectors / norms[:, None]
    if not np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=0.0003):
        raise RuntimeError(
            "Vectors still not L2-normalized after float32 normalization"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outfile = args.output_dir / f"qwen3_all_{len(ids)}.npy"
    np.save(outfile, vectors)
    manifest = {
        "model": args.model,
        "input_sha256": input_sha256,
        "source_ids": ids,
        "count": len(ids),
        "dimension": expected_dim,
        "dtype": "float32",
        "normalize_embeddings": True,
        "query_instruction": None,
        "batch_size": args.batch_size,
        "embedding_seconds": round(time.perf_counter() - start, 2),
        "file": outfile.name,
        "file_sha256": hashlib.sha256(outfile.read_bytes()).hexdigest(),
    }
    meta = args.output_dir / f"qwen3_all_{len(ids)}_manifest.json"
    meta.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "EMBEDDED",
        len(ids),
        "elapsed seconds",
        manifest["embedding_seconds"],
        flush=True,
    )
    print("OUTPUT", outfile, outfile.stat().st_size, "bytes", flush=True)
    print("MANIFEST", meta, flush=True)


if __name__ == "__main__":
    main()
