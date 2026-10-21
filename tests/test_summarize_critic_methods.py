"""Synthetic-data checks for the private critic-method statistics script."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.research.summarize_critic_methods import render_markdown, summarize


class CriticMethodSummaryTests(unittest.TestCase):
    def test_entry_counts_differ_from_essay_presence_and_pairs_are_unique(self):
        rows = [
            {"essay_no": 1, "critic": "甲", "_origin_schema": "pilot_v1", "methods": [
                {"code": "IMAGE", "argument_path": "secret copyrighted text"},
                {"code": "IMAGE"},
                {"code": "STRUCTURE"},
            ]},
            {"essay_no": 2, "critic": "甲", "_origin_schema": "article_v2", "methods": [{"code": "IMAGE"}]},
            {"essay_no": 3, "critic": "乙", "_origin_schema": "article_v2", "methods": [{"code": "TEXT_WORD"}]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.jsonl"
            source.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            result = summarize(source, expected_count=3)
        self.assertEqual(result["essays"], 3)
        self.assertEqual(result["methods_total"], 5)
        self.assertEqual(dict(result["method_entries"])["IMAGE"], 3)
        self.assertEqual(dict(result["method_essays"])["IMAGE"], 2)
        self.assertEqual(result["method_pairs"], [("IMAGE", "STRUCTURE", 1)])
        self.assertEqual(dict(result["critic_essays"]), {"甲": 2, "乙": 1})
        self.assertNotIn("secret copyrighted text", render_markdown(result))

    def test_duplicate_essay_number_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.jsonl"
            source.write_text(
                '\n'.join(json.dumps({"essay_no": 1, "methods": []}) for _ in range(2)) + '\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate essay_no"):
                summarize(source)


if __name__ == "__main__":
    unittest.main()
