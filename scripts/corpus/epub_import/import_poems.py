import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--toc", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--glyph-map", type=Path)

    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    output_dir = Path("data/output")
    stem = args.slug.replace("-", "_")

    extracted = output_dir / f"{stem}.json"
    normalized = output_dir / f"{stem}_normalized.json"

    # 1. Extraction
    subprocess.run(
        [
            sys.executable,
            str(script_dir / "extract_poems.py"),
            "--toc",
            args.toc,
            "--author",
            args.author,
            "--slug",
            args.slug,
        ],
        check=True,
    )

    # 2. Normalization
    command = [
        sys.executable,
        str(script_dir / "normalize_poems.py"),
        "--input",
        str(extracted),
        "--output",
        str(normalized),
    ]

    if args.glyph_map:
        command.extend(["--glyph-map", str(args.glyph_map)])

    subprocess.run(command, check=True)

    print(f"\n导入流程完成：{normalized}")


if __name__ == "__main__":
    main()
