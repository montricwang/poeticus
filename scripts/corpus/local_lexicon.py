"""本地《詩詞曲語辭匯釋》快照与检索；不修改生产数据库。

来源：ccddb.net 的 MediaWiki Action API。源数据仅写入仓库外 poeticus-data。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from urllib.parse import quote, urlencode

TITLE = "詩詞曲語辭匯釋"
PARATEXT_TITLES = {TITLE + "/敘言", TITLE + "/跋"}
BASE = "https://ccddb.net"
API = BASE + "/api.php"
INDEX_LINK = re.compile(
    r"^\*\[\[(詩詞曲語辭匯釋/[^\]|]+)(?:\|([^\]]+))?\]\](.*)$", re.M
)
TRANSCLUSION = re.compile(r"\{\{\s*:\s*(詩詞曲語辭匯釋/[^\}\|\n]+?)\s*(?:\|[^\}]*?)?\}\}")
WIKI_LINK = re.compile(r"\[\[(?:[^\]\|]*\|)?([^\]]+)\]\]")
SIMPLE_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
HEADING = re.compile(r"^={2,6}\s*(.*?)\s*={2,6}\s*$", re.M)
HERE = Path(__file__).resolve()
DEFAULT_DATA = HERE.parents[3] / "poeticus-data" / "lexicon" / "shi-ci-qu-yu-ci-hui-shi"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def data_root(value: str | None) -> Path:
    root = Path(value or os.environ.get("POETICUS_LEXICON_DATA_ROOT") or DEFAULT_DATA)
    return root.expanduser().resolve()


def page_path(root: Path, title: str) -> Path:
    return root / "sources" / (hashlib.sha256(title.encode("utf-8")).hexdigest() + ".json")


def load_page(root: Path, title: str) -> dict | None:
    p = page_path(root, title)
    if not p.is_file():
        return None
    rec = json.loads(p.read_text(encoding="utf-8"))
    if rec["title"] != title:
        raise ValueError(f"源页面文件不匹配：{p}")
    if hashlib.sha256(rec["wikitext"].encode("utf-8")).hexdigest() != rec["sha256"]:
        raise ValueError(f"源页面 SHA-256 校验失败：{title}")
    return rec


def save_page(root: Path, page: dict) -> bool:
    if page.get("missing") or not page.get("revisions"):
        return False
    revision = page["revisions"][0]
    content = revision["slots"]["main"]["content"]
    title = page["title"]
    record = {
        "title": title,
        "url": BASE + "/" + quote(title, safe="/"),
        "permalink": BASE + "/index.php?" + urlencode({"title": title, "oldid": revision["revid"]}),
        "page_id": page["pageid"],
        "revision_id": revision["revid"],
        "revision_timestamp": revision["timestamp"],
        "retrieved_at": utc_now(),
        "format": "MediaWiki wikitext / original page source",
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "wikitext": content,
    }
    dest = page_path(root, title)
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_suffix(".json.tmp")
    temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(dest)
    return True


def fetch_api(titles: list[str]) -> list[dict]:
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": "|".join(titles),
        "rvslots": "main",
        "rvprop": "ids|timestamp|content",
        "format": "json",
        "formatversion": "2",
    }
    # 故意使用 MediaWiki 批量只读接口；遇到 TLS 断开有限次重试，不绕过站点限流。
    command = [
        "curl", "--silent", "--show-error", "--fail", "--location",
        "--retry", "3", "--retry-all-errors", "--retry-delay", "2",
        "--connect-timeout", "12", "--max-time", "45",
        "--user-agent", "PoeticusLocalLexiconResearch/0.1 (personal noncommercial study)",
        API + "?" + urlencode(params),
    ]
    proc = subprocess.run(command, capture_output=True, check=False, timeout=65)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace")[-600:])
    data = json.loads(proc.stdout)
    if data.get("error"):
        raise RuntimeError(f"MediaWiki API: {data['error']}")
    if not isinstance(data.get("query", {}).get("pages"), list):
        raise RuntimeError("API 未返回 pages，不得视为采集完成")
    return data["query"]["pages"]


def catalog_from_index(text: str) -> list[dict]:
    results = []
    current_volume = ""
    for line in text.splitlines():
        mvol = re.match(r"^===\s*(卷[一二三四五六])\s*===", line)
        if mvol:
            current_volume = mvol.group(1)
        m = INDEX_LINK.match(line)
        if not m:
            continue
        title, label, tail = m.groups()
        label = label or title.split("/", 1)[1]
        variants = []
        for segment in re.findall(r"<span\b[^>]*>(.*?)</span>", tail):
            segment = re.sub(r"<[^>]+>", "", segment)
            variants += [s.strip() for s in re.split(r"[\u3000\s]+", segment) if s.strip()]
        results.append({
            "title": title,
            "headword": label,
            "volume": current_volume,
            "variants": list(dict.fromkeys(v for v in variants if v != label)),
        })
    titles = [e["title"] for e in results]
    if len(titles) != len(set(titles)):
        raise ValueError("目录出现重复词条链接，请先检查")
    return results


def children_from_text(text: str) -> list[str]:
    return list(dict.fromkeys(x.strip() for x in TRANSCLUSION.findall(text)))


def all_needed(root: Path, catalog: list[dict]) -> list[str]:
    """BFS 扩展所有嵌入子页面，防止只采词头页、漏掉“（一）”“（二）”。"""
    seen = set()
    queue = [TITLE] + [e["title"] for e in catalog]
    order = []
    index = 0
    while index < len(queue):
        title = queue[index]
        index += 1
        if title in seen:
            continue
        seen.add(title)
        order.append(title)
        page = load_page(root, title)
        if page:
            queue.extend(children_from_text(page["wikitext"]))
    return order


def manifest(root: Path, catalog: list[dict], needed: list[str], failures: dict) -> None:
    missing = [title for title in needed if not page_path(root, title).exists()]
    state = {
        "source": BASE + "/" + quote(TITLE),
        "source_kind": "MediaWiki source revisions; rendered HTML can differ by current templates",
        "scope": "local research only; not licensed for public redistributing by this collector",
        "captured_at": utc_now(),
        "catalog_items": len(catalog),
        "dictionary_headwords": sum(c["title"] not in PARATEXT_TITLES for c in catalog),
        "paratext_items": [c["title"] for c in catalog if c["title"] in PARATEXT_TITLES],
        "discovered_source_pages": len(needed),
        "saved_source_pages": len(needed) - len(missing),
        "uncollected_titles": missing,
        "failures": failures,
        "catalog": catalog,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def collect(root: Path, *, batch_size: int, max_batches: int, delay: float) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if not load_page(root, TITLE):
        pages = fetch_api([TITLE])
        if not any(save_page(root, p) for p in pages):
            raise RuntimeError("未能读取目录页")
    index_page = load_page(root, TITLE)
    if index_page is None:
        raise RuntimeError("目录源页面在采集后缺失")
    catalog = catalog_from_index(index_page["wikitext"])
    if len(catalog) < 100:
        raise RuntimeError(f"目录仅解析出 {len(catalog)} 个词条，停止以避免错误快照")
    failures = {}
    completed = 0
    for _ in range(max_batches):
        needed = all_needed(root, catalog)
        pending = [x for x in needed if not page_path(root, x).exists() and x not in failures]
        if not pending:
            break
        batch = pending[:batch_size]
        try:
            pages = fetch_api(batch)
            found = set()
            for p in pages:
                found.add(p["title"])
                if save_page(root, p):
                    completed += 1
                else:
                    failures[p["title"]] = "API 返回 missing/no revisions"
            for x in batch:
                if x not in found:
                    failures[x] = "API 未列出该标题"
        except Exception as exc:
            failures[" | ".join(batch)] = str(exc)[:350]
            print(f"请求失败：{str(exc)[:300]}", file=sys.stderr)
            break
        if delay:
            time.sleep(delay)
    needed = all_needed(root, catalog)
    manifest(root, catalog, needed, failures)
    print(json.dumps({
        "catalog": len(catalog),
        "source_pages_discovered": len(needed),
        "source_pages_saved": sum(page_path(root, x).exists() for x in needed),
        "saved_in_this_run": completed,
        "remaining": sum(not page_path(root, x).exists() for x in needed),
        "errors": failures,
        "data_dir": str(root),
    }, ensure_ascii=False, indent=2))


def plain_wikitext(raw: str) -> str:
    raw = re.sub(r"<noinclude>.*?</noinclude>", "", raw, flags=re.S | re.I)
    raw = re.sub(r"<(ref|gallery)\b[^>]*>.*?</\1>", "", raw, flags=re.S | re.I)
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
    raw = TRANSCLUSION.sub("", raw)
    raw = SIMPLE_TEMPLATE.sub("", raw)
    raw = WIKI_LINK.sub(r"\1", raw)
    raw = HEADING.sub(r"\1\n", raw)
    raw = raw.replace("'''", "").replace("''", "")
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t]{2,}", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def render_entry(root: Path, title: str, seen: set[str] | None = None) -> tuple[str, bool]:
    """按原文位置展开子条目；不能把所有子页追加在父页页码之后。"""
    seen = set() if seen is None else seen
    if title in seen:
        return "", False
    seen.add(title)
    rec = load_page(root, title)
    if not rec:
        return "", False
    complete = True

    def expand(match: re.Match[str]) -> str:
        nonlocal complete
        child = match.group(1).strip()
        child_text, ok = render_entry(root, child, seen)
        if not ok:
            complete = False
        return "\n\n" + child_text + "\n\n"

    expanded = TRANSCLUSION.sub(expand, rec["wikitext"])
    return plain_wikitext(expanded), complete


def rebuild(root: Path) -> None:
    main = load_page(root, TITLE)
    if not main:
        raise RuntimeError("先执行 fetch 获取目录")
    catalog = [item for item in catalog_from_index(main["wikitext"])
               if item["title"] not in PARATEXT_TITLES]
    dest = root / "lexicon.sqlite"
    temp = dest.with_suffix(".sqlite.tmp")
    if temp.exists():
        temp.unlink()
    db = sqlite3.connect(temp)
    try:
        db.executescript("""
            CREATE TABLE entry(
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL UNIQUE,
                headword TEXT NOT NULL,
                volume TEXT,
                variants TEXT NOT NULL,
                full_text TEXT NOT NULL,
                complete INTEGER NOT NULL CHECK(complete IN(0, 1)),
                source_url TEXT NOT NULL,
                revision_id INTEGER,
                text_sha256 TEXT
            );
            CREATE VIRTUAL TABLE entry_fts USING fts5(
                headword, variants, full_text,
                content='entry', content_rowid='id', tokenize='trigram'
            );
            CREATE INDEX idx_entry_headword ON entry(headword);
        """)
        complete_count = 0
        for item in catalog:
            text, complete = render_entry(root, item["title"])
            rec = load_page(root, item["title"])
            db.execute(
                "INSERT INTO entry(title,headword,volume,variants,full_text,complete,source_url,revision_id,text_sha256)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (item["title"], item["headword"], item["volume"],
                 json.dumps(item["variants"], ensure_ascii=False), text, int(complete),
                 rec["permalink"] if rec else BASE + "/" + quote(item["title"], safe="/"),
                 rec["revision_id"] if rec else None,
                 hashlib.sha256(text.encode("utf-8")).hexdigest()),
            )
            complete_count += complete
        db.execute("INSERT INTO entry_fts(entry_fts) VALUES('rebuild')")
        db.commit()
    finally:
        db.close()
    temp.replace(dest)
    print(f"索引：{len(catalog)} 词条、{complete_count} 完整、{len(catalog)-complete_count} 待补全，文件 {dest}")


def lookup(root: Path, term: str, limit: int, max_chars: int) -> None:
    dbfile = root / "lexicon.sqlite"
    if not dbfile.exists():
        raise RuntimeError("请先执行 build 生成本地索引")
    db = sqlite3.connect(f"file:{dbfile}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT * FROM entry WHERE headword=? OR EXISTS("
            "SELECT 1 FROM json_each(entry.variants) WHERE value=?) "
            "LIMIT ?", (term, term, limit),
        ).fetchall()
        if not rows:
            # FTS trigram 对三字以上有稳定子串检索；短词直接 LIKE。
            if len(term) >= 3:
                try:
                    rows = db.execute(
                        "SELECT entry.* FROM entry_fts JOIN entry ON entry_fts.rowid=entry.id "
                        "WHERE entry_fts MATCH ? LIMIT ?", ('"' + term.replace('"', '""') + '"', limit)
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            if not rows:
                rows = db.execute("SELECT * FROM entry WHERE full_text LIKE ? LIMIT ?",
                                  ("%" + term + "%", limit)).fetchall()
        for row in rows:
            text = row["full_text"]
            pos = text.find(term)
            if pos >= 0 and pos > max_chars // 2:
                # 题头不存在的全文命中，把证据附近作为摘要；不删数据库中的其余义项。
                start = max(0, pos - max_chars // 4)
            else:
                start = 0
            snippet = text[start:start + max_chars]
            print(f"\n{row['headword']}（{row['volume']}，{ '完整' if row['complete'] else '不完整' }）")
            print(f"异形：{', '.join(json.loads(row['variants'])) or '—'}")
            print(snippet + ("……" if start + max_chars < len(text) else ""))
            print(f"来源：{row['source_url']}")
        if not rows:
            print("未找到匹配词条。")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", help="私有目录（默认仓库相邻 poeticus-data）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    pfetch = sub.add_parser("fetch", help="只读批量抓取并可断点续采")
    pfetch.add_argument("--batch-size", type=int, default=15)
    pfetch.add_argument("--max-batches", type=int, default=100)
    pfetch.add_argument("--delay", type=float, default=0.7)
    sub.add_parser("build", help="从已保存的修订源文本离线重建 SQLite")
    pquery = sub.add_parser("lookup", help="离线查词")
    pquery.add_argument("term")
    pquery.add_argument("--limit", type=int, default=4)
    pquery.add_argument("--max-chars", type=int, default=1200)
    args = parser.parse_args()
    root = data_root(args.data_root)
    if args.cmd == "fetch":
        if not 1 <= args.batch_size <= 25:
            parser.error("--batch-size 必须在 1–25 之间")
        if not 0.2 <= args.delay <= 60:
            parser.error("--delay 不得低于 0.2 秒")
        collect(root, batch_size=args.batch_size, max_batches=args.max_batches,
                delay=args.delay)
    elif args.cmd == "build":
        rebuild(root)
    else:
        lookup(root, args.term, args.limit, args.max_chars)


if __name__ == "__main__":
    main()
