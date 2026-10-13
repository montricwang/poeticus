"""CNKGraph 的外部 HTTP 适配器。

本模块将第三方典故/出处响应整理为内部 EvidenceItem；
当前实现将 HTTP 404 转为未命中，其他 HTTP/网络/JSON 错误显式报错；
404 的实际接口语义仍需核查。
"""
import os
import httpx
from langsmith import traceable

from ..schema import EvidenceItem, EvidenceSource


class CNKGraphError(RuntimeError):
    """CNKGraph 请求或响应异常。"""


class CNKGraphProvider:
    """按证据类型查询 CNKGraph，并转换为统一的 EvidenceItem。"""

    def __init__(self):
        """读取 API 地址，并设置请求超时为 10 秒。"""

        self.base_url = os.getenv("CNKGRAPH_BASE_URL", "https://api.cnkgraph.com")
        self.timeout = 10.0

    async def _request_json(self, path: str, payload: dict[str, object]):
        """向指定路径发送 POST，解析 JSON，并转换已知网络异常。"""

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            ) as client:
                response = await client.post(path, json=payload)
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as exc:
            # 当前把 404 视为未命中；具体业务语义待核实。
            if exc.response.status_code == 404:
                return None

            raise CNKGraphError(
                f"CNKGraph 返回 HTTP {exc.response.status_code}"
            ) from exc

        except httpx.RequestError as exc:
            raise CNKGraphError("CNKGraph 网络请求失败") from exc

        except ValueError as exc:
            raise CNKGraphError("CNKGraph 返回无效 JSON") from exc

    @traceable(
        name="cnkgraph_search",
        run_type="tool",
    )
    async def search(
        self,
        query: str,
        evidence_type: str | None = None,
    ) -> list[EvidenceItem]:
        """根据证据类型选择典故或出处查询。"""

        if evidence_type in (None, "allusion"):
            return await self._search_allusion(query)
        if evidence_type == "reference":
            return await self._search_reference(query)
        raise ValueError("当前仅支持典故或出处查询")

    async def _search_allusion(self, query: str) -> list[EvidenceItem]:
        """查询典故释义和引文，转换成候选证据。"""

        # --- 1. 请求典故接口并检查响应结构 ---

        raw = await self._request_json(
            "/api/glossary/典故/find",
            {
                "key": query,
                "charIndex": "end",
            },
        )
        if raw is None:
            return []

        if isinstance(raw, dict):
            raw = [raw] if raw else []
        if not isinstance(raw, list):
            raise CNKGraphError("CNKGraph 典故响应结构异常")

        # --- 2. 从每条典故中提取释义、引文和书名 ---

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

    async def _search_reference(self, query: str) -> list[EvidenceItem]:
        """查询诗句出处候选，转换成包含作品信息的证据。"""

        # --- 1. 请求出处接口并检查响应结构 ---

        raw = await self._request_json(
            "/api/tool/reference",
            {"content": query},
        )
        if raw is None:
            return []
        if not isinstance(raw, dict):
            raise CNKGraphError("CNKGraph 出处响应结构异常")

        # --- 2. 读取句子及每句对应的出处候选 ---

        sentences = raw.get("Sentences") or []
        if not isinstance(sentences, list):
            raise CNKGraphError("CNKGraph 出处响应缺少 Sentences")

        # --- 3. 提取诗句、作品信息和来源标识 ---

        results = []

        for sentence in sentences:
            if not isinstance(sentence, dict):
                continue

            query_clause = sentence.get("Clause")
            references = sentence.get("References") or []
            if not isinstance(references, list):
                continue

            for reference in references:
                if not isinstance(reference, dict):
                    continue

                clause = reference.get("Clause")
                if not isinstance(clause, str) or not clause:
                    continue

                title = reference.get("Title")
                author = reference.get("Author")
                dynasty = reference.get("Dynasty")
                writing_id = reference.get("WritingId")

                results.append(
                    EvidenceItem(
                        anchor=(
                            query_clause
                            if isinstance(query_clause, str) and query_clause
                            else query
                        ),
                        type="reference",
                        text=clause,
                        source=EvidenceSource(
                            title=title if isinstance(title, str) else None,
                            author=author if isinstance(author, str) else None,
                            work=title if isinstance(title, str) else None,
                        ),
                        provider="cnkgraph",
                        status="candidate",
                        metadata={
                            "dynasty": dynasty,
                            "writing_id": writing_id,
                        },
                    )
                )

        return results
