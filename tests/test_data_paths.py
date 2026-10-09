"""Git 工作目录不能依赖开发者特定的磁盘路径或当前工作目录。"""
import pytest

from backend import data_paths


def test_default_data_root_is_sibling_of_checkout(monkeypatch, tmp_path):
    monkeypatch.delenv("POETICUS_DATA_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    expected = data_paths.REPOSITORY_ROOT.parent / "poeticus-data"
    assert data_paths.resolve_data_root() == expected.resolve()


def test_explicit_absolute_override(monkeypatch, tmp_path):
    custom = tmp_path / "poeticus-assets"
    monkeypatch.setenv("POETICUS_DATA_ROOT", str(custom))
    assert data_paths.resolve_data_root() == custom.resolve()


def test_relative_override_rejected(monkeypatch):
    monkeypatch.setenv("POETICUS_DATA_ROOT", "relative/poeticus-data")
    with pytest.raises(ValueError, match="absolute"):
        data_paths.resolve_data_root()


def test_canonical_layout_and_no_directory_creation():
    assert data_paths.READING_NORMALIZED_ROOT == data_paths.DATA_ROOT / "reading-corpus/normalized"
    assert data_paths.RETRIEVAL_CORPUS_ROOT == data_paths.DATA_ROOT / "retrieval/corpus"
    assert data_paths.MODELS_ROOT == data_paths.DATA_ROOT / "models"
    assert data_paths.EVAL_REPORTS_ROOT == data_paths.DATA_ROOT / "reports/evals"
