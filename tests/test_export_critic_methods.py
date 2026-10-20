"""Tests for the private research-card JSONL exporter (synthetic data only)."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.research.export_critic_methods import collect_records, write_export


class CriticExportTest(unittest.TestCase):
    def test_two_schema_records_keep_data_and_sort(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = root / "records"
            records.mkdir()
            pilot = {"essay_no": 1, "essay_id": "one", "moves": [{"evidence": [{"quote": "old"}]}]}
            newer = {"essay_no": 2, "essay_id": "two", "methods": [{"evidence": [{"quote": "new"}]}]}
            (records / "0002_two.json").write_text(json.dumps(newer))
            (records / "0001_one.json").write_text(json.dumps(pilot))
            rows, meta = collect_records(records, 2)
            output = root / "merged.jsonl"
            result = write_export(rows, meta, output)
            saved = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual([row["essay_no"] for row in saved], [1, 2])
            self.assertEqual([row["_record_schema"] for row in saved], ["pilot_v1", "article_v2"])
            self.assertEqual(saved[0]["moves"], pilot["moves"])
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(result["evidence_count"], 2)
            self.assertEqual(json.loads((records / "0001_one.json").read_text()), pilot)

    def test_rejects_wrong_count_and_duplicate_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            records = Path(directory)
            item = {"essay_no": 1, "essay_id": "one", "methods": [{"evidence": []}]}
            (records / "0001_one.json").write_text(json.dumps(item))
            with self.assertRaisesRegex(ValueError, "Expected 2"):
                collect_records(records, 2)
            (records / "0002_two.json").write_text(json.dumps({**item, "essay_no": 2}))
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                collect_records(records, 2)


if __name__ == "__main__":
    unittest.main()
