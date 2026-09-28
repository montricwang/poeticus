import json
from pathlib import Path

from intent_router import graph


dataset_path = Path(__file__).with_name("router_cases.json")
dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

# 本轮只运行新增的七道题，避免重复支付前十题的 API 费用。
cases = dataset["cases"][-7:]

preferred_count = 0
acceptable_count = 0

for case in cases:
    result = graph.invoke(
        {
            "poem": dataset["poem"],
            "question": case["question"],
            "selection": case.get("selection"),
        }
    )

    actual = result["intent"]
    preferred = case["expected_route"]

    allowed = case.get(
        "allowed_routes",
        [preferred],
    )

    is_preferred = actual == preferred
    is_acceptable = actual in allowed

    preferred_count += is_preferred
    acceptable_count += is_acceptable

    print(f"\n{case['id']}：{case['question']}")
    print(f"选区：{case.get('selection')}")
    print(f"首选：{preferred}")
    print(f"实际：{actual}")
    print(f"理由：{result['reason']}")

    if is_preferred:
        print("结果：PASS")
    elif is_acceptable:
        print("结果：ACCEPTABLE（合理的替代路径）")
    else:
        print("结果：FAIL")


total = len(cases)

print("\n===== 评测结果 =====")
print(f"首选路径命中：{preferred_count}/{total}")
print(f"可接受路径命中：{acceptable_count}/{total}")
