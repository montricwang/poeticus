"""No network or model required: a fake loopback llama-server exercises the batch."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/research/offline_critic_actions.py"
SPEC = importlib.util.spec_from_file_location("offline_critic_actions", SCRIPT)
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


def local_model_response(url, payload=None, timeout=30):
    if url.endswith("/v1/models"):
        return {"data": [{"id": "fake-local-model"}]}
    incoming = json.loads(payload["messages"][1]["content"].split("\n", 1)[1])
    source = incoming["material"][0]
    result = {"operations": [{
        "source_index": source["source_index"],
        "material": "某个动词", "action": "先辨认拟人，再考察场景变化",
        "inference": "动景携带情绪", "boundary": "只针对这一句",
        "evidence_quote": source["excerpts"][0],
    }]}
    return {"choices": [{"message": {"content": json.dumps(result, ensure_ascii=False)},
                         "finish_reason": "stop"}]}


class ExtractionTests(unittest.TestCase):
    def test_discards_existing_method_labels(self):
        groups = app.build_cards({"methods": [{"code": "INTERTEXT", "argument_path": "先找旧诗",
                                               "evidence": [{"quote": "借旧诗的韵味"}]}]})
        self.assertNotIn("INTERTEXT", json.dumps(groups))
        self.assertEqual(groups[0][0]["source_index"], 1)

    def test_quote_verification(self):
        payload = {"operations": [{"source_index": 1, "material": "字词", "action": "核对",
                                   "inference": "拟人", "boundary": "", "evidence_quote": "编造引文"}]}
        with self.assertRaisesRegex(ValueError, "all proposed"):
            app.validate(payload, [{"source_index": 1, "excerpts": ["原始引文"]}], "cards")

    def test_split_very_long_original_paragraph(self):
        groups = app.build_original(["一" * 1100, "二" * 10], 500)
        self.assertEqual(len(groups), 3)
        self.assertEqual(groups[0][0]["source_index"], 1)

    def test_full_path_resumes_and_saves_offline(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            result_dir = root / "results"
            result_dir.mkdir()
            with (result_dir / "critic_methods_reviewed_v2_1505.jsonl").open("w", encoding="utf-8") as fh:
                for i in range(1, 1506):
                    row = {"essay_no": i, "essay_id": f"essay-{i}", "poet": "李白",
                           "work": "菩萨蛮", "methods": [{"code": "TEXT_WORD",
                           "argument_path": "先看拟人效果", "evidence": [{"quote": "把暝色人格化"}]}]}
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            with patch.object(app, "fetch_json", side_effect=local_model_response):
                cmd = ["--data-root", str(root), "--server", "http://127.0.0.1:8091", "--limit", "2"]
                self.assertEqual(app.main(cmd), 0)
                self.assertEqual(app.main(cmd), 0)  # resume, no overwrite
                output = result_dir / "offline_actions_cards_v1" / "records"
                saved = json.loads((output / "0001.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["operations"][0]["evidence_quote"], "把暝色人格化")
                self.assertEqual(len(list(output.glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
