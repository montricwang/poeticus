"""Synthetic tests for the lossless Critic pilot-to-v2 projection."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.research.normalize_critic_methods import (
    atomic_jsonl,
    normalize_record,
    normalize_rows,
)


def _pilot():
    return {
        "essay_no": 1, "essay_id": "one", "source": {"sha256": "source"},
        "poet": "词人甲", "work": "作品甲", "critic": "评论者甲",
        "research_question": "研究什么问题？",
        "method_synthesis": "研究者概括的方法",
        "strength_risk_assessment": "长处与风险",
        "interpretive_limitations": "证据尚有不确定性",
        "audit_status": "逐字校验", "note": "",
        "moves": [{
            "evidence_id": "e1", "paragraph": 2, "char_start": 3,
            "exact_quote": "原文短引", "paragraph_sha256": "hash",
            "method_code": "TEXT_WORD", "method_name": "字词细读",
            "analysis": "从动词变化分析语气", "evidence_comment": "留意上下文",
        }],
    }


def _article():
    return {
        "essay_no": 2, "essay_id": "two", "source": {"sha256": "source"},
        "poet": "词人乙", "work": "作品乙", "critic": "评论者乙",
        "core_argument": "评论的主要论点",
        "analysis_target": "比较旧说", "special_observation": "细读一个虚字",
        "limitations": "仅是假设", "transferable": "核对异文",
        "author_vs_ai": "归纳与原文有别", "analysis_source": "original",
        "methods": [{
            "code": "DEBATE", "argument_path": "反驳旧说",
            "evidence": [{
                "paragraph": 1, "quote": "原文", "char_start": 0,
                "paragraph_sha256": "hash2",
            }],
        }],
    }


class NormalizeCriticMethodsTest(unittest.TestCase):
    def test_pilot_projection_keeps_evidence_and_explicit_missing_fields(self):
        original = _pilot()
        normalized = normalize_record(original)
        self.assertEqual(normalized["_record_schema"], "article_v2")
        self.assertEqual(normalized["_origin_schema"], "pilot_v1")
        self.assertEqual(normalized["analysis_target"], "研究什么问题？")
        self.assertEqual(normalized["core_argument"], "")
        self.assertEqual(normalized["transferable"], "")
        self.assertEqual(normalized["methods"][0]["evidence"][0]["quote"], "原文短引")
        self.assertEqual(normalized["_pilot_original"], original)
        self.assertNotIn("moves", normalized)

    def test_new_record_is_preserved_with_same_shape(self):
        newer = _article()
        normalized = normalize_record(newer)
        self.assertEqual(normalized["methods"], newer["methods"])
        self.assertEqual(normalized["core_argument"], newer["core_argument"])
        self.assertIsNone(normalized["_pilot_original"])
        self.assertEqual(set(normalized), set(normalize_record(_pilot())))

    def test_missing_analysis_source_is_not_silently_fabricated(self):
        newer = _article()
        del newer["analysis_source"]
        normalized = normalize_record(newer)
        self.assertEqual(normalized["analysis_source"], "")
        self.assertEqual(normalized["_missing_fields"], ["analysis_source"])

    def test_jsonl_is_sorted_and_duplicate_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "original.jsonl", root / "uniform.jsonl"
            original = [_article(), _pilot()]
            source.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in original))
            rows, info = normalize_rows(source, 2)
            self.assertEqual([row["essay_no"] for row in rows], [1, 2])
            self.assertEqual(info["methods"], 2)
            self.assertEqual(info["evidence_indices"], 2)
            self.assertEqual(len(atomic_jsonl(rows, output)), 64)
            self.assertEqual(len(output.read_text().splitlines()), 2)
            self.assertEqual(len(source.read_text().splitlines()), 2)
            source.write_text("".join(json.dumps({**original[0], "essay_id": "dup"}) + "\n" for _ in range(2)))
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                normalize_rows(source, 2)
            self.assertEqual(len(output.read_text().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
