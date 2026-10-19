"""Reproducible, read-only CNKGraph public API inventory and low-rate smoke audit.

No authentication, brute-forcing, pagination crawl or bulk downloads. The source
Postman ZIP and Swagger schema are fetched anew; only safe metadata is committed.
Usage: .venv/bin/python -m scripts.experiments.cnkgraph_api_audit --inventory
       .venv/bin/python -m scripts.experiments.cnkgraph_api_audit --probe --batch 0
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

POSTMAN_URL = "https://open.cnkgraph.com/Api/postman.zip"
SWAGGER_URL = "https://open.cnkgraph.com/swagger/v1/swagger.json"
TERMS_URL = "https://cnkgraph.com/Home/OpenResources"
BASE = "https://open.cnkgraph.com"
RESULT_DIR = Path("docs/research/cnkgraph")
# 100 KiB maximum response sample. Streaming avoids accidentally bulk-downloading
# whole books, massive indexes and writings. Response bodies are NEVER persisted.
MAX_BYTES = 102_400
SKIP_PREFIXES = ("/api/mcp", "/api/wechat")
PATH_VALUES = {
    "dynasty": "宋", "dynastyName": "宋", "regionId": "CN3301",
    "regionName": "潮州市", "authorName": "杜甫", "authorId": "17270",
    "writingId": "136925", "writingType": "诗", "pageNo": "0",
    "coupletWords": "天地,古今", "key": "31190", "id": "90",
    "character": "中", "book": "平水韵", "rhymeBook": "平水韵",
    "rhyme": "青", "name": "苏轼", "year": "901",
    "category": "典故", "group": "正史类", "tuneId": "90",
    "formatIndex": "0", "itemId": "0002", "volumeId": "KR7a0001_018",
    "RegionId": "CN3301", "Name": "西湖", "type": "Writing",
    "subId": "1", "targetId": "15188", "author": "杜甫",
    "region": "CN3301", "clauseIndex": "0", "clause": "大江东去",
    "text": "诗词", "Category": "典故",
}
PARAM_RE = re.compile(r"\{\{([^}]+)\}\}|\{([^}]+)\}")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def compact_shape(data: Any) -> dict[str, Any]:
    """Return only shape/identifiers; never copyrighted full text."""
    if isinstance(data, dict):
        out = {"kind": "object", "keys": list(data)[:30]}
        ids = ("id", "Id", "ID", "key", "Key", "writingId", "authorId", "bookId", "name")
        out["id_examples"] = {k: str(data[k])[:75] for k in ids
                              if k in data and isinstance(data[k], (int, str))}
        for key, value in data.items():
            if isinstance(value, list):
                out["list_field"] = key
                out["list_length"] = len(value)
                if value:
                    out["first_item"] = compact_shape(value[0])
                break
        return out
    if isinstance(data, list):
        return {"kind": "array", "length_in_sample": len(data),
                "first_item": compact_shape(data[0]) if data else None}
    return {"kind": type(data).__name__}


def request_keys(body: Any) -> Any:
    if isinstance(body, dict):
        return {k: request_keys(v) for k, v in body.items()}
    if isinstance(body, list):
        return [request_keys(body[0])] if body else []
    if isinstance(body, str):
        return body[:35] if len(body) <= 35 else "<text:%d chars>" % len(body)
    return body


def load_sources() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    archive = requests.get(POSTMAN_URL, timeout=20)
    archive.raise_for_status()
    swagger_response = requests.get(SWAGGER_URL, timeout=20)
    swagger_response.raise_for_status()
    swagger = swagger_response.json()
    manifest: list[dict[str, Any]] = []
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        for info in z.infolist():
            group = info.filename.encode("cp437").decode("gbk", errors="replace").split(".")[0]
            collection = json.loads(z.read(info.filename))
            values = {v["key"]: str(v.get("value", "")) for v in collection.get("variable", [])}
            for n, example in enumerate(collection["item"], 1):
                req = example["request"]
                raw = req["url"]["raw"]
                endpoint = urlsplit(raw.replace("https://{{host}}", BASE))
                payload = req.get("body", {}).get("raw", "")
                try:
                    body = json.loads(payload) if payload else None
                except json.JSONDecodeError:
                    body = None
                manifest.append({
                    "id": "%02d-%02d" % (len({m["domain"] for m in manifest}) + 1, n),
                    "domain": group, "name": example["name"],
                    "method": req["method"].upper(), "path": endpoint.path,
                    "query": endpoint.query, "url_source": urlsplit(raw.replace("https://{{host}}", BASE)).netloc,
                    "variables": values, "body_fields": request_keys(body),
                    "_body": body,
                })
    source = {
        "postman_url": POSTMAN_URL, "postman_sha256": hashlib.sha256(archive.content).hexdigest(),
        "postman_zip_bytes": len(archive.content), "swagger_url": SWAGGER_URL,
        "swagger_sha256": hashlib.sha256(swagger_response.content).hexdigest(),
        "swagger_version": swagger.get("openapi"), "terms_url": TERMS_URL,
        "retrieved_at_utc": utcnow(),
    }
    return {"source": source, "swagger": swagger}, manifest


def normalize_path(path: str) -> str:
    return re.sub(r"/\d+(?=/|$)", "/{id}", re.sub(
        r"/[A-Z]{2}\d+(?=/|$)", "/{region}", path.lower())).rstrip("/")


def substitute(text: str, values: dict[str, str]) -> tuple[str, list[str]]:
    missing: list[str] = []
    def replace(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        value = values.get(name) or PATH_VALUES.get(name) or PATH_VALUES.get(name.lower())
        if not value:
            missing.append(name)
            return match.group(0)
        return str(value)
    return PARAM_RE.sub(replace, text), missing


def build_inventory(sources: dict[str, Any], postman: list[dict[str, Any]]) -> dict[str, Any]:
    paths = sources["swagger"]["paths"]
    operations = []
    for path, entry in paths.items():
        for method, operation in entry.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            operations.append({
                "method": method.upper(), "path": path, "domain": (operation.get("tags") or ["Other"])[0],
                "summary": operation.get("summary", ""),
                "required_path_params": [p["name"] for p in operation.get("parameters", [])
                                         if p.get("in") == "path" and p.get("required")],
                "request_body_required": operation.get("requestBody", {}).get("required", False),
                "request_schema": operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {}),
                "response_schema": operation.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema", {}),
            })
    # Keep all 71 Postman examples distinct, including same path/method with different arguments.
    public = [{k: v for k, v in row.items() if not k.startswith("_")} for row in postman]
    public_ops = {(r["method"], r["path"].lower()) for r in public}
    for op in operations:
        op["covered_by_postman"] = (op["method"], op["path"].lower()) in public_ops
    return {
        "source": sources["source"],
        "postman_count": len(public), "postman_domains": dict(Counter(r["domain"] for r in public)),
        "postman_unique_method_paths_exact": len(public_ops),
        "swagger_method_count": len(operations), "swagger_path_count": len(paths),
        "postman_examples": public, "swagger_operations": operations,
    }


def test_request(row: dict[str, Any], *, session: requests.Session, pause: float) -> dict[str, Any]:
    values = dict(PATH_VALUES)
    values.update(row.get("variables", {}))
    # Preserve examples' real IDs; replace the sole stale example ID by a known
    # successful writing from the historic qingshang experiment.
    values["writingId"] = "136925"
    lower_path = row["path"].lower()
    if lower_path.startswith("/api/book/"):
        values.update(category="史部", group="正史类")
    if lower_path.startswith("/api/category/"):
        values.update(book="钦定古今图书集成")
    if lower_path.startswith("/api/rhyme/"):
        values.update(category="青")
    if lower_path.startswith("/api/glossary/"):
        values.update(category="典故")
    if lower_path.startswith("/api/map/"):
        values.update(Name="西湖")
    path, missing = substitute(row["path"], values)
    result = {"tested_at_utc": utcnow(), "method": row["method"],
              "path": row["path"], "domain": row["domain"], "name": row.get("name", row.get("summary", "")),
              "test_path": path, "status": "not_tested"}
    if missing:
        return {**result, "reason": "missing_path_examples:" + ",".join(missing)}
    if row["method"] not in ("GET", "POST"):
        return {**result, "reason": "non_readonly_method"}
    if any(path.lower().startswith(p) for p in SKIP_PREFIXES):
        return {**result, "reason": "excluded_service_or_session_endpoint"}
    if "/export" in path.lower():
        return {**result, "reason": "potential_bulk_export_not_probed"}
    if row.get("_body") is None and row["method"] == "POST":
        example_bodies = {
            "/api/book/search": "黄鹤楼",
            "/api/glossary/典故": [1000],
            "/api/glossary/典故/find": {"Key": "桃花", "CharIndex": "end"},
            "/api/tool/label": {"Epoch": "宋", "Content": "大江东去，浪淘尽。"},
            "/api/tool/labelandresolveentity": {"Epoch": "宋", "Content": "大江东去，浪淘尽。"},
            "/api/tool/analyzepoem": {"Content": "白日依山尽，黄河入海流。欲穷千里目，更上一层楼。", "RhymeBook": "平水韵"},
            "/api/tool/analyzeci": {"Content": "大江东去，浪淘尽，千古风流人物。", "TuneName": "念奴娇", "RhymeBook": "词林正韵"},
            "/api/tool/analyzecouplet": {"Content": "海内存知己，天涯若比邻。", "RhymeBook": "平水韵"},
        }
        row["_body"] = example_bodies.get(path.lower())
    if row.get("request_body_required") and row.get("_body") is None:
        return {**result, "reason": "no_valid_post_body_sample"}
    body = row.get("_body")
    if row["method"] == "POST" and body is None:
        return {**result, "reason": "no_valid_post_body_sample"}
    q = row.get("query", "")
    q, missing_query = substitute(q, values)
    if missing_query:
        return {**result, "reason": "missing_query_example:" + ",".join(missing_query)}
    url = BASE + path + ("?" + q if q else "")
    if not url.lower().startswith((BASE + "/api/").lower()):
        return {**result, "reason": "unexpected_url"}
    began = time.perf_counter()
    try:
        with session.request(row["method"], url, json=body if row["method"] == "POST" else None,
                             headers={"Accept": "application/json", "Accept-Language": "zh-Hant"},
                             stream=True, timeout=(5, 12), allow_redirects=False) as resp:
            sample = bytearray()
            overflow = False
            for chunk in resp.iter_content(8192):
                if len(sample) + len(chunk) > MAX_BYTES:
                    sample.extend(chunk[:MAX_BYTES-len(sample)])
                    overflow = True
                    break
                sample.extend(chunk)
            mime = resp.headers.get("content-type", "").split(";")[0]
            result.update({"http_status": resp.status_code, "mime": mime,
                           "latency_ms": round((time.perf_counter()-began)*1000),
                           "bytes_sampled": len(sample), "truncated": overflow})
            try:
                payload = json.loads(sample) if not overflow else None
                result["response"] = compact_shape(payload) if payload is not None else {"kind": "unparsed"}
            except (UnicodeDecodeError, json.JSONDecodeError):
                result["response"] = {"kind": "non_json"}
            if 200 <= resp.status_code < 300 and (result["response"]["kind"] in ("object", "array")):
                if result["response"].get("kind") == "array" and result["response"].get("length_in_sample") == 0:
                    result["status"] = "partial_empty"
                elif result["response"].get("kind") == "object" and result["response"].get("keys") == []:
                    result["status"] = "partial_empty"
                else:
                    result["status"] = "valid_shape" if not overflow else "partial_truncated"
            elif resp.status_code in (401, 403, 429):
                result["status"] = "blocked"
            elif resp.status_code >= 400:
                result["status"] = "http_error"
            elif overflow:
                result["status"] = "partial_truncated"
            else:
                result["status"] = "unexpected_response"
            # Bounded short diagnostic on errors only, not copyrighted content.
            if resp.status_code >= 400:
                result["error_excerpt"] = bytes(sample[:160]).decode("utf-8", errors="replace")
    except requests.RequestException as e:
        result.update({"status": "network_error", "reason": type(e).__name__,
                       "latency_ms": round((time.perf_counter()-began)*1000)})
    time.sleep(pause)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--batch", type=int, default=0, help="0-3: 71 samples split into four batches; 4: Swagger-only")
    parser.add_argument("--pause", type=float, default=0.5)
    args = parser.parse_args()
    if not args.inventory and not args.probe:
        parser.error("specify --inventory or --probe")
    sources, postman = load_sources()
    inventory = build_inventory(sources, postman)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    (RESULT_DIR / "api_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.inventory and not args.probe:
        print("Inventory:", inventory["postman_count"], "Postman examples,",
              inventory["swagger_method_count"], "Swagger operations,",
              inventory["swagger_path_count"], "Swagger paths")
        return
    if args.batch < 4:
        rows = postman[args.batch * 18: (args.batch+1)*18]
    elif args.batch == 4:
        # All routes not already covered by same HTTP method and raw/template URL.
        seen = {(r["method"], r["path"].lower()) for r in postman}
        rows = []
        for op in inventory["swagger_operations"]:
            if (op["method"], op["path"].lower()) not in seen:
                rows.append(op)
    else:
        parser.error("batch must be 0..4")
    session = requests.Session()
    outcomes = [test_request(row, session=session, pause=args.pause) for row in rows]
    file = RESULT_DIR / f"probe_batch_{args.batch}.json"
    file.write_text(json.dumps({"source": sources["source"], "batch": args.batch,
                                 "results": outcomes}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print("Batch", args.batch, "operations", len(outcomes), "statuses", dict(Counter(r["status"] for r in outcomes)))
    for result in outcomes:
        print(result["domain"], result["method"], result["test_path"],
              result["status"], result.get("http_status", "-"), result.get("latency_ms", "-"))


if __name__ == "__main__":
    main()
