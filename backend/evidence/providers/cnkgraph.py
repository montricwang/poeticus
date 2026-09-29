import os

import httpx

from ..schema import EvidenceItem, EvidenceSource


class CNKGraphError(RuntimeError):
    """CNKGraph 请求或响应异常。"""


class CNKGraphProvider:
    def __init__(self):
        self.base_url = os.getenv(
            "CNKGRAPH_BASE_URL",
            "https://api.cnkgraph.com",
        )
        self.timeout = 10.0

    async def search(
        self,
        query: str,
        evidence_type: str | None = None,
    ) -> list[EvidenceItem]:
        if evidence_type not in (None, "allusion"):
            raise ValueError("当前仅支持典故查询")

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            ) as client:
                response = await client.post(
                    "/api/glossary/典故/find",
                    json={
                        "key": query,
                        "charIndex": "end",
                    },
                )
                response.raise_for_status()
                raw = response.json()

                # item = raw[0] if isinstance(raw, list) and raw else raw

                # if isinstance(item, dict):
                #     print("返回字段：", list(item.keys()))
                #     print("释义数据：", item.get("Explains"))

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                print(
                    "CNKGraph 返回 404：",
                    exc.response.text[:500],
                )
                return []

            raise CNKGraphError(
                f"CNKGraph 返回 HTTP {exc.response.status_code}"
            ) from exc

        except httpx.RequestError as exc:
            raise CNKGraphError("CNKGraph 网络请求失败") from exc

        except ValueError as exc:
            raise CNKGraphError("CNKGraph 返回无效 JSON") from exc

        # 将第三方响应转换为 Poeticus 的 EvidenceItem。
        if isinstance(raw, dict):
            raw = [raw] if raw else []
        if not isinstance(raw, list):
            raise CNKGraphError("CNKGraph 响应结构异常")

        results = []

        for item in raw:
            if not isinstance(item, dict):
                continue

            explains = item.get("Explains") or []
            quotes = item.get("Quotes") or []

            explanation = (
                explains[0]
                if isinstance(explains, list)
                and explains
                and isinstance(explains[0], dict)
                else {}
            )
            quote = (
                quotes[0]
                if isinstance(quotes, list) and quotes and isinstance(quotes[0], dict)
                else {}
            )

            meaning = explanation.get("Explain")
            original = quote.get("Content")
            book = quote.get("Book")

            parts = []
            if isinstance(meaning, str) and meaning:
                parts.append(f"释义：{meaning}")
            if isinstance(original, str) and original:
                parts.append(f"引文：{original}")

            if not parts:
                continue

            results.append(
                EvidenceItem(
                    anchor=query,
                    type="allusion",
                    text="\n".join(parts),
                    source=(
                        EvidenceSource(title=book)
                        if isinstance(book, str) and book
                        else None
                    ),
                    provider="cnkgraph",
                    status="candidate",
                )
            )

        return results
