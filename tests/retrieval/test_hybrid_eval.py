import json

from backend.retrieval.fanout import (
    ChannelDescriptor,
    QueryChannelResult,
    RetrievalHit,
)
from backend.retrieval.query_strategy import QueryOrigin, QueryVariant
from scripts.retrieval.hybrid_eval import (
    find_probe_work_ids,
    probe_list_supports,
)


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



def test_probe_list_supports_shows_hit_and_missing_list():
    query = QueryVariant(
        text="完整查询",
        origins=(QueryOrigin(level="passage", start=0, end=4),),
    )
    dense = QueryChannelResult(
        query=query,
        channel=ChannelDescriptor(
            name="dense_faiss_sentence",
            method="dense",
            chunk_policy="sentence",
        ),
        hits=(
            RetrievalHit(
                rank=1,
                chunk_id="c-other",
                work_id="w-other",
                text="other",
            ),
            RetrievalHit(
                rank=2,
                chunk_id="c-target",
                work_id="w-target",
                text="target",
                score=0.7,
                score_name="ann_inner_product",
            ),
        ),
    )
    lexical = QueryChannelResult(
        query=query,
        channel=ChannelDescriptor(
            name="lexical_bm25_sentence",
            method="lexical",
            chunk_policy="sentence",
        ),
        hits=(
            RetrievalHit(
                rank=1,
                chunk_id="c-other",
                work_id="w-other",
                text="other",
            ),
        ),
    )

    supports = probe_list_supports(
        [dense, lexical],
        {"w-target"},
    )

    assert supports[0]["rank"] == 2
    assert supports[0]["text"] == "target"
    assert supports[1]["rank"] is None
