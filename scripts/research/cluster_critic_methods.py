"""Offline, exploratory grouping of *argument paths* within a critic method.

Input and every output are private research artifacts. This is a candidate
selection tool for close reading, not a learned taxonomy or Agent router.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path


def extract_paths(source: Path, code: str = "INTERTEXT") -> list[dict]:
    """Keep traceability, but never embed poet, critic, work or quoted evidence."""
    extracted = []
    seen = set()
    with source.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            row = json.loads(line)
            essay_no = row["essay_no"]
            for index, method in enumerate(row.get("methods", [])):
                if method.get("code") != code:
                    continue
                path = method.get("argument_path", "").strip()
                if not path:
                    continue
                key = (essay_no, index)
                if key in seen:
                    raise ValueError(f"Duplicate method identity at line {line_no}: {key}")
                seen.add(key)
                extracted.append({
                    "essay_no": essay_no,
                    "essay_id": row["essay_id"],
                    "method_index": index,
                    "argument_path": path,
                    "critic": row.get("critic", ""),
                    "poet": row.get("poet", ""),
                    "work": row.get("work", ""),
                })
    return extracted


def sample_paths(paths: list[dict], limit: int, seed: int) -> list[dict]:
    if limit < 1:
        raise ValueError("--limit must be positive")
    if limit >= len(paths):
        return paths.copy()
    rng = random.Random(seed)
    indices = sorted(rng.sample(range(len(paths)), limit))
    return [paths[index] for index in indices]


def grouping(paths: list[dict], model_dir: Path, clusters: int) -> tuple[list[dict], float]:
    """Force coarse, *provisional* groups to choose contrasting reading cases."""
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    if clusters < 2 or clusters >= len(paths):
        raise ValueError("--clusters must be between 2 and sample size - 1")
    if not model_dir.is_dir():
        raise FileNotFoundError(f"Local embedding model missing: {model_dir}")

    texts = [item["argument_path"] for item in paths]
    model = SentenceTransformer(str(model_dir), local_files_only=True, device="cpu")
    vectors = np.asarray(model.encode(
        texts, normalize_embeddings=True, batch_size=8, show_progress_bar=True,
    ), dtype=np.float32)
    # Normalized embeddings and cosine similarity: grouping ignores metadata.
    algorithm = KMeans(n_clusters=clusters, random_state=17, n_init=10)
    labels = algorithm.fit_predict(vectors)
    centroids = algorithm.cluster_centers_
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
    similarity = np.sum(vectors * centroids[labels], axis=1)
    score = float(silhouette_score(vectors, labels, metric="cosine"))
    assignments = [
        {**item, "cluster": int(label), "centroid_similarity": round(float(sim), 4)}
        for item, label, sim in zip(paths, labels, similarity)
    ]
    return assignments, score


def review_notes(assignments: list[dict], score: float, source_hash: str, seed: int) -> str:
    counts = Counter(item["cluster"] for item in assignments)
    lines = [
        "# INTERTEXT 初步分组：人工复核用（私有）", "",
        f"- 来源 JSONL SHA-256：`{source_hash}`",
        f"- 抽样：{len(assignments)} 条；随机种子：{seed}",
        f"- Cosine silhouette：{score:.4f}（仅供对照，不是文学质量分数）", "",
        "**这些组是强制划分的候选，不代表发现了真实的子方法。**",
        "必须回看原赏析并确认：同组是否共享论证步骤，而非题材、词句或套话。", "",
    ]
    for cluster, count in counts.most_common():
        group = [x for x in assignments if x["cluster"] == cluster]
        group.sort(key=lambda item: item["centroid_similarity"], reverse=True)
        # Closest examples plus a low-similarity counterexample, not just best cases.
        picks = group[:3] + (group[-1:] if len(group) > 3 else [])
        lines.extend([f"## 组 {cluster}（{count} 条）", ""])
        for item in picks:
            lines.append(
                f"- #{item['essay_no']} / 方法 {item['method_index']} "
                f"/ 相似度 {item['centroid_similarity']:.3f}：{item['argument_path']}"
            )
        lines.append("")
    lines.extend([
        "## 阅读检查", "",
        "- [ ] 每组至少读一篇完整赏析，核对引文及推理过程", 
        "- [ ] 检查组内是否是同一批题材、作品名或关键词造成的假相似", 
        "- [ ] 为分组写出可以执行的分析步骤，并寻找反例", 
        "- [ ] 无法写出步骤的组标记为不成立，不强行命名", "",
    ])
    return "\n".join(lines)


def run(args: argparse.Namespace) -> None:
    repo = Path(__file__).resolve().parents[2]
    output = args.output_dir.resolve()
    if output == repo or repo in output.parents:
        raise ValueError("Private outputs must stay outside the public Git repository")
    paths = extract_paths(args.input, args.code)
    selected = sample_paths(paths, args.limit, args.seed)
    if len(selected) <= args.clusters:
        raise ValueError("Too few records for chosen cluster count")
    intended_files = (output / "assignments_private.jsonl", output / "review_private.md", output / "run_metadata.json")
    if any(file.exists() for file in intended_files):
        raise FileExistsError(f"Output files already exist in {output}; use a new directory")

    source_hash = hashlib.sha256(args.input.read_bytes()).hexdigest()
    print(f"{args.code}: {len(paths)} paths; sampling {len(selected)}, k={args.clusters}", flush=True)
    assignments, score = grouping(selected, args.model_dir, args.clusters)
    output.mkdir(parents=True, exist_ok=True)
    (output / "assignments_private.jsonl").write_text(
        "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in assignments), encoding="utf-8"
    )
    (output / "review_private.md").write_text(
        review_notes(assignments, score, source_hash, args.seed), encoding="utf-8"
    )
    metadata = {
        "source_sha256": source_hash, "method_code": args.code, "available_paths": len(paths),
        "sample_size": len(selected), "seed": args.seed, "clusters": args.clusters,
        "model_dir": str(args.model_dir), "cosine_silhouette": round(score, 4),
        "counts": dict(Counter(a["cluster"] for a in assignments)),
        "note": "Exploratory forced clusters; not validated literary subtypes.",
    }
    (output / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in metadata.items() if k != "model_dir"}, ensure_ascii=False), flush=True)
    print(f"Private review: {output / 'review_private.md'}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Private reviewed JSONL")
    parser.add_argument("--model-dir", type=Path, required=True, help="Local embedding model directory")
    parser.add_argument("--output-dir", type=Path, required=True, help="Private directory outside repository")
    parser.add_argument("--code", default="INTERTEXT")
    parser.add_argument("--limit", type=int, default=120, help="0 is invalid; >= population means all")
    parser.add_argument("--clusters", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20261021)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
