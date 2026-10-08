from scripts.evals.build_eval_candidates import (
    balanced_sample,
    build_candidate_pool,
    source_hint,
)


def sample_records():
    return [
        {
            "id": "a1",
            "author": "甲",
            "collection": "甲集",
            "cipai": "某调",
            "title": None,
            "content": {
                "text": ["春酲未醒。"],
                "annotations": [
                    "◎春酲：春天醉后的困倦。",
                    "◎风乍起，吹皱一池春水。（五代冯延巳《谒金门》）",
                    "◎摩围：见前《水龙吟》注。",
                ],
                "commentaries": [],
            },
        },
        {
            "id": "a2",
            "author": "甲",
            "collection": "甲集",
            "cipai": "另一调",
            "title": None,
            "content": {
                "text": ["九街灯火。"],
                "annotations": [
                    "◎九街：京师街巷之通称。",
                    "◎客从远方来，遗我双鲤鱼。（古乐府《饮马长城窟行》）",
                ],
                "commentaries": [],
            },
        },
        {
            "id": "b1",
            "author": "乙",
            "collection": "乙集",
            "cipai": "第三调",
            "title": None,
            "content": {
                "text": ["玉花骢上。"],
                "annotations": [
                    "◎玉花骢：骏马名。",
                    "◎身无彩凤双飞翼，心有灵犀一点通。（唐李商隐《无题》）",
                ],
                "commentaries": [],
            },
        },
    ]


def test_build_candidate_pool_selects_only_clean_structural_candidates():
    profile = build_candidate_pool(
        sample_records(),
        headword_limit=10,
        quoted_limit=10,
        seed=1,
    )

    headwords = profile["candidates"]["headword_colon"]
    quotes = profile["candidates"]["quoted_source"]

    assert {item["headword"] for item in headwords} == {"春酲", "九街", "玉花骢"}
    assert len(quotes) == 3
    assert all(item["source_hint"] for item in quotes)
    assert all("见前" not in item["annotation"] for item in headwords)


def test_candidate_pool_keeps_question_only_for_headword_candidates():
    profile = build_candidate_pool(
        sample_records(),
        headword_limit=3,
        quoted_limit=3,
        seed=2,
    )

    assert all(
        item["suggested_question"].startswith("「")
        for item in profile["candidates"]["headword_colon"]
    )
    assert all(
        item["suggested_question"] is None
        for item in profile["candidates"]["quoted_source"]
    )


def test_balanced_sample_rotates_between_collections():
    items = [
        {"collection": "甲集", "text": f"甲{i}"}
        for i in range(10)
    ] + [
        {"collection": "乙集", "text": f"乙{i}"}
        for i in range(2)
    ]

    selected = balanced_sample(items, limit=4, seed=7)
    collections = [item["collection"] for item in selected]

    assert collections.count("乙集") >= 1
    assert len(selected) == 4


def test_source_hint_reads_trailing_source_parenthesis():
    assert (
        source_hint("◎风乍起，吹皱一池春水。（五代冯延巳《谒金门》）")
        == "（五代冯延巳《谒金门》）"
    )
    assert source_hint("◎这里只是一条普通说明。") is None
