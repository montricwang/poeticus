"""Checks the archived CNKGraph capability atlas without network access."""

from __future__ import annotations

import re
from pathlib import Path

from scripts.experiments.render_cnkgraph_audit import DEFAULT_DATA_DIR
from scripts.experiments.render_cnkgraph_capability_matrix import (
    END,
    START,
    build_catalog,
    render,
)


def test_full_catalog_matches_all_archived_sources() -> None:
    matrix = build_catalog(DEFAULT_DATA_DIR)
    swagger_rows = re.findall(r"^\| .?(?:GET|POST) /api/|^\| .?POST /mcp", matrix, re.M)
    postman_rows = re.findall(r"^\| P\d{2} \|", matrix, re.M)
    # Source inventory has 105 Swagger operations, 71 Postman examples.
    assert len(swagger_rows) == 105
    assert len(postman_rows) == 71
    assert "Tool/AnalyzeCi" in matrix
    assert "Book/Find" in matrix
    assert "S85" in matrix
    assert "P01" in matrix and "P71" in matrix


def test_matrix_regenerates_without_erasing_human_analysis(tmp_path: Path) -> None:
    original = (DEFAULT_DATA_DIR / "capability-atlas.md").read_text(encoding="utf-8")
    path = tmp_path / "atlas.md"
    path.write_text(original, encoding="utf-8")
    render(path)
    result = path.read_text(encoding="utf-8")
    assert result == original
    assert result.count(START) == 1 and result.count(END) == 1
    assert "未来 Agent" in result and "下次复测" in result
