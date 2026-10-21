#!/usr/bin/env python3
"""Resumable, offline extraction of concrete critical moves from private critic notes.

The default `cards` pass consumes yesterday's 1505 reviewed records, NOT the
copyrighted EPUB. An optional `original` pass rereads the original EPUB through
the existing private critic_runner.py. Neither input nor outputs enter Git.
Only a local OpenAI-compatible llama.cpp server is supported.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_DATA = Path("/home/montric/projects/poeticus-data/critic-methods")
SCHEMA_VERSION = "offline-actions-v1"
PROMPT_VERSION = "2026-10-21-independent-steps-v1"
SYSTEM = """你研究的是文学批评家如何从材料一步步推出判断，而非给作品写赏析。
请用简体中文，只输出一个合法 JSON 对象，不要 Markdown，不要思考过程。
寻找可复用的*具体论证动作*，例如“找出两句的同一意象→比较语序变化→判断效果”，
不要只写“文本细读”“典故分析”“审美分析”等宽泛方法标签。
一条动作至少包括：使用何种材料(material)、实际做了什么可重复的操作(action)、
得出了什么推论(inference)、这个推论有什么证据边界(boundary)。
不能把研究者的推测冒充原赏析作者的观点；不要自行补充材料之外的事实。
每条动作附一条输入中逐字连续的短引文 evidence_quote，和相应 source_index。
如果材料不足以拆解具体动作，返回空 operations。每篇最多提取 5 条，优先独特且有凭据的动作。
固定 JSON 结构：
{"operations":[{"source_index":1,"material":"...","action":"...","inference":"...","boundary":"...","evidence_quote":"..."}],"uncertainty":"..."}
"""


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=path.name + ".",
            suffix=".tmp", delete=False
        ) as fh:
            tmp = Path(fh.name)
            json.dump(value, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    if len({row["essay_id"] for row in rows}) != len(rows):
        raise ValueError(f"Duplicate essay_id: {path}")
    return sorted(rows, key=lambda item: item["essay_no"])


def build_cards(row: dict) -> list[list[dict]]:
    items = []
    for i, method in enumerate(row.get("methods", []), 1):
        path = str(method.get("argument_path") or "").strip()
        excerpts = [str(e.get("quote") or "").strip() for e in method.get("evidence", [])]
        excerpts = [q for q in excerpts if q]
        if path and excerpts:
            # Do not give the model the preexisting 14-class method label.
            items.append({"source_index": i, "argument_path": path, "excerpts": excerpts})
    if not items:
        return []
    # Each card is usually short; this split also guards unusually large records.
    groups, group, length = [], [], 0
    for item in items:
        size = len(json.dumps(item, ensure_ascii=False))
        if group and length + size > 4400:
            groups.append(group)
            group, length = [], 0
        group.append(item)
        length += size
    if group:
        groups.append(group)
    return groups


def build_original(paragraphs: list[str], chunk_chars: int) -> list[list[dict]]:
    segments = []
    for i, para in enumerate(paragraphs, 1):
        for start in range(0, len(para), chunk_chars):
            segments.append({"source_index": i, "text": para[start:start + chunk_chars]})
    groups, group, length = [], [], 0
    for item in segments:
        size = len(item["text"])
        if group and length + size > chunk_chars:
            groups.append(group)
            group, length = [], 0
        group.append(item)
        length += size
    if group:
        groups.append(group)
    return groups


def local_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    try:
        address = ipaddress.ip_address(host)
        allowed = address.is_private or address.is_loopback
    except ValueError:
        allowed = host.lower() in {"localhost", "host.docker.internal"}
    if parsed.scheme != "http" or not allowed or parsed.username or parsed.password:
        raise ValueError("For offline use, --server must be an http:// local/private address")
    return url.rstrip("/")


class ServerUnavailable(Exception):
    pass


def fetch_json(url: str, payload: dict | None = None, timeout: int = 30) -> dict:
    raw = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, raw, {"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as res:
            return json.load(res)
    except HTTPError as err:
        excerpt = err.read(500).decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {err.code}: {excerpt}") from err
    except (URLError, TimeoutError, OSError) as err:
        raise ServerUnavailable(f"Local llama-server unreachable: {err}") from err


def model_name(base: str) -> str:
    models = fetch_json(base + "/v1/models", timeout=8).get("data", [])
    if not models:
        raise ServerUnavailable("Local llama-server returned no model at /v1/models")
    return str(models[0]["id"])


def interpret_json(text: str) -> dict:
    # Some local templates include a thought section even with JSON mode.
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned).strip()
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        if start < 0:
            raise ValueError("model did not emit JSON")
        result, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    if not isinstance(result, dict) or not isinstance(result.get("operations"), list):
        raise ValueError("model JSON lacks operations list")
    return result


def validate(result: dict, inputs: list[dict], mode: str) -> tuple[list[dict], list[str]]:
    refs = {}
    for entry in inputs:
        values = entry["excerpts"] if mode == "cards" else [entry["text"]]
        refs.setdefault(entry["source_index"], []).extend(values)
    good, warnings = [], []
    for n, op in enumerate(result["operations"][:5], 1):
        if not isinstance(op, dict):
            warnings.append(f"move {n}: not an object")
            continue
        try:
            idx = int(op["source_index"])
            quote = str(op["evidence_quote"]).strip()
            fields = {key: str(op[key]).strip() for key in
                      ("material", "action", "inference", "boundary")}
            if idx not in refs or len(quote) < 3 or not any(quote in v for v in refs[idx]):
                raise ValueError("quote not found verbatim at source_index")
            if not fields["material"] or not fields["action"] or not fields["inference"]:
                raise ValueError("missing substantive material/action/inference")
            good.append({"source_index": idx, **fields, "evidence_quote": quote})
        except (KeyError, ValueError, TypeError) as err:
            warnings.append(f"move {n}: {err}")
    if result["operations"] and not good:
        raise ValueError("all proposed operations failed evidence validation")
    return good, warnings


def infer(base: str, model: str, inputs: list[dict], meta: dict, mode: str,
          max_tokens: int, timeout: int, json_mode: bool) -> dict:
    intro = ("以下是上一轮研究笔记，不是赏析原文；请只从笔记提取动作，不声称通读原文。"
             if mode == "cards" else "以下是赏析原文，按段落号编号。")
    user = intro + "\n" + json.dumps({"metadata": meta, "material": inputs}, ensure_ascii=False)
    request = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if json_mode:
        request["response_format"] = {"type": "json_object"}
    response = fetch_json(base + "/v1/chat/completions", request, timeout=timeout)
    choice = response["choices"][0]
    text = choice["message"].get("content") or ""
    parsed = interpret_json(text)
    if choice.get("finish_reason") == "length":
        raise ValueError("model output truncated (increase --max-tokens)")
    return parsed


def get_private_runner(path: Path):
    name = "poeticus_private_critic_runner"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import private source parser at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def eta(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes // 60}h{minutes % 60:02d}m"


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["cards", "original"], default="cards")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, help="Private output directory (defaults under data-root)")
    parser.add_argument("--server", default="http://127.0.0.1:8091")
    parser.add_argument("--model", help="Local llama-server model ID; autodetect by default")
    parser.add_argument("--limit", type=int, default=3, help="First N essays, default 3 for pilot")
    parser.add_argument("--numbers", help="Comma-separated essay numbers for targeted validation")
    parser.add_argument("--all", action="store_true", help="Process every essay (1505 expected)")
    parser.add_argument("--status", action="store_true", help="Show saved progress without connecting")
    parser.add_argument("--dry-run", action="store_true", help="Check input, no model calls")
    parser.add_argument("--max-tokens", type=int, default=900)
    parser.add_argument("--chunk-chars", type=int, default=3000, help="Original-mode source chunk size")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--max-failures", type=int, default=5,
                        help="Stop early if repeated failures suggest a bad model configuration")
    parser.add_argument("--no-json-mode", action="store_true", help="For older servers without JSON mode")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    if args.chunk_chars < 500 or args.attempts < 1 or args.max_tokens < 200 or args.max_failures < 1:
        raise SystemExit("Check chunk-chars, attempts, max-tokens and max-failures")
    root = args.data_root.expanduser().resolve()
    output = (args.output or root / "results" / f"offline_actions_{args.mode}_v1").expanduser().resolve()
    if not output.is_relative_to(root):
        raise SystemExit("Output must stay under the private --data-root, never in Git")
    manifest = root / "results" / "manifest.jsonl"
    if args.mode == "cards":
        source_file = root / "results" / "critic_methods_reviewed_v2_1505.jsonl"
    else:
        source_file = manifest
    if not source_file.exists():
        raise SystemExit(f"Missing private input: {source_file}")
    rows = load_jsonl(source_file)
    if len(rows) != 1505:
        raise SystemExit(f"Expected 1505 essays, found {len(rows)}; check input version")
    if args.mode == "original":
        # Import only on demand; the original parser needs bs4 + lxml.
        runner = get_private_runner(root / "results" / "critic_runner.py")
        epub_hash = hashlib.sha256((root / "raw" / "唐宋词鉴赏辞典.epub").read_bytes()).hexdigest()
        if epub_hash != rows[0]["source_sha256"]:
            raise SystemExit("EPUB SHA changed since manifest creation")
    if args.numbers and args.all:
        raise SystemExit("Use either --numbers or --all")
    if args.numbers:
        chosen = {int(part.strip()) for part in args.numbers.split(",") if part.strip()}
        targets = [r for r in rows if int(r["essay_no"]) in chosen]
        if len(targets) != len(chosen):
            raise SystemExit("One or more --numbers do not exist in the manifest")
    else:
        targets = rows if args.all else rows[:args.limit]
    if not targets:
        raise SystemExit("No essays selected")
    records = output / "records"
    done = sum((records / f'{r["essay_no"]:04d}.json').exists() for r in rows)
    if args.status:
        failures = len(list((output / "errors").glob("*.json")))
        print(f"mode={args.mode} done={done}/1505 errors={failures} output={output}")
        return 0
    print(f"mode={args.mode} selected={len(targets)} saved={done}/1505 source={source_file}", flush=True)
    if args.dry_run:
        example = targets[0]
        print(f"First essay #{example['essay_no']} has {len(build_cards(example)) if args.mode == 'cards' else 'original'} chunks")
        return 0

    base = local_url(args.server)
    model = args.model or model_name(base)
    config = {"schema": SCHEMA_VERSION, "prompt": PROMPT_VERSION, "mode": args.mode,
              "model": model, "max_tokens": args.max_tokens,
              "chunk_chars": args.chunk_chars, "source_file_sha256": hashlib.sha256(source_file.read_bytes()).hexdigest()}
    config_file = output / "run-config.json"
    if config_file.exists():
        previous = json.loads(config_file.read_text(encoding="utf-8"))
        if config != previous:
            raise SystemExit("Run config changed. Select a NEW private --output for this experiment.")
    else:
        atomic_json(config_file, config)
    print(f"Local model={model}; URL={base}; progress will print after every essay", flush=True)

    started = time.monotonic()
    processed, failures = 0, 0
    for position, row in enumerate(targets, 1):
        no = int(row["essay_no"])
        dest = records / f"{no:04d}.json"
        if dest.exists():
            continue
        begin = time.monotonic()
        print(f"[{position:4d}/{len(targets)}] start #{no:04d} {row.get('poet', '')}《{row.get('work', '')}》", flush=True)
        try:
            if args.mode == "cards":
                chunks = build_cards(row)
            else:
                ps, signature = runner.source(row)
                if [digest(p) for p in ps] != row["paragraph_sha256"]:
                    raise ValueError("EPUB paragraph hashes do not match manifest")
                chunks = build_original(ps, args.chunk_chars)
            all_moves, warnings = [], []
            if not chunks:
                warnings.append("no usable source material; examine existing card quality")
            for ci, chunk in enumerate(chunks, 1):
                print(f"  chunk {ci}/{len(chunks)} -> local GPU model...", flush=True)
                parsed = None
                for attempt in range(1, args.attempts + 1):
                    try:
                        parsed = infer(base, model, chunk,
                                       {"essay_no": no, "work": row.get("work", ""),
                                        "critic": row.get("critic", row.get("critic_raw", "")),
                                        "research_question": str(row.get("analysis_target", ""))[:400],
                                        "existing_limitations": str(row.get("limitations", ""))[:400],
                                        "chunk": ci, "chunks": len(chunks)},
                                       args.mode, args.max_tokens, args.timeout,
                                       not args.no_json_mode)
                        valid, notes = validate(parsed, chunk, args.mode)
                        all_moves.extend(valid)
                        warnings.extend(notes)
                        break
                    except ServerUnavailable:
                        raise
                    except (ValueError, RuntimeError, KeyError, IndexError) as err:
                        if attempt == args.attempts:
                            raise RuntimeError(f"chunk {ci}/{len(chunks)}, attempts exhausted: {err}") from err
                        print(f"  #{no:04d} chunk {ci}: retry {attempt}/{args.attempts}: {err}", flush=True)
            record = {"schema": SCHEMA_VERSION, "mode": args.mode,
                      "essay_no": no, "essay_id": row["essay_id"], "critic": row.get("critic", row.get("critic_raw", "")),
                      "poet": row.get("poet", ""), "work": row.get("work", ""),
                      "source_sha256": row.get("source", {}).get("sha256", row.get("source_sha256")),
                      "input_hash": digest(json.dumps(chunks, ensure_ascii=False, sort_keys=True)),
                      "model": model, "chunks": len(chunks), "operations": all_moves,
                      "warnings": warnings, "elapsed_seconds": round(time.monotonic() - begin, 2)}
            atomic_json(dest, record)
            err_file = output / "errors" / f"{no:04d}.json"
            if err_file.exists():
                err_file.unlink()
            processed += 1
            outcome = f"ok moves={len(all_moves)} warnings={len(warnings)}"
        except ServerUnavailable as err:
            print(f"\nServer stopped: {err}\nNo data lost. Restart with the same command.", file=sys.stderr)
            return 2
        except (ValueError, RuntimeError, OSError) as err:
            failures += 1
            atomic_json(output / "errors" / f"{no:04d}.json",
                        {"essay_no": no, "essay_id": row["essay_id"], "error": str(err)})
            outcome = f"FAILED: {err}"
        elapsed = time.monotonic() - started
        rate = elapsed / max(processed + failures, 1)
        pending = len(targets) - position
        print(f"[{position:4d}/{len(targets)}] #{no:04d} {outcome} "
              f"essay={eta(time.monotonic()-begin)} avg={rate:.1f}s ETA≈{eta(rate*pending)}", flush=True)
        if failures >= args.max_failures:
            print(f"Stopped after {failures} failures. Inspect {output / 'errors'} before resuming.",
                  file=sys.stderr)
            return 1
    total_saved = sum((records / f'{int(r["essay_no"]):04d}.json').exists() for r in rows)
    print(f"Finished this run: newly saved={processed}, failures={failures}, "
          f"total saved={total_saved}/1505")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped by user; saved essays are intact. Re-run to resume.", file=sys.stderr)
        raise SystemExit(130)
