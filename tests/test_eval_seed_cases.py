import json
from pathlib import Path

from evals.schema import EvalDataset


SEED_DATASET = Path(__file__).resolve().parents[1] / "evals" / "seed_cases.json"


def test_seed_eval_dataset_matches_schema():
    payload = json.loads(SEED_DATASET.read_text(encoding="utf-8"))

    dataset = EvalDataset.model_validate(payload)

    assert dataset.schema_version == "1"
    assert dataset.dataset_version == 1
    assert len(dataset.cases) == 10


def test_seed_eval_cases_keep_stable_unique_ids():
    payload = json.loads(SEED_DATASET.read_text(encoding="utf-8"))
    dataset = EvalDataset.model_validate(payload)

    ids = [case.id for case in dataset.cases]

    assert len(ids) == len(set(ids))


def test_seed_eval_selection_is_part_of_poem_snapshot():
    payload = json.loads(SEED_DATASET.read_text(encoding="utf-8"))
    dataset = EvalDataset.model_validate(payload)

    for case in dataset.cases:
        if case.input.selection:
            assert case.input.selection in case.input.poem
