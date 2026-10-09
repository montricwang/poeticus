"""BM25 与 SQLite FTS5 共用的字符 n-gram 和查询表达式。

离线索引构建与在线 Serving 必须采用相同的分词边界。
至于无有效词项的 Query 应当报错还是返回空结果，
由各调用方依据自身语义决定。"""
from __future__ import annotations

from collections.abc import Iterable, Iterator


def iter_character_runs(text: str) -> Iterator[str]:
    """依次产生连续的 Unicode 字母/数字片段；标点作为分隔边界。"""
    current: list[str] = []
    for char in text:
        if char.isalnum():
            current.append(char)
            continue
        if current:
            yield "".join(current)
            current = []
    if current:
        yield "".join(current)


def character_ngrams(
    text: str,
    *,
    min_n: int = 2,
    max_n: int = 3,
) -> list[str]:
    """按相同的 Unicode 边界规则生成语料和 Query 词项。"""
    if min_n <= 0 or max_n < min_n:
        raise ValueError("n-gram 范围必须满足 0 < min_n <= max_n")

    grams: list[str] = []
    for run in iter_character_runs(text):
        for n in range(min_n, max_n + 1):
            if len(run) < n:
                continue
            grams.extend(run[index:index + n] for index in range(len(run) - n + 1))
    return grams


def unique_in_order(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def match_query_or_none(
    query: str,
    *,
    min_n: int = 2,
    max_n: int = 3,
) -> str | None:
    """构造 FTS5 MATCH 表达式；空词项的处理由调用方决定。"""
    grams = unique_in_order(character_ngrams(query, min_n=min_n, max_n=max_n))
    if not grams:
        return None
    escaped = [gram.replace('"', '""') for gram in grams]
    return " OR ".join(f'"{gram}"' for gram in escaped)
