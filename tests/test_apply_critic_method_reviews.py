"""Synthetic tests; no private literary text is included."""

import copy
import hashlib
import unittest

from scripts.research.apply_critic_method_reviews import apply_reviews


def _row(number=13):
    return {
        "essay_no": number,
        "essay_id": f"essay-{number}",
        "methods": [
            {"code": "COUNTERFACTUAL", "argument_path": "分析景物的动静关系", "evidence": [{"quote": "短引", "paragraph": 1}]},
            {"code": "STRUCTURE", "argument_path": "分析篇章", "evidence": [{"quote": "另一短引", "paragraph": 2}]},
        ],
    }


def _decision(number=13, status="approved"):
    item = {
        "essay_no": number, "essay_id": f"essay-{number}",
        "method_index": 1, "old_code": "COUNTERFACTUAL",
        "path_sha256": hashlib.sha256("分析景物的动静关系".encode()).hexdigest(),
        "status": status,
    }
    item["new_code" if status == "approved" else "proposed_code"] = "IMAGE"
    return item


class ApplyCriticMethodReviewsTest(unittest.TestCase):
    def test_changes_only_approved_label_and_keeps_input_intact(self):
        source = [_row(13), _row(154)]
        before = copy.deepcopy(source)
        result, stats = apply_reviews(source, [_decision(13), _decision(154, "needs_review")])
        self.assertEqual(stats, {"approved": 1, "needs_review": 1})
        self.assertEqual(result[0]["methods"][0]["code"], "IMAGE")
        self.assertEqual(result[0]["methods"][1], before[0]["methods"][1])
        self.assertEqual(result[1], before[1])
        self.assertEqual(source, before)

    def test_review_checks_fingerprint_and_identity(self):
        for key, value in (("essay_id", "wrong"), ("path_sha256", "bad"), ("old_code", "IMAGE")):
            with self.subTest(key=key):
                decision = _decision()
                decision[key] = value
                with self.assertRaisesRegex(ValueError, "mismatch|changed"):
                    apply_reviews([_row()], [decision])

    def test_duplicate_and_unknown_target_fail(self):
        decision = _decision()
        with self.assertRaisesRegex(ValueError, "Duplicate review"):
            apply_reviews([_row()], [decision, decision])
        with self.assertRaisesRegex(ValueError, "Unknown essay"):
            apply_reviews([_row()], [_decision(99)])


if __name__ == "__main__":
    unittest.main()
