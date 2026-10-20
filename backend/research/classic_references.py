"""Read-only official sources: MoeDict dictionary and Chinese Wikisource Action API."""
from __future__ import annotations

import json
import os
from html.parser import HTMLParser
from urllib.parse import quote

import httpx


class ReferenceSourceError(RuntimeError):
    """External provider error, distinct from a valid zero-match response."""


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def _strip_markup(text: str) -> str:
    parser = _PlainText()
    parser.feed(text)
    return parser.text()


class ClassicReferencesClient:
    MAX_BYTES = 256 * 1024
    WIKISOURCE_API = "https://zh.wikisource.org/w/api.php"
    MOEDICT_ORIGIN = "https://www.moedict.tw"

    def __init__(self) -> None:
        self.user_agent = os.getenv(
            "POETICUS_WIKIMEDIA_USER_AGENT",
            "PoeticusResearch/0.1 (https://poeticus.app; research)",
        )
        self.timeout = httpx.Timeout(15.0)

    async def _get(self, url: str, params: dict[str, str | int] | None = None) -> dict[str, object] | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                async with client.stream(
                    "GET", url, params=params,
                    headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                ) as response:
                    if response.status_code == 404:
                        return None
                    response.raise_for_status()
                    if "json" not in response.headers.get("content-type", "").lower():
                        raise ReferenceSourceError("来源接口返回非 JSON 数据")
                    size = response.headers.get("content-length")
                    if size and int(size) > self.MAX_BYTES:
                        raise ReferenceSourceError("来源接口响应过大")
                    data = bytearray()
                    async for part in response.aiter_bytes():
                        if len(data) + len(part) > self.MAX_BYTES:
                            raise ReferenceSourceError("来源接口响应过大")
                        data.extend(part)
        except httpx.HTTPStatusError as exc:
            raise ReferenceSourceError(
                f"来源接口 HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise ReferenceSourceError("来源接口连接失败或超时") from exc
        except (UnicodeError, ValueError) as exc:
            raise ReferenceSourceError("来源接口响应头异常") from exc
        try:
            decoded = json.loads(data)
        except (ValueError, UnicodeError) as exc:
            raise ReferenceSourceError("来源接口 JSON 无效") from exc
        if not isinstance(decoded, dict):
            raise ReferenceSourceError("来源接口 JSON 结构错误")
        if "error" in decoded:
            details = decoded["error"]
            code = details.get("code", "unknown") if isinstance(details, dict) else "unknown"
            raise ReferenceSourceError("MediaWiki API 错误：" + str(code)[:80])
        return decoded

    async def lookup_moedict(self, term: str) -> dict[str, object]:
        if not isinstance(term, str) or not 1 <= len(term.strip()) <= 16:
            raise ValueError("萌典字词必须为 1–16 字")
        word = term.strip()
        raw = await self._get(
            self.MOEDICT_ORIGIN + "/a/" + quote(word, safe="") + ".json"
        )
        if raw is None:
            return {
                "status": "no_hit", "provider": "moedict", "query": word, "entries": [],
            }
        pronunciations = raw.get("h")
        if not isinstance(pronunciations, list):
            raise ReferenceSourceError("萌典词条缺少读音/释义列表")
        entries: list[dict[str, object]] = []
        for pronunciation in pronunciations[:3]:
            if not isinstance(pronunciation, dict):
                continue
            meanings = pronunciation.get("d")
            if not isinstance(meanings, list):
                continue
            definitions: list[dict[str, object]] = []
            for m in meanings[:6]:
                if not isinstance(m, dict):
                    continue
                examples = m.get("q") or []
                definitions.append({
                    "definition_original": str(m.get("f") or "")[:340],
                    "examples_original": [
                        str(example)[:350] for example in examples[:2]
                        if isinstance(example, str)
                    ] if isinstance(examples, list) else [],
                })
            entries.append({
                "bopomofo": str(pronunciation.get("b") or "")[:100],
                "pinyin": str(pronunciation.get("p") or "")[:130],
                "definitions": definitions,
            })
        return {
            "status": "ok" if entries else "no_hit",
            "provider": "moedict",
            "query": word,
            "headword": str(raw.get("t") or word)[:60],
            "url": self.MOEDICT_ORIGIN + "/a/" + quote(word, safe=""),
            "entries": entries,
            "license_note": (
                "词条来自台湾教育部《重编国语辞典修订本》，CC BY-ND 3.0 TW；"
                "所列释义和例句保留原文字形/标记并注明萌典来源。"
                "这是字典候选义项，不自动等于当前诗句的正确释义。"
            ),
        }

    async def search_wikisource(self, query: str) -> dict[str, object]:
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 100:
            raise ValueError("维基文库查询必须为 1–100 字")
        text = query.strip()
        data = await self._get(self.WIKISOURCE_API, {
            "action": "query", "list": "search", "srsearch": text,
            "srnamespace": 0, "srlimit": 5, "srprop": "snippet",
            "format": "json", "formatversion": 2,
        })
        query_info = data.get("query") if data is not None else None
        if not isinstance(query_info, dict):
            raise ReferenceSourceError("维基文库搜索没有有效查询响应")
        rows = query_info.get("search")
        if not isinstance(rows, list):
            raise ReferenceSourceError("维基文库搜索缺少 search 数组")
        results: list[dict[str, object]] = []
        for item in rows[:5]:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            if not isinstance(title, str) or not title:
                continue
            page_id = item.get("pageid")
            if not isinstance(page_id, int):
                continue
            results.append({
                "title": title[:170],
                "pageid": page_id,
                "url": "https://zh.wikisource.org/wiki/" + quote(title.replace(" ", "_"), safe=""),
                "snippet": _strip_markup(str(item.get("snippet") or ""))[:370],
            })
        return {
            "status": "ok" if results else "no_hit",
            "provider": "wikisource",
            "query": text,
            "results": results,
            "note": "搜索结果仅定位文库候选页面；引用时需检查版本与实际正文。",
        }

    async def read_wikisource(self, pageid: int) -> dict[str, object]:
        if not isinstance(pageid, int) or pageid < 1:
            raise ValueError("维基文库 pageid 无效")
        data = await self._get(self.WIKISOURCE_API, {
            "action": "query", "prop": "revisions",
            "pageids": pageid, "rvprop": "ids|timestamp|content", "rvslots": "main",
            "format": "json", "formatversion": 2,
        })
        query_info = data.get("query") if data is not None else None
        if not isinstance(query_info, dict):
            raise ReferenceSourceError("维基文库正文查询失败")
        pages = query_info.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ReferenceSourceError("维基文库正文查询缺少页面")
        page = pages[0]
        if not isinstance(page, dict) or page.get("missing") is True:
            return {
                "status": "no_hit", "provider": "wikisource", "pageid": pageid,
            }
        revisions = page.get("revisions") or []
        if not isinstance(revisions, list) or not revisions:
            raise ReferenceSourceError("维基文库缺少修订记录")
        rev = revisions[0]
        content = (rev.get("slots") or {}).get("main", {}).get("content")
        if not isinstance(content, str):
            raise ReferenceSourceError("维基文库正文结构异常")
        title = str(page.get("title") or "")[:180]
        revision_id = rev.get("revid")
        if not isinstance(revision_id, int):
            raise ReferenceSourceError("维基文库缺少修订号")
        return {
            "status": "ok", "provider": "wikisource",
            "pageid": pageid, "title": title, "revision_id": revision_id,
            "timestamp": str(rev.get("timestamp") or "")[:40],
            "url": f"https://zh.wikisource.org/w/index.php?oldid={revision_id}",
            "wikitext_excerpt": content[:3500],
            "truncated": len(content) > 3500,
            "note": (
                "返回维基文库 wikitext 原文节选（含模板语法），不是现代校勘的权威底本；"
                "核对引文应保留本次 revision URL 并关注页面版本、影印与源文献。"
            ),
        }
