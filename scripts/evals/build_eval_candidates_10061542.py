"""2026-10-06 15:42 的 Eval 候选抽样入口。

复用上一轮已经验证过的候选筛选逻辑，本轮扩大样本：
- headword_colon: 50 条
- quoted_source: 100 条

输出仍写入 poeticus-data/reports/evals/，用于人工打标，不提交公开仓库。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.data_paths import EVAL_REPORTS_ROOT, READING_NORMALIZED_ROOT

from scripts.evals.build_eval_candidates_10061450 import (
    ROOT,
    build_candidate_pool,
    load_records,
    render_markdown,
)


STAMP = "10061542"
DEFAULT_INPUT = READING_NORMALIZED_ROOT / "all_normalized.json"
DEFAULT_JSON_OUTPUT = EVAL_REPORTS_ROOT / f"eval_candidates_{STAMP}.json"
DEFAULT_MD_OUTPUT = EVAL_REPORTS_ROOT / f"eval_candidates_{STAMP}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="扩大 Eval 候选抽样：50 条词头 + 100 条引文来源"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--headword-limit", type=int, default=50)
    parser.add_argument("--quoted-limit", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20261006)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.headword_limit < 1 or args.quoted_limit < 1:
        raise SystemExit("候选数量必须 >= 1")

    records = load_records(args.input)
    profile = build_candidate_pool(
        records,
        headword_limit=args.headword_limit,
        quoted_limit=args.quoted_limit,
        seed=args.seed,
    )

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.md_output.parent.mkdir(parents=True, exist_ok=True)

    args.json_output.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(
        render_markdown(profile, args.input).replace(
            "# Eval Candidates 10061450",
            f"# Eval Candidates {STAMP}",
            1,
        ),
        encoding="utf-8",
    )

    stats = profile["selection_stats"]
    print(
        f"候选生成完成：短词头 {stats['headword_colon']}；"
        f"引文来源 {stats['quoted_source']}"
    )
    print(f"JSON：{args.json_output}")
    print(f"Markdown：{args.md_output}")
    print("注意：报告含私人出版物派生文本，不要提交公开仓库。")


if __name__ == "__main__":
    main()
