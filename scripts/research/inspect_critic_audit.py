"""Print private Critic sample methods alongside their exact source context.

Read-only reviewer aid: no copyrighted commentary enters the repository or logs
unless a human intentionally invokes this locally.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZipFile

from scripts.research.audit_critic_methods import import_runner, load_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uniform", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--epub", type=Path, required=True)
    parser.add_argument("--private-runner", type=Path, required=True)
    parser.add_argument("--essays", required=True, help="Comma-separated essay numbers")
    parser.add_argument("--context", type=int, default=75, help="Characters on either side of quote")
    parser.add_argument("--max-path", type=int, default=260, help="Method argument path preview length")
    args = parser.parse_args()
    desired = [int(s) for s in args.essays.split(",")]
    rows = {r["essay_no"]: r for r in load_jsonl(args.uniform)}
    manifest = {r["essay_id"]: r for r in load_jsonl(args.manifest)}
    reader = import_runner(args.private_runner)
    cache = {}
    with ZipFile(args.epub) as archive:
        for number in desired:
            row = rows[number]
            metadata = manifest[row["essay_id"]]
            _, paragraphs, _, _ = reader.parse({
                "EPUB文件": metadata["epub_file"],
                "条目锚点": " / ".join(metadata["entry_anchors"]),
            }, archive, cache)
            print(f"\n### #{number} {row['critic']} · {row['poet']}《{row['work']}》")
            print("主论：", row["core_argument"][:300])
            print("限制：", row["limitations"][:430])
            print("特殊：", row["special_observation"][:200])
            for i, method in enumerate(row["methods"], 1):
                print(f"[{i}] {method['code']}：{method['argument_path'][:args.max_path]}")
                for evidence in method["evidence"][:2]:
                    para = paragraphs[evidence["paragraph"] - 1]
                    offset, quote = evidence["char_start"], evidence["quote"]
                    context = para[max(0, offset - args.context):offset + len(quote) + args.context]
                    print(f"  原评[{evidence['paragraph']}]: {context}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
