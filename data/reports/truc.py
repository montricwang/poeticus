import json
from pathlib import Path


def truncate_toc(node, max_children=10):
    """
    递归裁剪目录树
    """
    if isinstance(node, list):
        result = []

        for item in node[:max_children]:
            result.append(truncate_toc(item, max_children))

        if len(node) > max_children:
            result.append(
                {
                    "title": f"... ({len(node) - max_children} more children)",
                    "truncated": True,
                }
            )

        return result

    elif isinstance(node, dict):
        result = {}

        for key, value in node.items():
            if key == "children":
                result[key] = truncate_toc(value, max_children)
            else:
                result[key] = value

        return result

    else:
        return node


input_file = Path("epub_structure.json")
output_file = Path("epub_structure_toc_preview.json")


with input_file.open("r", encoding="utf-8") as f:
    data = json.load(f)


data["toc"] = truncate_toc(data["toc"], max_children=10)


with output_file.open("w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)


print(f"saved: {output_file}")
