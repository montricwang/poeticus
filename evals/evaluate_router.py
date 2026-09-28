"""只评测意图分类，不执行完整 Graph，也不会生成文学回答。"""

import argparse
import json
from pathlib import Path

from intent_router import classify_intent


DATASET_PATH = Path(__file__).with_name("router_cases.json")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Poeticus 意图分类评测（调用真实 LLM）")
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--all", action="store_true", help="运行全部测试题")
    selector.add_argument("--case", help="只运行指定题目，例如 R011")
    args = parser.parse_args(argv)

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    cases = dataset["cases"] if args.all else dataset["cases"][-7:]
    if args.case:
        cases = [case for case in dataset["cases"] if case["id"] == args.case]
        if not cases:
            parser.error(f"找不到题目：{args.case}")

    preferred_count = 0
    acceptable_count = 0

    for case in cases:
        # 直接调用分类节点，不要使用 graph.invoke()，否则细读分支还会生成回答。
        decision = classify_intent(
            {
                "poem": dataset["poem"],
                "question": case["question"],
                "selection": case.get("selection"),
            }
        )

        actual = decision["intent"]
        preferred = case["expected_route"]
        allowed = case.get("allowed_routes", [preferred])
        is_preferred = actual == preferred
        is_acceptable = actual in allowed

        preferred_count += is_preferred
        acceptable_count += is_acceptable

        print(f"\n{case['id']}：{case['question']}")
        print(f"选区：{case.get('selection')}")
        print(f"首选：{preferred}；实际：{actual}")
        print(f"理由：{decision['reason']}")
        print(
            "结果："
            + ("PASS" if is_preferred else "ACCEPTABLE" if is_acceptable else "FAIL")
        )

    total = len(cases)
    print("\n===== 评测结果 =====")
    print(f"首选路径命中：{preferred_count}/{total}")
    print(f"可接受路径命中：{acceptable_count}/{total}")


if __name__ == "__main__":
    main()
