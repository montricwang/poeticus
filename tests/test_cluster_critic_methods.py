"""Synthetic tests: no books, network or embedding model required."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.research.cluster_critic_methods import extract_paths, review_notes, sample_paths


class ClusterCriticMethodsTest(unittest.TestCase):
    def test_extract_keeps_methods_and_private_identifiers_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input.jsonl"
            source.write_text(json.dumps({
                "essay_no": 9, "essay_id": "demo", "critic": "评论者", "poet": "词人",
                "work": "某词", "methods": [
                    {"code": "INTERTEXT", "argument_path": "对照前后文后辨析借用"},
                    {"code": "TEXT_WORD", "argument_path": "分析语气"},
                    {"code": "INTERTEXT", "argument_path": " 追溯典故的改写方向 "},
                ],
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            paths = extract_paths(source)
            self.assertEqual(len(paths), 2)
            self.assertEqual([x["method_index"] for x in paths], [0, 2])
            self.assertEqual(paths[1]["argument_path"], "追溯典故的改写方向")
            self.assertNotIn("词人", [x["argument_path"] for x in paths])

    def test_sample_is_deterministic_and_does_not_mutate(self):
        population = [{"argument_path": str(i)} for i in range(25)]
        self.assertEqual(sample_paths(population, 7, 19), sample_paths(population, 7, 19))
        self.assertEqual(len(population), 25)
        with self.assertRaises(ValueError):
            sample_paths(population, 0, 19)

    def test_review_contains_prototypes_and_caution(self):
        rows = [
            {"cluster": 0, "centroid_similarity": .9, "essay_no": 1,
             "method_index": 0, "argument_path": "追溯化用"},
            {"cluster": 0, "centroid_similarity": .7, "essay_no": 2,
             "method_index": 1, "argument_path": "比较异文"},
        ]
        note = review_notes(rows, .08, "abc", 12)
        self.assertIn("追溯化用", note)
        self.assertIn("候选", note)
        self.assertIn("SHA-256", note)


if __name__ == "__main__":
    unittest.main()
