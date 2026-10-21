"""Regression checks for the private INTERTEXT methodology research pipeline."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.research.intertext_methodology import (
    add_decisions,
    export,
    extract_intertext,
    rebuild_taxonomy,
    show_next,
)


def essay(number: int) -> dict:
    return {
        "essay_no": number,
        "essay_id": f"essay-{number}",
        "analysis_target": "如何证明化用关系？",
        "core_argument": "先证来源，再比差异",
        "limitations": "来源尚有异说",
        "poet": "甲",
        "work": "乙",
        "critic": "丙",
        "source": {"epub_file": f"OEBPS/text{number}.html"},
        "methods": [
            {"code": "INTERTEXT", "argument_path": f"比较原词和新词的语义变化 {number}",
             "evidence": [{"quote": "旧句", "paragraph": 1, "char_start": 0,
                           "paragraph_sha256": "abc"}]},
            {"code": "TEXT_WORD", "argument_path": "细读动词", "evidence": []},
        ],
    }


def decision(identifier: str, action: str = "compare-transform") -> dict:
    return {
        "record_id": identifier,
        "actions": [{
            "key": action, "name": "比异析变", "input": "原作与新作",
            "operation": "逐项比对省略、改写和语气",
            "inference": "判断意义是否改变",
            "boundary": "不能仅凭共享意象认定直接借用",
            "evidence_refs": [0],
        }],
        "rationale": "材料明确比较两个文本的差异",
        "uncertainty": "",
    }


class IntertextMethodologyTests(unittest.TestCase):
    def test_extract_preserves_context_and_evidence(self) -> None:
        rows = extract_intertext([essay(1), essay(2)])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["record_id"], "0001:m0")
        self.assertEqual(rows[0]["evidence"][0]["quote"], "旧句")
        self.assertEqual(rows[0]["essay_context"]["limitations"], "来源尚有异说")
        self.assertEqual(rows[0]["source"]["epub_file"], "OEBPS/text1.html")

    def test_export_add_resume_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "reviewed.jsonl"
            input_path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in [essay(1), essay(2)]),
                encoding="utf-8",
            )
            output = root / "study"
            first = export(input_path, output, expected=2)
            self.assertEqual(first["record_count"], 2)
            self.assertEqual(export(input_path, output, expected=2)["export_sha256"],
                             first["export_sha256"])
            self.assertEqual(len(show_next(output, 10, 0)), 2)
            result = add_decisions(output, [decision("0001:m0")])
            self.assertEqual(result["remaining"], 1)
            self.assertEqual([row["record_id"] for row in show_next(output, 10, 0)],
                             ["0002:m0"])
            with self.assertRaisesRegex(ValueError, "Already coded"):
                add_decisions(output, [decision("0001:m0")])
            add_decisions(output, [decision("0002:m0")])
            summary = rebuild_taxonomy(output)
            self.assertEqual(summary["reviewed_count"], 2)
            self.assertEqual(summary["categories"][0]["occurrences"], 2)
            self.assertEqual(summary["categories"][0]["representative_record_ids"],
                             ["0001:m0", "0002:m0"])

    def test_invalid_evidence_reference_does_not_mutate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "source.jsonl"
            input_path.write_text(json.dumps(essay(3), ensure_ascii=False) + "\n",
                                  encoding="utf-8")
            output = root / "study"
            export(input_path, output, expected=1)
            bad = decision("0003:m0")
            bad["actions"][0]["evidence_refs"] = [4]
            with self.assertRaisesRegex(ValueError, "invalid evidence_refs"):
                add_decisions(output, [bad])
            self.assertEqual(show_next(output, 10, 0)[0]["record_id"], "0003:m0")

    def test_export_does_not_overwrite_changed_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "source.jsonl"
            input_path.write_text(json.dumps(essay(3), ensure_ascii=False) + "\n",
                                  encoding="utf-8")
            output = root / "study"
            export(input_path, output, expected=1)
            modified = essay(3)
            modified["methods"][0]["argument_path"] = "新的论证路径"
            input_path.write_text(json.dumps(modified, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs"):
                export(input_path, output, expected=1)


if __name__ == "__main__":
    unittest.main()
