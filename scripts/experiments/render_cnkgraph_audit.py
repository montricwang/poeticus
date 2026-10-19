"""Render the recorded CNKGraph smoke results as a self-contained dark HTML review UI.

Offline only: loads local JSON files, never sends HTTP requests. Reviewer annotations
live in the browser (localStorage) and can be exported as JSON; they are not
written to the repository by the report.

Usage:
    .venv/bin/python -m scripts.experiments.render_cnkgraph_audit
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT / "docs" / "research" / "cnkgraph"
DEFAULT_OUTPUT = DEFAULT_DATA_DIR / "cnkgraph_audit_report.html"

CATEGORY = {
    "人物": "人物", "People": "人物", "Biography": "人物生平",
    "古籍库": "古籍", "Book": "古籍",
    "地理": "地理", "Map": "地理", "SilkRoad": "丝路",
    "字典": "字典", "Char": "字典",
    "工具": "工具", "Tool": "工具", "Label": "实体标注",
    "年历": "年历", "Calendar": "年历",
    "曲谱": "曲谱", "QuTune": "曲谱",
    "类书": "类书", "Category": "类书",
    "词汇、典故": "典故词汇", "Glossary": "典故词汇",
    "词谱": "词谱", "CiTune": "词谱",
    "诗文库": "诗文", "Writing": "诗文", "Poem": "诗文",
    "韵典": "韵典", "Rhyme": "韵典",
    "Mcp": "协议服务", "WeChat": "其他服务",
}
RANKED = [
    "人物", "人物生平", "古籍", "地理", "丝路", "字典", "工具",
    "实体标注", "年历", "曲谱", "类书", "典故词汇", "词谱",
    "诗文", "韵典", "协议服务", "其他服务",
]


def load(data_dir: Path) -> dict[str, Any]:
    manifest = json.loads((data_dir / "api_inventory.json").read_text(encoding="utf-8"))
    examples = manifest["postman_examples"]
    swagger = manifest["swagger_operations"]
    batches = [
        json.loads((data_dir / f"probe_batch_{i}.json").read_text(encoding="utf-8"))["results"]
        for i in range(5)
    ]
    if len(examples) != 71 or sum(map(len, batches[:4])) != len(examples):
        raise ValueError("Expected all 71 Postman examples in original source order")
    if len(batches[4]) != 85 or len(swagger) != 105:
        raise ValueError("Swagger supplementation differs from the audited inventory")
    if len(batches[0]) != 18 or len(batches[1]) != 18 or len(batches[2]) != 18:
        raise ValueError("Unexpected Postman batch boundaries")

    rows: list[dict[str, Any]] = []
    for batch, results in enumerate(batches):
        for offset, result in enumerate(results):
            source = examples[batch * 18 + offset] if batch < 4 else next(
                (x for x in swagger
                 if x["method"] == result["method"] and x["path"] == result["path"]), None
            )
            if source is None:
                raise ValueError(f"Cannot resolve definition for {result['method']} {result['path']}")
            if source["method"] != result["method"] or source["path"] != result["path"]:
                raise ValueError("Results have drifted from the recorded manifest")
            row = {
                "id": "P" + str(batch * 18 + offset + 1).zfill(2)
                if batch < 4 else "S" + str(offset + 1).zfill(2),
                "batch": batch,
                "group": "Postman 示例" if batch < 4 else "Swagger 补充",
                "category": CATEGORY.get(result["domain"], result["domain"]),
                "original_domain": result["domain"],
                "description": result["name"],
                "summary": source.get("summary", ""),
                "method": result["method"],
                "path": result["path"],
                "test_path": result.get("test_path", result["path"]),
                "query": source.get("query", ""),
                "request_example": source.get("body_fields", None),
                "input_variables": source.get("variables", {}),
                "request_schema": source.get("request_schema", {}),
                "response_schema": source.get("response_schema", {}),
                "tested_at": result.get("tested_at_utc", ""),
                "machine_status": result["status"],
                "http_status": result.get("http_status"),
                "mime": result.get("mime"),
                "latency_ms": result.get("latency_ms"),
                "bytes_sampled": result.get("bytes_sampled"),
                "truncated": result.get("truncated", False),
                "response": result.get("response", {}),
                "reason": result.get("reason", ""),
                "error_excerpt": result.get("error_excerpt", ""),
            }
            if row["id"] in {x["id"] for x in rows}:
                raise ValueError(f"Duplicate result ID {row['id']}")
            rows.append(row)
    counters = Counter(r["machine_status"] for r in rows)
    return {
        "source": manifest["source"],
        "counts": {
            "records": len(rows), "postman": len(examples),
            "postman_unique_method_paths": manifest["postman_unique_method_paths_exact"],
            "swagger_operations": len(swagger),
            "swagger_paths": manifest["swagger_path_count"],
            "shape_parseable": counters["valid_shape"],
            "truncated": counters["partial_truncated"],
            "errors": counters["http_error"],
            "unprobed": counters["not_tested"],
            "timed_out": counters["network_error"],
            "other": counters["unexpected_response"],
            "status_counts": dict(counters),
        },
        "categories": [name for name in RANKED if any(r["category"] == name for r in rows)],
        "rows": rows,
    }


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>CNKGraph · API 全域普查报告 · Poeticus</title>
<style>
:root{color-scheme:dark;--bg:#0a0e18;--panel:#111827;--panel2:#151e30;--line:#283449;--ink:#e6eaf3;--muted:#93a1ba;--dim:#687792;--green:#60d5b3;--amber:#f3c176;--red:#f08c90;--blue:#8ab5ff;--violet:#b2a6fc}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(ellipse 85% 560px at 22% -10%,#1b2b42 0%,transparent 73%),var(--bg);font:14px/1.62 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink)}
button,input,select,textarea{font:inherit}button{cursor:pointer}a{color:#a5c8ff;text-decoration:none}a:hover{text-decoration:underline}
.wrapper{max-width:1440px;margin:auto;padding:36px 38px 90px}.eyebrow{font:700 11px/1.3 ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:2.8px;color:var(--green)}h1,h2,h3,p{margin-top:0}h1{font-size:clamp(32px,4vw,53px);letter-spacing:-1.6px;line-height:1.2;margin:14px 0 12px;font-weight:750}h1 em{font-style:normal;color:var(--green)}.intro{max-width:860px;color:var(--muted);font-size:15px;line-height:1.85}.top{display:flex;justify-content:space-between;gap:25px;align-items:flex-start}.stamp{flex:0 0 auto;text-align:right;border:1px solid var(--line);border-radius:12px;padding:15px 17px;background:#111a2a;color:var(--muted);font-size:12px}.stamp strong{display:block;font-size:14px;color:var(--ink);margin-bottom:3px}.nav{display:flex;gap:8px;margin:24px 0 30px;flex-wrap:wrap}.nav a{border:1px solid var(--line);padding:7px 13px;border-radius:30px;color:var(--muted);font-size:12px}.nav a:hover{background:var(--panel2);text-decoration:none;color:#fff}
.metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:11px}.metric{padding:18px 17px 17px;border:1px solid var(--line);background:linear-gradient(140deg,#172135,#111827);border-radius:13px;min-width:0}.metric .label{font-size:12px;color:var(--muted);margin:0 0 9px}.metric .value{font:650 clamp(24px,2.4vw,33px)/1.14 ui-monospace,Consolas,monospace;letter-spacing:-1.5px}.metric .caption{margin:8px 0 0;font-size:11px;color:var(--dim)}
section{margin-top:39px}h2{font-size:19px;letter-spacing:-.2px;margin-bottom:13px}.sub{color:var(--muted);font-size:13px;margin:0 0 15px}.cards{display:grid;grid-template-columns:1.25fr 1fr;gap:15px}.panel{border:1px solid var(--line);background:var(--panel);border-radius:14px;padding:20px 22px}.panel h3{font-size:14px;margin-bottom:9px;color:var(--ink)}.panel p{font-size:13px;line-height:1.75;color:var(--muted);margin-bottom:0}.bullet{padding-left:20px;margin:10px 0 0;color:var(--muted)}.bullet li{padding:5px 0}.bullet b{color:var(--ink);font-weight:600}.caution{border-left:3px solid var(--amber);padding-left:16px}.rule-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:16px}.rule{padding:13px 15px;border:1px solid var(--line);border-radius:11px;color:var(--muted);font-size:12px;background:#101827}.rule strong{color:var(--ink);display:block;font-size:13px;margin-bottom:5px}
.bar{height:13px;background:#253149;border-radius:15px;overflow:hidden;display:flex;margin:21px 0 16px}.seg{height:100%}.legend{display:flex;gap:17px;flex-wrap:wrap;color:var(--muted);font-size:12px}.swatch{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:6px}.status-valid_shape{--c:var(--green)}.status-partial_truncated{--c:var(--amber)}.status-not_tested{--c:var(--dim)}.status-http_error{--c:var(--red)}.status-network_error{--c:#e3a08e}.status-unexpected_response{--c:var(--violet)}.status-partial_empty{--c:var(--amber)}
.badge{display:inline-flex;align-items:center;white-space:nowrap;border:1px solid color-mix(in srgb,var(--c) 35%,transparent);color:var(--c);background:color-mix(in srgb,var(--c) 8%,transparent);border-radius:7px;font:600 11px/1.4 ui-monospace,Consolas,monospace;padding:3px 7px}.badge:before{content:"";width:5px;height:5px;background:var(--c);border-radius:50%;margin-right:7px}
.coverage{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.coverage-item{text-align:left;border:1px solid var(--line);background:#131c2d;padding:12px 14px;border-radius:10px;display:grid;grid-template-columns:100px 1fr 30px;align-items:center;gap:8px;color:var(--ink)}.coverage-item:hover,.coverage-item.active{border-color:#75a9eb;background:#1b2b42}.coverage-item .smallbar{height:7px;display:flex;overflow:hidden;background:#2b394f;border-radius:5px}.coverage-item b{font:650 13px ui-monospace,monospace;text-align:right}.coverage-item span{font-size:12px}.summarylines{font:12px ui-monospace,Consolas,monospace;color:var(--muted)}
.toolbar{position:sticky;top:0;z-index:12;background:#0b111ded;border:1px solid var(--line);backdrop-filter:blur(16px);padding:12px;border-radius:13px;margin:16px 0 12px;display:grid;grid-template-columns:minmax(150px,2fr) repeat(4,minmax(110px,1fr)) auto;gap:8px}.toolbar input,.toolbar select,.review select,.review textarea{background:#0e1523;border:1px solid #354159;color:var(--ink);border-radius:8px;padding:9px 10px;outline:none;min-width:0}.toolbar input:focus,.toolbar select:focus,.review textarea:focus{border-color:#80b3ff}.toolbar button,.export,.mini{background:#19273c;color:#b6d2ff;border:1px solid #354761;border-radius:8px;padding:8px 11px}.toolbar button:hover,.export:hover,.mini:hover{background:#253d59}.countline{color:var(--muted);margin-bottom:10px;font-size:12px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.list-layout{display:grid;grid-template-columns:minmax(0,1.17fr) minmax(370px,.83fr);gap:15px;align-items:start}.table-wrap{border-radius:13px;border:1px solid var(--line);overflow:hidden;min-width:0}table{border-collapse:collapse;width:100%;font-size:12px}th{text-align:left;color:var(--dim);font-weight:600;font-size:11px;letter-spacing:.3px;background:#192233;padding:11px 12px;position:sticky;top:0}td{padding:11px 12px;border-top:1px solid #222c3d;vertical-align:middle}tbody tr{cursor:pointer}tbody tr:hover{background:#1a293b}tbody tr.selected{background:#21354a}td:nth-child(2){white-space:nowrap}th:nth-child(3){min-width:185px}.path{font:12px/1.5 ui-monospace,Consolas,monospace;overflow-wrap:anywhere;color:#d5deed}.desc{margin-top:3px;color:var(--dim);font-size:11px}.method{font:650 11px ui-monospace,monospace;color:var(--blue)}.method.post{color:var(--violet)}.muted{color:var(--muted)}.num{text-align:right;font:12px ui-monospace,monospace;color:var(--muted);white-space:nowrap}.no-data{text-align:center;padding:50px;color:var(--muted)}
.inspector{border:1px solid var(--line);background:linear-gradient(155deg,#152035,#101725);border-radius:13px;position:sticky;top:82px;max-height:calc(100vh - 103px);overflow:auto;scrollbar-color:#46536a transparent}.inspect-head{padding:19px 20px 14px;border-bottom:1px solid var(--line)}.inspect-body{padding:17px 20px 22px}.inspect-head h3{font-size:15px;margin:8px 0 0;line-height:1.45;overflow-wrap:anywhere}.labelrow{display:flex;gap:7px;flex-wrap:wrap;align-items:center}.tag{font-size:11px;color:#c6d0e3;background:#263449;border:1px solid #35445c;border-radius:5px;padding:2px 7px}.small-title{font-size:11px;color:var(--dim);letter-spacing:1.2px;text-transform:uppercase;margin:18px 0 7px;font-weight:700}.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}.kv{background:#0c1422;border:1px solid #26344a;padding:10px 11px;border-radius:8px;overflow-wrap:anywhere}.kv label{display:block;color:var(--dim);font-size:11px;margin-bottom:5px}.kv strong{font:550 12px/1.6 ui-monospace,monospace;color:var(--ink)}.inspect-body pre{white-space:pre-wrap;word-break:break-word;font:11.5px/1.65 ui-monospace,Consolas,monospace;color:#bed7f4;background:#090f1b;border:1px solid #243348;border-radius:8px;padding:12px 13px;max-height:250px;overflow:auto;margin:0}.inspect-body .hint{font-size:12px;color:var(--muted);line-height:1.7}.review{border:1px solid #3d536b;background:#111e31;border-radius:10px;padding:13px;margin-top:17px}.review h4{font-size:13px;margin:0 0 7px}.review label{color:var(--muted);font-size:12px}.review select,.review textarea{width:100%;margin-top:6px}.review textarea{resize:vertical;min-height:74px;font-size:12px}.review-note{font-size:11px;color:var(--dim)}.review-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.resource{color:var(--muted);font-size:12px;line-height:1.8}.resource a{word-break:break-all}.resource code{color:#d0dfef;background:#111d2f;border:1px solid #2b3c52;padding:2px 5px;border-radius:4px}.resource-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.footer{font-size:12px;color:var(--dim);padding-top:20px;border-top:1px solid var(--line);margin-top:40px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
@media(max-width:1170px){.metrics{grid-template-columns:repeat(3,1fr)}.toolbar{grid-template-columns:2fr 1fr 1fr}.list-layout{grid-template-columns:1fr}.inspector{position:relative;top:0;max-height:unset}.coverage{grid-template-columns:1fr 1fr}}
@media(max-width:690px){.wrapper{padding:23px 15px 60px}.top{display:block}.stamp{margin-top:15px;text-align:left}.metrics{grid-template-columns:repeat(2,1fr)}.metric{padding:14px}.cards,.rule-grid,.resource-grid{grid-template-columns:1fr}.coverage{grid-template-columns:1fr}.toolbar{grid-template-columns:1fr 1fr}.toolbar input{grid-column:1/-1}.table-wrap{overflow:auto}th:nth-child(3){min-width:240px}.two{grid-template-columns:1fr}h1{font-size:34px}}
</style>
</head>
<body>
<div class="wrapper">
<header id="top">
 <div class="eyebrow">POETICUS / RESEARCH ASSETS / 2026.10.20</div>
 <div class="top"><div><h1>CNKGraph <em>API 全域普查</em></h1>
 <p class="intro">官方 Postman × Swagger 的只读探测结果。面向逐条人工核对：哪些接口有响应，哪些被截断、报错或未测；什么可以继续验证，什么不能直接接入 Poeticus。</p></div>
 <div class="stamp"><strong>首轮 Smoke Test</strong><span id="tested-time">—</span><div>独立 HTML · 本地离线阅读</div></div></div>
 <div class="nav"><a href="#overview">总览</a><a href="#coverage">领域覆盖</a><a href="#explorer">逐项审阅</a><a href="#methods">方法与限制</a><a href="#sources">官方来源</a></div>
</header>
<section id="overview" style="margin-top:0">
 <div class="metrics">
 <div class="metric"><p class="label">探测记录</p><div class="value" id="metric-total">—</div><p class="caption">含输入变体和补充接口</p></div>
 <div class="metric"><p class="label">Postman 示例</p><div class="value" id="metric-postman">—</div><p class="caption">逐例发送，保留重复案例</p></div>
 <div class="metric"><p class="label">Swagger 操作</p><div class="value" id="metric-swagger">—</div><p class="caption">官方公开规格，不等于全部测试成功</p></div>
 <div class="metric"><p class="label">JSON 可解析</p><div class="value" id="metric-json" style="color:var(--green)">—</div><p class="caption">仅验证响应形式</p></div>
 <div class="metric"><p class="label">响应被截断</p><div class="value" id="metric-truncated" style="color:var(--amber)">—</div><p class="caption">保护性限制 100 KiB</p></div>
 <div class="metric"><p class="label">未实际请求</p><div class="value" id="metric-skipped" style="color:var(--dim)">—</div><p class="caption">导出、协议、登录等限制</p></div>
 </div>
 <div class="cards" style="margin-top:16px">
  <article class="panel caution"><h3>阅读前先区分两个概念</h3>
  <p><strong style="color:var(--ink)">valid_shape ≠ 接口业务有效。</strong> 目前大多数记录只有状态码、耗时和字段结构，尚未保存完整返回正文，也没有逐字段语义复核。返回 200 也可能是空结果、无关结果或业务错误对象。</p>
  <div class="rule-grid"><div class="rule"><strong>可直接核对</strong> 方法 / 路径、状态、耗时、顶层字段、样本与阻塞原因</div><div class="rule"><strong>需要再次实测</strong> 数据正确性、格式变体、实体链接、来源定位、可重复性</div><div class="rule"><strong>尚无许可结论</strong> 商业接入、批量落盘、对外缓存和再分发权限</div></div></article>
  <article class="panel"><h3>值得优先打开的记录</h3>
  <ul class="bullet"><li><b>词谱详情</b>：词牌格式、示例作品和格律字段（P50）</li>
  <li><b>词谱片段匹配</b>：返回候选词牌（P53）</li>
  <li><b>新实体标注</b>：Tool/Label 与 LabelAndResolveEntity（请搜索 Label）</li>
  <li><b>新词律校验</b>：Tool/AnalyzeCi（请搜索 AnalyzeCi），返回的是结构，不代表判断正确</li>
  <li><b>旧自动笺注</b>：Tool/labelize 仍为 404</li></ul></article>
 </div>
 <div class="panel" style="margin-top:15px">
  <h3>探测结果分布</h3><div class="bar" id="global-bar" aria-label="按状态分布"></div>
  <div class="legend" id="status-legend"></div>
 </div>
</section>
<section id="coverage">
 <h2>按领域查看覆盖</h2><p class="sub">上方原始 Postman 包有 12 类；Swagger 另外列出 Biography、Label、Poem、SilkRoad、Mcp 等领域。点击领域可直接筛选下方记录。</p>
 <div id="coverage-grid" class="coverage"></div>
</section>
<section id="explorer">
 <h2>逐项审阅 <span style="color:var(--dim);font-weight:400">/ Explorer</span></h2>
 <p class="sub">点击任意行，右侧显示请求示例、响应形状、错误和人工复核记录。筛选、备注与导出都在本地执行，不会重新调用 CNKGraph。</p>
 <div class="toolbar">
  <input id="search" type="search" placeholder="搜索路径 / 名称 / 参数 / 字段…" aria-label="搜索接口">
  <select id="category-filter" aria-label="领域"><option value="">所有领域</option></select>
  <select id="status-filter" aria-label="响应状态"><option value="">所有状态</option></select>
  <select id="source-filter" aria-label="来源"><option value="">全部来源</option><option value="Postman 示例">Postman</option><option value="Swagger 补充">Swagger 补充</option></select>
  <select id="sort" aria-label="排序"><option value="source">原始清单顺序</option><option value="latency_desc">响应时间：慢→快</option><option value="latency_asc">响应时间：快→慢</option><option value="status">异常优先</option></select>
  <button type="button" id="reset">重置</button>
 </div>
 <div class="countline"><span id="filtered-count"></span><span id="review-count"></span></div>
 <div class="list-layout">
  <div class="table-wrap"><table><thead><tr><th style="width:57px">编号</th><th style="width:64px">方法</th><th>接口 / 描述</th><th>状态</th><th style="text-align:right">耗时</th></tr></thead><tbody id="rows"></tbody></table></div>
  <aside class="inspector" id="inspector" aria-label="接口详情">
    <div class="inspect-head"><div class="labelrow"><span class="tag">REVIEW PANEL</span></div><h3>选择左侧任意一条接口</h3></div>
    <div class="inspect-body"><p class="hint">本报告保留原始请求和结构化观测。选择后可人工标记复核状态并导出复核清单。</p></div>
  </aside>
 </div>
 <div style="margin-top:17px;display:flex;gap:10px;flex-wrap:wrap;align-items:center">
   <button class="export" type="button" id="export-review">导出我的复核 JSON</button>
   <span class="muted" style="font-size:12px">复核备注保存在当前浏览器本地；请导出 JSON 以便共享或归档。</span>
 </div>
</section>
<section id="methods">
 <h2>探测方法与失效边界</h2>
 <div class="cards">
 <div class="panel"><h3>这轮实际做了什么</h3><ul class="bullet">
  <li>下载官方 Postman ZIP 与 Swagger OpenAPI，分别记录 SHA-256；逐例保留 71 条 Postman 输入变体。</li>
  <li>低频串行 GET / POST，只读数据或文本分析；每条响应最多读取 102,400 字节。</li>
  <li>保存方法、路径、运行时状态码、耗时、MIME、字段名与首个列表元素的形状。不持久化原始全文或访问凭据。</li>
  <li>Swagger 补测中存在用于触发路径的临时参数；404、400 可能由无效输入引起。</li></ul></div>
 <div class="panel"><h3>这轮不能证明什么</h3><ul class="bullet">
  <li>HTTP 200 + JSON 结构，不说明该输入有真实、正确、完整的知识结果。</li>
  <li>较大的响应被主动截断，不能据此判断实际全量列表结构和记录数。</li>
  <li>单次计时包括网络环境差异，只用于定位慢接口，不能当成 SLA 或 p95。</li>
  <li>未测试高风险批量导出、登录会话或协议写调用；未测并不等于接口不存在。</li>
  <li>所有外部数据的权利状态均需独立确认，不能因公开访问而对外镜像。</li></ul></div></div>
</section>
<section id="sources">
 <h2>来源与复现</h2>
 <div class="panel resource resource-grid">
  <div><strong>官方资源</strong><p><a id="postman-link" target="_blank" rel="noopener noreferrer">Postman 公开示例</a><br><a id="swagger-link" target="_blank" rel="noopener noreferrer">Swagger OpenAPI JSON</a><br><a id="terms-link" target="_blank" rel="noopener noreferrer">开放资源与使用限制</a></p><p>官方说明注明研究学习场景限非商业；商用、缓存与再发布须另行取得明确许可。</p></div>
  <div><strong>本地审计资产</strong><p><code>scripts/experiments/cnkgraph_api_audit.py</code><br><code>docs/research/cnkgraph/api_inventory.json</code><br><code>probe_batch_0.json … probe_batch_4.json</code></p><p>这份 HTML 内嵌上述文件的元数据快照，可直接以 <code>file://</code> 离线打开。JSON 里的记录不会自动更新。</p></div>
 </div>
</section>
<footer class="footer">Poeticus / CNKGraph public API smoke audit · 2026-10-20 · 人工复核前的技术资产，不代表接口可用于商业服务。</footer>
</div>
<script type="application/json" id="report-data">__REPORT_DATA__</script>
<script>
"use strict";
const payload=JSON.parse(document.getElementById("report-data").textContent);
const {rows,source,counts,categories}=payload;
const STATUS={
 valid_shape:["JSON 结构可解析","var(--green)"],
 partial_truncated:["响应截断","var(--amber)"],
 http_error:["HTTP 错误","var(--red)"],
 network_error:["连接 / 超时","var(--red)"],
 not_tested:["未请求","var(--dim)"],
 unexpected_response:["非预期响应","var(--violet)"],
 partial_empty:["返回为空","var(--amber)"]
};
const $=id=>document.getElementById(id);
const escapeHTML=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const niceJson=x=>JSON.stringify(x??null,null,2);
const formatMs=x=>typeof x==="number"?x.toLocaleString("zh-CN")+" ms":"—";
const SK="poeticus-cnkgraph-audit-review-v1";
let reviews={};try{reviews=JSON.parse(localStorage.getItem(SK)||"{}")||{}}catch(err){reviews={}}
let selected=null,filtered=[];
const state={query:"",category:"",status:"",source:"",sort:"source"};
function saveReviews(){try{localStorage.setItem(SK,JSON.stringify(reviews))}catch(err){}}
function badge(status){const name=STATUS[status]?.[0]||status;return '<span class="badge status-'+escapeHTML(status)+'">'+escapeHTML(name)+"</span>"}
function setMetric(key,value){$(key).textContent=value}
setMetric("metric-total",counts.records);setMetric("metric-postman",counts.postman);
setMetric("metric-swagger",counts.swagger_operations);setMetric("metric-json",counts.shape_parseable);
setMetric("metric-truncated",counts.truncated);setMetric("metric-skipped",counts.unprobed);
$("tested-time").textContent=new Date(source.retrieved_at_utc).toLocaleString("zh-CN",{timeZone:"Asia/Shanghai",hour12:false})+" · 北京时间";
for(const [id,key] of [["postman-link","postman_url"],["swagger-link","swagger_url"],["terms-link","terms_url"]]){
 $(id).href=source[key];
}
function stackedBar(list){
 const counter={};for(const row of list)counter[row.machine_status]=(counter[row.machine_status]||0)+1;
 return Object.entries(STATUS).filter(([status])=>counter[status]).map(([status,[label,color]])=>
 '<div class="seg" style="width:'+(counter[status]/list.length*100).toFixed(3)+'%;background:'+color+'" title="'+label+': '+counter[status]+'"></div>').join("");
}
$("global-bar").innerHTML=stackedBar(rows);
$("status-legend").innerHTML=Object.entries(STATUS).filter(([k])=>counts.status_counts[k]).map(([k,[label,color]])=>
 '<span><i class="swatch" style="background:'+color+'"></i>'+escapeHTML(label)+' <b>'+counts.status_counts[k]+'</b></span>').join("");
function coverage(){
 const grid=$("coverage-grid");grid.textContent="";
 for(const cat of categories){
  const list=rows.filter(x=>x.category===cat);
  const btn=document.createElement("button");btn.type="button";btn.className="coverage-item"+(state.category===cat?" active":"");
  btn.innerHTML="<span>"+escapeHTML(cat)+"</span><span class='smallbar'>"+stackedBar(list)+"</span><b>"+list.length+"</b>";
  btn.onclick=()=>{state.category=state.category===cat?"":cat;$("category-filter").value=state.category;coverage();filterAndRender();$("explorer").scrollIntoView({behavior:"smooth"})};
  grid.appendChild(btn);
 }
}
for(const cat of categories)$("category-filter").add(new Option(cat,cat));
for(const [status,[label]] of Object.entries(STATUS))$("status-filter").add(new Option(label,status));
function filterAndRender(){
 const query=state.query.trim().toLocaleLowerCase();
 filtered=rows.filter(r=>{
  if(state.category&&r.category!==state.category)return false;
  if(state.status&&r.machine_status!==state.status)return false;
  if(state.source&&r.group!==state.source)return false;
  if(!query)return true;
  return [r.id,r.category,r.original_domain,r.description,r.summary,r.method,r.path,r.test_path,r.reason,
          JSON.stringify(r.response),JSON.stringify(r.request_example),JSON.stringify(r.response_schema)].join(" ").toLocaleLowerCase().includes(query);
 });
 if(state.sort==="latency_desc")filtered.sort((a,b)=>(b.latency_ms??-1)-(a.latency_ms??-1));
 if(state.sort==="latency_asc")filtered.sort((a,b)=>(a.latency_ms??Infinity)-(b.latency_ms??Infinity));
 if(state.sort==="status"){
   const score={network_error:0,http_error:1,unexpected_response:2,not_tested:3,partial_truncated:4,partial_empty:5,valid_shape:6};
   filtered.sort((a,b)=>(score[a.machine_status]??10)-(score[b.machine_status]??10));
 }
 $("filtered-count").textContent="当前 "+filtered.length+" / "+rows.length+" 条记录";
 $("review-count").textContent="已人工标记 "+Object.values(reviews).filter(x=>x.verdict&&x.verdict!=="pending").length+" 条";
 const table=$("rows");table.replaceChildren();
 if(!filtered.length){const tr=document.createElement("tr");tr.innerHTML='<td colspan="5" class="no-data">没有符合条件的接口</td>';table.append(tr);return}
 const fragment=document.createDocumentFragment();
 for(const row of filtered){
  const tr=document.createElement("tr");tr.dataset.id=row.id;
  if(row.id===selected)tr.classList.add("selected");
  tr.innerHTML='<td class="muted">'+escapeHTML(row.id)+'</td>'+
   '<td><span class="method '+(row.method==="POST"?"post":"")+'">'+escapeHTML(row.method)+'</span></td>'+
   '<td><div class="path">'+escapeHTML(row.path)+'</div><div class="desc">'+escapeHTML(row.category)+' · '+escapeHTML(row.description||row.summary||"—")+'</div></td>'+
   '<td>'+badge(row.machine_status)+(reviews[row.id]?.verdict&&reviews[row.id].verdict!=="pending"?'<div class="desc" style="color:var(--blue)">★ 已复核</div>':"")+'</td>'+
   '<td class="num">'+(row.latency_ms==null?"—":row.latency_ms.toLocaleString("zh-CN"))+'</td>';
  tr.onclick=()=>openRow(row.id);
  fragment.append(tr);
 }
 table.append(fragment);
}
function oneField(label,value){return '<div class="kv"><label>'+escapeHTML(label)+'</label><strong>'+escapeHTML(value==null?"—":value)+'</strong></div>'}
function codeBlock(label,body){return '<div class="small-title">'+escapeHTML(label)+'</div><pre></pre>'}
function openRow(id){
 const r=rows.find(x=>x.id===id);if(!r)return;selected=id;
 for(const tr of document.querySelectorAll("#rows tr"))tr.classList.toggle("selected",tr.dataset.id===id);
 const details=$("inspector");
 let notice="";
 if(r.machine_status==="valid_shape")notice="已确认收到可解析的 JSON 结构；尚未校验字段值的语义、可靠来源与真实业务有效性。";
 if(r.machine_status==="partial_truncated")notice="响应超过 100 KiB，脚本主动终止读取。当前只能确认 HTTP 状态和响应大小上限，完整 JSON 尚未解析。";
 if(r.machine_status==="http_error")notice="当前输入返回 HTTP 错误。尤其 Swagger 补充记录可能使用试探 ID，不能直接认定路由失效。";
 if(r.machine_status==="not_tested")notice="出于批量导出、认证/协议边界或样本缺失，本轮未向服务器发送此请求。";
 if(r.machine_status==="network_error")notice="单次请求连接失败或超时，需要小规模单独复测。";
 if(r.machine_status==="unexpected_response")notice="返回重定向、204 或非 JSON 等特殊响应，需要辨认端点行为后再下结论。";
 const req=r.request_example==null?"未在该来源中提供完整请求体样例":niceJson(r.request_example);
 let html='<div class="inspect-head"><div class="labelrow"><span class="tag">'+escapeHTML(r.id)+'</span><span class="tag">'+escapeHTML(r.group)+'</span>'+badge(r.machine_status)+'</div>'+
  '<h3>'+escapeHTML(r.method+' '+r.path)+'</h3><div style="margin-top:7px;color:var(--muted);font-size:12px">'+escapeHTML(r.description||r.summary||"")+'</div></div>'+
  '<div class="inspect-body"><div class="panel" style="padding:11px 13px;font-size:12px;line-height:1.7;color:var(--muted);background:#0d1929;border-color:#2c3f59">'+escapeHTML(notice)+'</div>'+
  '<div class="small-title">调用情况</div><div class="two">'+oneField("HTTP",r.http_status??"未请求")+oneField("单次耗时",formatMs(r.latency_ms))+
  oneField("MIME",r.mime)+oneField("采样体积",r.bytes_sampled==null?"—":(r.bytes_sampled+" B"))+'</div>'+
  '<div class="small-title">实际提交的路径（保留已知替换值）</div><pre id="actual-path"></pre>'+
  codeBlock("请求体字段 / Postman 输入",req)+codeBlock("响应结构摘要（不是完整响应）",niceJson(r.response))+
  (r.request_schema&&Object.keys(r.request_schema).length?codeBlock("Swagger 请求 Schema",niceJson(r.request_schema)):"")+
  (r.response_schema&&Object.keys(r.response_schema).length?codeBlock("Swagger 响应 Schema",niceJson(r.response_schema)):"")+
  (r.reason?codeBlock("未测试 / 超时原因",r.reason):"")+
  (r.error_excerpt?codeBlock("错误返回节选",r.error_excerpt):"")+
  '<div class="review"><h4>人工核实</h4><p class="review-note">仅保存在这个浏览器，点击“导出”可带走结果。确认业务有效前需核实具体字段、数据来源与授权。</p><label for="review-verdict">复核判断</label><select id="review-verdict"><option value="pending">尚未核实</option><option value="usable">已核验业务数据</option><option value="partial">部分可用 / 有限制</option><option value="invalid">当前不可用 / 错误</option><option value="blocked">授权或条件阻塞</option></select>'+
  '<label for="review-notes">核验记录（证据、样本、待补步骤）</label><textarea id="review-notes" placeholder="例如：已核实一个真实词牌 ID，返回含 3 种体例；仍需确认格式正文。"></textarea>'+
  '<div class="review-controls"><button class="mini" id="review-save" type="button">保存这条复核</button><span class="review-note" id="saved-note"></span></div></div>'+
  '<p class="hint" style="margin:14px 0 0">测试时间：'+escapeHTML(r.tested_at||"—")+' (UTC)<br>来源领域：'+escapeHTML(r.original_domain)+'</p></div>';
 details.innerHTML=html;
 const codeValues=[r.test_path+(r.query?"?"+r.query:""),req,niceJson(r.response)];
 let ptr=0;details.querySelector("#actual-path").textContent=codeValues[ptr++];
 // Only code blocks with a predictable generated label order are present.
 const blocks=[...details.querySelectorAll(".inspect-body > pre")];
 for(let i=1;i<blocks.length;i++){
  const heading=blocks[i].previousElementSibling?.textContent??"";
  const lookup={
   "请求体字段 / Postman 输入":req,
   "响应结构摘要（不是完整响应）":niceJson(r.response),
   "Swagger 请求 Schema":niceJson(r.request_schema),
   "Swagger 响应 Schema":niceJson(r.response_schema),
   "未测试 / 超时原因":r.reason,
   "错误返回节选":r.error_excerpt
  };
  blocks[i].textContent=lookup[heading]??"";
 }
 $("review-verdict").value=reviews[id]?.verdict||"pending";
 $("review-notes").value=reviews[id]?.notes||"";
 $("review-save").onclick=()=>{
  const verdict=$("review-verdict").value,notes=$("review-notes").value.trim();
  reviews[id]={verdict,notes,updated_at:new Date().toISOString()};
  saveReviews();$("saved-note").textContent="已在本机保存";filterAndRender();
 };
 if(window.innerWidth<=1170)details.scrollIntoView({behavior:"smooth",block:"start"});
}
for(const [input,key] of [["search","query"],["category-filter","category"],["status-filter","status"],["source-filter","source"],["sort","sort"]]){
 $(input).addEventListener(input==="search"?"input":"change",event=>{
  state[key]=event.target.value;if(key==="category")coverage();filterAndRender();
 });
}
$("reset").onclick=()=>{
 Object.assign(state,{query:"",category:"",status:"",source:"",sort:"source"});
 for(const id of ["search","category-filter","status-filter","source-filter"])$(id).value="";
 $("sort").value="source";coverage();filterAndRender();
};
$("export-review").onclick=()=>{
 const contents=JSON.stringify({
  format:"poeticus-cnkgraph-manual-review-v1",
  exported_at:new Date().toISOString(),
  inventory_postman_sha256:source.postman_sha256,
  inventory_swagger_sha256:source.swagger_sha256,
  reviews:reviews
 },null,2);
 const blob=new Blob([contents],{type:"application/json;charset=utf-8"});
 const href=URL.createObjectURL(blob);
 const a=document.createElement("a");a.href=href;a.download="cnkgraph_review_"+new Date().toISOString().slice(0,10)+".json";
 a.click();URL.revokeObjectURL(href);
};
coverage();filterAndRender();
</script>
</body></html>'''


def build(output: Path, data_dir: Path) -> None:
    doc = load(data_dir)
    # JSON will live inside a script element: HTML parsing must not see '<'.
    embedded = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(HTML.replace("__REPORT_DATA__", embedded), encoding="utf-8")
    print(f"{output}: {output.stat().st_size:,} bytes, {doc['counts']['records']} probe records")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    options = parser.parse_args()
    build(options.output, options.data_dir)


if __name__ == "__main__":
    main()
