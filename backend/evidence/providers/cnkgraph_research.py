"""CNKGraph 研究工具的独立只读 HTTP 客户端。

用于本地非商业研究实验；产品公开部署默认不注册相关 Agent 工具。
将第三方完整 JSON 转为受限的候选信息，避免把卷正文/全量结果交给模型。
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx


class CNKGraphResearchError(RuntimeError):
    """外部查询失败；不同于成功但没有命中。"""


class CNKGraphResearchClient:
    """仅暴露明确允许的研究端点，禁止模型自选 URL。"""

    MAX_RESPONSE_BYTES = 96 * 1024

    def __init__(self) -> None:
        self.base_url = os.getenv(
            "CNKGRAPH_RESEARCH_BASE_URL", "https://open.cnkgraph.com"
        ).rstrip("/")
        self.timeout = 12.0

    async def _post(self, path: str, payload: dict[str, object]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                follow_redirects=False,
            ) as client:
                async with client.stream("POST", path, json=payload) as response:
                    response.raise_for_status()
                    if "json" not in response.headers.get("content-type", "").lower():
                        raise CNKGraphResearchError("CNKGraph 返回非 JSON 数据")
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > self.MAX_RESPONSE_BYTES:
                        raise CNKGraphResearchError("CNKGraph 响应过大，请缩小查询范围")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > self.MAX_RESPONSE_BYTES:
                            raise CNKGraphResearchError("CNKGraph 响应过大，请缩小查询范围")
                        data.extend(chunk)
        except httpx.HTTPStatusError as exc:
            raise CNKGraphResearchError(
                f"CNKGraph HTTP {exc.response.status_code}，请核对查询参数或接口状态"
            ) from exc
        except httpx.RequestError as exc:
            raise CNKGraphResearchError("CNKGraph 网络请求失败或超时") from exc
        except (ValueError, UnicodeDecodeError) as exc:
            raise CNKGraphResearchError("CNKGraph 响应头或编码异常") from exc

        try:
            parsed = json.loads(data)
        except (ValueError, UnicodeDecodeError) as exc:
            raise CNKGraphResearchError("CNKGraph JSON 格式无效") from exc
        if not isinstance(parsed, dict):
            raise CNKGraphResearchError("CNKGraph 返回的数据结构不是对象")
        return parsed

    async def analyze_ci(self, content: str, tune_name: str) -> dict[str, object]:
        """从钦谱/龙谱校验中仅提取可核实的格律疑点。"""
        raw = await self._post(
            "/api/Tool/AnalyzeCi",
            {"Content": content, "TuneName": tune_name, "RhymeBook": "词林正韵"},
        )
        err = raw.get("ErrorMessage")
        if isinstance(err, str) and err.strip():
            raise CNKGraphResearchError("CNKGraph 词律分析报告错误：" + err[:160])

        result: dict[str, object] = {
            "status": "ok",
            "provider": "cnkgraph",
            "query": {"tune_name": tune_name, "content_length": len(content)},
            "rhyme_book": "词林正韵",
            "analyses": [],
            "note": (
                "仅据后世《钦定词谱》／《唐宋词格律》等规则校验格式与押韵。"
                "未报错不等于宋代实际演唱合乐，异文、变格、多音字应结合文献人工判断。"
            ),
        }
        labels = [("钦谱", "QinPuValidationResult"), ("龙谱", "LongPuValidationResult")]
        analyses: list[dict[str, object]] = []
        for name, key in labels:
            item = raw.get(key)
            if item is None:
                continue
            if not isinstance(item, dict):
                raise CNKGraphResearchError(f"CNKGraph {name}结果结构异常")
            wrong_rhymes: list[dict[str, object]] = []
            rhyme_items = item.get("InvalidRhymes") or []
            if not isinstance(rhyme_items, list):
                raise CNKGraphResearchError(f"CNKGraph {name}韵部数据结构异常")
            for group in rhyme_items[:4]:
                if not isinstance(group, dict):
                    continue
                wrong_chars = group.get("WrongChars") or []
                wrong_rhymes.append({
                    "rhyme_category": str(group.get("Category") or "")[:110],
                    "rhyme_chars": str(group.get("RhymeChars") or "")[:100],
                    "wrong_characters": [
                        {
                            "character": str(c.get("Character") or "")[:3],
                            "actual_category": [
                                str(r.get("Category") or "")[:75]
                                for r in (c.get("Refers") or [])[:3]
                                if isinstance(r, dict)
                            ],
                        }
                        for c in wrong_chars[:12]
                        if isinstance(c, dict)
                    ],
                })
            clauses = item.get("Example") or []
            errors = [
                {"clause_index": index, "error": str(clause["ValidationError"])[:150]}
                for index, clause in enumerate(clauses[:120])
                if isinstance(clause, dict) and clause.get("ValidationError")
            ][:10]
            analyses.append({
                "standard": name,
                "tune_name": str(item.get("TuneName") or "")[:60],
                "tune_id": item.get("TuneId"),
                "format_index": item.get("FormatIndex"),
                "format_count": item.get("FormatCount"),
                "format_description": str(item.get("FormatDescription") or "")[:240],
                "invalid_rhymes": wrong_rhymes,
                "clause_errors": errors,
                "has_reported_rhyme_errors": bool(wrong_rhymes),
            })
        if not analyses:
            raise CNKGraphResearchError("CNKGraph 未返回任何可解析的词谱校验结果")
        result["analyses"] = analyses
        return result

    async def search_books(self, query: str) -> dict[str, object]:
        """在古籍中按短关键词检索，保留书卷 ID 与短命中片段。"""
        # 实测可用的 Postman 路由是 /Api/Book/Find，大小写与 Swagger 不同。
        raw = await self._post("/Api/Book/Find", {"key": query, "pageNo": 1})
        error = raw.get("Error")
        if error:
            raise CNKGraphResearchError("CNKGraph 古籍检索失败：" + str(error)[:130])
        count = raw.get("Count")
        if not isinstance(count, int) or count < 0:
            raise CNKGraphResearchError("CNKGraph 古籍检索缺少有效的匹配总数")
        groups = raw.get("Result")
        if groups is None:
            groups = []
        if not isinstance(groups, list):
            raise CNKGraphResearchError("CNKGraph 古籍检索结果结构异常")
        hits: list[dict[str, object]] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            category = str(group.get("Category") or "")[:90]
            books = group.get("Books") or []
            if not isinstance(books, list):
                continue
            for book in books:
                if not isinstance(book, dict):
                    continue
                volumes = book.get("Volumes") or []
                if not isinstance(volumes, list):
                    continue
                for vol in volumes[:2]:
                    if not isinstance(vol, dict):
                        continue
                    pages = vol.get("Pages") or []
                    if not isinstance(pages, list):
                        continue
                    for page in pages[:2]:
                        if not isinstance(page, dict):
                            continue
                        hits.append({
                            "book": str(book.get("Book") or "")[:130],
                            "book_id": str(book.get("BookId") or "")[:60],
                            "category": category,
                            "volume": str(vol.get("Volume") or "")[:90],
                            "volume_id": str(vol.get("VolumeId") or "")[:80],
                            "matched_text": str(page.get("MatchedText") or "")[:100],
                            "before": str(page.get("PreviousText") or "")[-110:],
                            "after": str(page.get("LaterText") or "")[:110],
                        })
                        if len(hits) >= 5:
                            break
                    if len(hits) >= 5:
                        break
                if len(hits) >= 5:
                    break
            if len(hits) >= 5:
                break
        # Count > 0 而当前页结构未给出片段，不能误报无命中。
        status = "no_hit" if count == 0 else "ok" if hits else "partial"
        return {
            "status": status,
            "provider": "cnkgraph",
            "query": query,
            "total_matches_reported": count,
            "hits": hits,
            "note": (
                "只返回检索候选的书卷与短上下文；匹配不等于已证实出处、版本"
                "或文学影响关系。需要时根据书卷 ID 单独查证。"
            ),
        }
