"""Offline checks for the archived CNKGraph report; never call remote APIs."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

from scripts.experiments.render_cnkgraph_audit import DEFAULT_DATA_DIR, build, load


class EmbeddedJSONParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.script_open = False
        self.payload_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.script_open = tag == "script" and ("id", "report-data") in attrs

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.script_open = False

    def handle_data(self, data: str) -> None:
        if self.script_open:
            self.payload_parts.append(data)


def test_report_uses_complete_recorded_batches() -> None:
    report = load(DEFAULT_DATA_DIR)
    counts = report["counts"]
    assert counts["records"] == 156
    assert counts["postman"] == 71
    assert counts["postman_unique_method_paths"] == 64
    assert counts["swagger_operations"] == 105
    assert counts["shape_parseable"] == 92
    assert counts["unprobed"] == 16
    assert sum(counts["status_counts"].values()) == len(report["rows"])
    assert len({record["id"] for record in report["rows"]}) == len(report["rows"])
    assert set(record["group"] for record in report["rows"]) == {
        "Postman 示例", "Swagger 补充"
    }
    assert any(record["path"].lower() == "/api/tool/analyzeci"
               for record in report["rows"])
    assert any(record["path"].lower() == "/api/tool/labelize"
               and record["http_status"] == 404 for record in report["rows"])


def test_html_is_standalone_and_has_json_payload(tmp_path: Path) -> None:
    dest = tmp_path / "report.html"
    build(dest, DEFAULT_DATA_DIR)
    output = dest.read_text(encoding="utf-8")
    assert 'name="color-scheme" content="dark"' in output
    assert "https://fonts.googleapis.com" not in output
    assert '<script src=' not in output
    assert "<script type=\"application/json\" id=\"report-data\">" in output
    parser = EmbeddedJSONParser()
    parser.feed(output)
    parsed = json.loads("".join(parser.payload_parts))
    assert len(parsed["rows"]) == 156
    assert parsed["counts"]["status_counts"]["unexpected_response"] > 0
