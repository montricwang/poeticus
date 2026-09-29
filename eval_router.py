"""LangGraph 意图分类基线评测：使用真实 LLM。"""

import json
import time
from datetime import datetime
from pathlib import Path

from intent_router import classify_intent


POEM = (
    "风卷珠帘自上钩，萧萧乱叶报新秋。"
    "独携纤手上高楼。"
    "缺月向人舒窈窕，三星当户照绸缪。"
    "香生雾縠见纤柔。"
)

CASES_PATH = Path("tests/data/router_cases.json")
REPORT_PATH = Path("reports/router_eval.json")


def main():
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    results = []

    for case in cases:
        start = time.perf_counter()

        try:
            response = classify_intent(
                {
                    "poem": POEM,
                    "question": case["question"],
                    "selection": case["selection"],
                }
            )

            actual = response["intent"]
            reason = response.get("reason", "")
            error = None

        except Exception as exc:
            actual = None
            reason = ""
            error = type(exc).__name__

        duration = round(time.perf_counter() - start, 3)

        passed = actual == case["expected_intent"]

        result = {
            **case,
            "actual_intent": actual,
            "reason": reason,
            "passed": passed,
            "duration_seconds": duration,
            "error": error,
        }

        results.append(result)

        status = "PASS" if passed else "FAIL"

        print(
            f"{case['id']} {status} | "
            f"expected={case['expected_intent']} | "
            f"actual={actual} | {duration}s"
        )

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {
        "time": datetime.now().isoformat(),
        "model": "deepseek-flash",
        "prompt": "prompts/classify_intent.md",
        "total": len(results),
        "passed": sum(r["passed"] for r in results),
        "results": results,
    }

    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n分类结果：{report['passed']}/{report['total']}")
    print(f"详细报告：{REPORT_PATH}")


if __name__ == "__main__":
    main()
