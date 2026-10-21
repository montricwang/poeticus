"""Synthetic checks for applying human critique decisions to fixed samples."""

import unittest

from scripts.research.audit_critic_methods import attach_manual_reviews


class CriticAuditDecisionTest(unittest.TestCase):
    def test_manual_decisions_do_not_change_unsampled_essays(self):
        sample = [
            {"essay_no": 1, "manual_verdict": "pending", "manual_note": ""},
            {"essay_no": 13, "manual_verdict": "pending", "manual_note": ""},
        ]
        reviewed = attach_manual_reviews(sample, {
            "13": {"verdict": "label_mismatch", "note": "标签定义不符合论证方法"},
        })
        self.assertEqual(reviewed, 1)
        self.assertEqual(sample[0]["manual_verdict"], "pending")
        self.assertEqual(sample[1]["manual_verdict"], "label_mismatch")
        self.assertEqual(sample[1]["manual_note"], "标签定义不符合论证方法")

    def test_rejects_non_sampled_or_invalid_decisions(self):
        sample = [{"essay_no": 1, "manual_verdict": "pending", "manual_note": ""}]
        with self.assertRaisesRegex(ValueError, "not in the stratified sample"):
            attach_manual_reviews(sample, {"2": {"verdict": "uncertain", "note": ""}})
        with self.assertRaisesRegex(ValueError, "Malformed"):
            attach_manual_reviews(sample, {"1": {"verdict": "good", "note": ""}})


if __name__ == "__main__":
    unittest.main()
