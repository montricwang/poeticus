import json

from scripts.retrieval.hybrid_eval import find_probe_work_ids


def test_find_probe_work_ids_matches_text_and_author(tmp_path):
    path = tmp_path / "works.jsonl"
    rows = [
        {
            "work_id": "w1",
            "author": "范仲淹",
            "content": "都来此事，眉间心上，无计相回避。",
        },
        {
            "work_id": "w2",
            "author": "别人",
            "content": "都来此事，眉间心上，无计相回避。",
        },
        {
            "work_id": "w3",
            "author": "范仲淹",
            "content": "其他文本",
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    assert find_probe_work_ids(
        work_path=path,
        probe_text="眉间心上",
        probe_author="范仲淹",
    ) == {"w1"}
