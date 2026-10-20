"""Regenerate only the exhaustive API matrix in the CNKGraph capability atlas.

This script reads archived JSON without network access. The human-curated
explanations before the sentinel markers are never touched.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from scripts.experiments.render_cnkgraph_audit import DEFAULT_DATA_DIR, load

START = "<!-- BEGIN GENERATED API MATRIX -->"
END = "<!-- END GENERATED API MATRIX -->"
BACKTICK = chr(96)


def inline(text: object, max_length: int = 120) -> str:
    cleaned = " ".join(str(text or "").split()).replace("|", "／")
    return cleaned[: max_length - 1] + "…" if len(cleaned) > max_length else cleaned


def code(text: object) -> str:
    return BACKTICK + inline(text, 200) + BACKTICK


def observed(row: dict | None) -> str:
    if row is None:
        return "请查 Postman 原路径示例"
    status = row["machine_status"]
    http = row.get("http_status")
    return code(status) + (" (" + str(http) + ")" if http is not None else "")


def shape(row: dict | None) -> str:
    if row is None:
        return "—"
    response = row.get("response") or {}
    keys = response.get("keys") or []
    return inline("、".join(keys[:9]), 95) if keys else inline(response.get("kind", "—"))


def build_catalog(data_dir: Path) -> str:
    manifest = json.loads((data_dir / "api_inventory.json").read_text(encoding="utf-8"))
    records = load(data_dir)["rows"]
    postman_rows = {row["id"]: row for row in records if row["group"] == "Postman 示例"}
    swagger_rows = {
        (row["method"], row["path"]): row for row in records
        if row["group"] == "Swagger 补充"
    }
    swagger = manifest["swagger_operations"]
    postman = manifest["postman_examples"]
    if len(swagger) != 105 or len(postman) != 71:
        raise ValueError("Unexpected source count")
    output = [
        "### A. Swagger 完整 HTTP 操作目录（105 项）",
        "",
        "18 个 Swagger 标签。‘参见 P’表示该操作在清单构建时被视作已有 Postman 覆盖；"
        "这**不是**语义或业务验收。其他项给出 Swagger 补测时的状态。"
        "相关参数 Schema 详见 api_inventory.json / HTML 报告。",
        "",
    ]
    swagger_by_domain: dict[str, list] = defaultdict(list)
    for item in swagger:
        swagger_by_domain[item["domain"]].append(item)
    for domain, entries in swagger_by_domain.items():
        output += ["#### Swagger / " + inline(domain), "",
                   "| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |",
                   "| --- | --- | --- | --- |"]
        for item in entries:
            row = swagger_rows.get((item["method"], item["path"]))
            if item["covered_by_postman"]:
                status = "参见 P 实例"
            else:
                if row is None:
                    raise ValueError(f"Missing Swagger result: {item['method']} {item['path']}")
                status = observed(row) + " · " + row["id"]
            schema = item.get("response_schema", {})
            schema_ref = schema.get("$ref", "") if isinstance(schema, dict) else ""
            return_desc = shape(row)
            if schema_ref:
                return_desc += "; " + inline(schema_ref.rsplit("/", 1)[-1], 50)
            output.append(
                "| " + code(item["method"] + " " + item["path"])
                + " | " + inline(item.get("summary"), 105)
                + " | " + status
                + " | " + return_desc + " |"
            )
        output.append("")
    output += [
        "### B. Postman 原始示例记录（71 项）",
        "",
        "这里**保留同一路由不同输入的全部示例**，以免后来忘记本来有多种查询形式。"
        "‘响应字段’只是这一条输入返回的首层 JSON 键（截断和异常时为空）。",
        "",
    ]
    postman_by_domain: dict[str, list] = defaultdict(list)
    for index, item in enumerate(postman, 1):
        postman_by_domain[item["domain"]].append((index, item))
    for domain, entries in postman_by_domain.items():
        output += ["#### Postman / " + inline(domain), "",
                   "| 编号 | 方法与路径 | 示例用途 / 输入 | 首轮状态 | 响应字段 |",
                   "| --- | --- | --- | --- | --- |"]
        for index, item in entries:
            rid = f"P{index:02d}"
            row = postman_rows[rid]
            sample = item.get("body_fields")
            if sample is None:
                sample = item.get("query") or item.get("variables")
            if isinstance(sample, dict):
                sample = json.dumps(sample, ensure_ascii=False, separators=(",", ":"))
            inp = inline(item.get("name"), 60)
            if sample:
                inp += "；" + code(inline(sample, 70))
            output.append(
                "| " + rid
                + " | " + code(item["method"] + " " + item["path"])
                + " | " + inp
                + " | " + observed(row)
                + " | " + shape(row) + " |"
            )
        output.append("")
    output += [
        "### C. 阅读索引注意事项",
        "",
        "- Swagger 的模板参数（如 {id}）和 Postman 的真实示例 ID 可能只是在文本上不同；"
        "不能按 105+71 推算出独立能力总数。",
        "- 在追查某条接口时先按 P/S 编号打开 HTML，确认真正提交的 test_path、请求体、"
        "HTTP 状态、采样上限、响应结构和失败原因。PDF/CSV/导出接口并没有因此获得授权。",
        "- 需要更新 Swagger 或 Postman 时先比较原始 SHA，再保存新快照。"
        "这份索引由本地已归档的清单生成，不自动联系 CNKGraph。",
        "",
    ]
    return "\n".join(output)


def render(path: Path, data_dir: Path = DEFAULT_DATA_DIR) -> None:
    original = path.read_text(encoding="utf-8")
    if original.count(START) != 1 or original.count(END) != 1:
        raise ValueError("Capability atlas must contain exactly one pair of generated markers")
    appendix = build_catalog(data_dir)
    updated = re.sub(
        re.escape(START) + r".*?" + re.escape(END),
        lambda _: START + "\n\n" + appendix + "\n" + END,
        original,
        flags=re.DOTALL,
    )
    path.write_text(updated, encoding="utf-8")
    print(f"Regenerated {path} ({len(appendix.splitlines())} matrix lines)")


if __name__ == "__main__":
    render(DEFAULT_DATA_DIR / "capability-atlas.md")
