"""CNKGraph 研究工具的独立只读 HTTP 客户端。

用于本地非商业研究实验；产品公开部署默认不注册相关 Agent 工具。
将第三方完整 JSON 转为受限的候选信息，避免把卷正文/全量结果交给模型。
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote

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

    async def _get(self, path: str) -> object:
        return await self._request_json("GET", path)

    async def _post(
        self, path: str, payload: dict[str, object],
        *, allow_book_no_hit: bool = False,
    ) -> object:
        return await self._request_json(
            "POST", path, payload, allow_book_no_hit=allow_book_no_hit,
        )

    async def _request_json(
        self, method: str, path: str, payload: dict[str, object] | None = None,
        *, allow_book_no_hit: bool = False,
    ) -> object:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                follow_redirects=False,
            ) as client:
                async with client.stream(method, path, json=payload) as response:
                    if (
                        allow_book_no_hit
                        and method == "POST"
                        and path == "/Api/Book/Find"
                        and response.status_code == 404
                    ):
                        # Live observation: Book/Find uses a JSON 404 {"Message":"没找到"}
                        # for a valid query with no matches. Other 404s remain errors.
                        raw_error = bytearray()
                        async for piece in response.aiter_bytes():
                            if len(raw_error) + len(piece) > 1024:
                                break
                            raw_error.extend(piece)
                        try:
                            details = json.loads(raw_error)
                        except (ValueError, UnicodeDecodeError):
                            details = None
                        if details == {"Message": "没找到"}:
                            return {"Count": 0, "Result": []}
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
        if not isinstance(parsed, (dict, list)):
            raise CNKGraphResearchError("CNKGraph 返回的数据结构不是对象或数组")
        return parsed

    async def analyze_ci(self, content: str, tune_name: str) -> dict[str, object]:
        """从钦谱/龙谱校验中仅提取可核实的格律疑点。"""
        raw = await self._post(
            "/api/Tool/AnalyzeCi",
            {"Content": content, "TuneName": tune_name, "RhymeBook": "词林正韵"},
        )
        if not isinstance(raw, dict):
            raise CNKGraphResearchError("CNKGraph 词律分析响应结构异常")
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
        raw = await self._post(
            "/Api/Book/Find", {"key": query, "pageNo": 1},
            allow_book_no_hit=True,
        )
        if not isinstance(raw, dict):
            raise CNKGraphResearchError("CNKGraph 古籍检索响应结构异常")
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
    async def lookup_ci_tune(self, tune_name: str) -> dict[str, object]:
        """以词牌名称/别名查谱，按需取匹配词牌详情，返回简短体式候选。"""
        raw = await self._post("/api/ciTune/find", {"key": tune_name})
        if not isinstance(raw, list):
            raise CNKGraphResearchError("CNKGraph 词牌搜索结果结构异常")
        choices = [
            entry for entry in raw[:15]
            if isinstance(entry, dict) and isinstance(entry.get("Id"), int)
        ]
        summaries = [
            {
                "id": x["Id"],
                "name": str(x.get("Name") or "")[:45],
                "aliases": [str(a)[:40] for a in (x.get("Aliases") or [])[:8]],
                "writing_count": x.get("WritingCount"),
            }
            for x in choices[:7]
        ]
        if not choices:
            return {
                "status": "no_hit", "provider": "cnkgraph",
                "tune_query": tune_name, "candidates": [],
            }

        # 模糊搜索若同时命中多个词牌，先回候选，避免擅自消歧。
        exact = [
            x for x in choices
            if tune_name == x.get("Name") or tune_name in (x.get("Aliases") or [])
        ]
        if len(exact) != 1:
            return {
                "status": "candidates", "provider": "cnkgraph",
                "tune_query": tune_name, "candidates": summaries,
                "note": "查询词可能对应多个词牌，请结合当前作品选择词牌。",
            }

        item = exact[0]
        detail = await self._get("/api/ciTune/" + str(item["Id"]))
        if not isinstance(detail, dict):
            raise CNKGraphResearchError("CNKGraph 词牌详情结构异常")
        formats = detail.get("Formats") or []
        if not isinstance(formats, list):
            raise CNKGraphResearchError("CNKGraph 词牌格式列表结构异常")
        return {
            "status": "ok",
            "provider": "cnkgraph",
            "id": detail.get("Id"),
            "name": str(detail.get("Name") or "")[:60],
            "aliases": [str(a)[:45] for a in (detail.get("Aliases") or [])[:12]],
            "description": str(detail.get("Desc") or "")[:240],
            "writing_count": detail.get("WritingCount"),
            "format_count": len(formats),
            "formats": [
                {
                    "index": f.get("FormatIndex"),
                    "description": str(f.get("Desc") or "")[:190],
                    "sample_author": str(f.get("SampleAuthor") or "")[:60],
                    "sample_excerpt": str(f.get("SampleContent") or "")[:95],
                    "definition": str(f.get("Definition") or "")[:400],
                }
                for f in formats[:12] if isinstance(f, dict)
            ],
            "note": "词谱提供后世整理的不同体式与押韵范式，不能直接证明宋代原曲调。",
        }

    async def lookup_rhyme(
        self, book: str, category_id: str = "", character: str = "",
    ) -> dict[str, object]:
        """只读韵书分类或单韵部字表，不调用返回数 MB 的综合单字接口。"""
        supported = {"平水韵", "词林正韵", "中原音韵", "中华通韵"}
        if book not in supported:
            raise ValueError("不支持的韵书")
        if not category_id:
            raw = await self._get("/api/rhyme/" + quote(book, safe=""))
        else:
            raw = await self._get(
                "/api/rhyme/" + quote(book, safe="")
                + "/" + quote(category_id, safe="")
            )
        if not isinstance(raw, dict) or not isinstance(raw.get("Categories"), list):
            raise CNKGraphResearchError("CNKGraph 韵部目录结构异常")
        entries = []
        for category in raw["Categories"][:110]:
            if not isinstance(category, dict):
                continue
            groups = category.get("PingShuiCategories") or []
            candidates = []
            for member in (category.get("Chars") or []):
                if isinstance(member, dict) and isinstance(member.get("Char"), str):
                    candidates.append(member["Char"])
            for group in groups:
                if not isinstance(group, dict):
                    continue
                for member in group.get("Chars") or []:
                    if isinstance(member, dict) and isinstance(member.get("Char"), str):
                        candidates.append(member["Char"])
            entries.append({
                "group": str(category.get("Group") or "")[:50],
                "name": str(category.get("Name") or "")[:90],
                "id": str(category.get("Id") or "")[:30],
                "tone": str(category.get("Tone") or "")[:25],
                "char_count": len(candidates),
                "characters_sample": candidates[:70] if category_id else [],
                "character_present": character in candidates if character and category_id else None,
                "sub_categories": [
                    {"name": str(sub.get("Name") or "")[:50],
                     "id": str(sub.get("Id") or "")[:30],
                     "char_count": len(sub.get("Chars") or [])}
                    for sub in groups[:12] if isinstance(sub, dict)
                ] if category_id else [],
            })
        return {
            "status": "ok" if entries else "no_hit",
            "provider": "cnkgraph",
            "book": book, "category_id": category_id or None,
            "character": character or None,
            "categories": entries,
            "note": (
                "若未指定 category_id，此结果仅为韵部目录，并没有查定单字归属。"
                "若指定韵部，可根据 character_present 判断该韵部的字表是否收录该字；"
                "多音字、通韵与历史读音仍需结合语境。"
            ),
        }

    async def resolve_entities(self, text: str, epoch: str = "宋") -> dict[str, object]:
        """抽取知识图谱候选：实体 ID、类型、在原文中的位置及有限属性。"""
        raw = await self._post(
            "/api/Tool/LabelAndResolveEntity", {"Content": text, "Epoch": epoch}
        )
        if not isinstance(raw, dict):
            raise CNKGraphResearchError("CNKGraph 实体标注结构异常")
        labels = raw.get("ContentLabels")
        entities = raw.get("Entities")
        if not isinstance(labels, list) or not isinstance(entities, list):
            raise CNKGraphResearchError("CNKGraph 实体标注缺少候选列表")

        candidates = []
        for label in labels[:22]:
            if not isinstance(label, dict):
                continue
            candidates.append({
                "type": str(label.get("Type") or "")[:35],
                "id": str(label.get("Identity") or "")[:75],
                "text": str(label.get("Value") or "")[:70],
                "start": label.get("Start"),
                "length": label.get("Length"),
            })
        details = []
        identifiers = {(x["type"], x["id"]) for x in candidates}
        for entity in entities[:35]:
            if not isinstance(entity, dict):
                continue
            entity_type = str(entity.get("Type") or "")[:35]
            entity_id = str(entity.get("Id") or "")[:75]
            if (entity_type, entity_id) not in identifiers:
                continue
            properties = entity.get("Properties") or []
            details.append({
                "type": entity_type,
                "id": entity_id,
                "properties": [
                    {"name": str(prop.get("Key") or "")[:32],
                     "value": str(prop.get("Value") or "")[:140]}
                    for prop in properties[:9] if isinstance(prop, dict)
                    and prop.get("Key") not in ("小传", "著作", "職稱", "职称")
                ][:6],
            })
            if len(details) >= 10:
                break
        return {
            "status": "ok" if candidates else "no_hit",
            "provider": "cnkgraph", "epoch": epoch,
            "query_length": len(text),
            "labels": candidates, "entities": details,
            "note": (
                "实体只是外部候选，词牌也可能误识别为普通词汇；"
                "应结合上下文、人物时代与 Poeticus 自有作品数据消歧。"
                "原文 Start/Length 只适用于此次提交的 text，不得映射到另一版本。"
            ),
        }
