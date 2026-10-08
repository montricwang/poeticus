"""Shared locations for private Poeticus data, independent of the shell's CWD.

By default data sits in a sibling directory of the Git checkout. Set the
absolute POETICUS_DATA_ROOT path to relocate it without editing source code.
Nothing in this module creates directories or moves existing assets.
"""
from __future__ import annotations

import os
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def resolve_data_root() -> Path:
    configured = os.getenv("POETICUS_DATA_ROOT", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise ValueError("POETICUS_DATA_ROOT must be an absolute path")
        return path.resolve()
    return (REPOSITORY_ROOT.parent / "poeticus-data").resolve()


DATA_ROOT = resolve_data_root()
READING_ROOT = DATA_ROOT / "reading-corpus"
READING_RAW_ROOT = READING_ROOT / "raw"
READING_NORMALIZED_ROOT = READING_ROOT / "normalized"
READING_REVIEW_ROOT = READING_ROOT / "review"
RETRIEVAL_ROOT = DATA_ROOT / "retrieval"
RETRIEVAL_CORPUS_ROOT = RETRIEVAL_ROOT / "corpus"
MODELS_ROOT = DATA_ROOT / "models"
REPORTS_ROOT = DATA_ROOT / "reports"
EPUB_REPORTS_ROOT = REPORTS_ROOT / "epub-import"
RETRIEVAL_REPORTS_ROOT = REPORTS_ROOT / "retrieval"
EVAL_REPORTS_ROOT = REPORTS_ROOT / "evals"
