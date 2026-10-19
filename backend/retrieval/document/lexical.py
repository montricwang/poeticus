"""文献检索的轻量 BM25；查询和文献使用同一套 n-gram tokenizer。"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

LEXICAL_RE = re.compile(r"[\u3400-\u9fff]+|[a-z0-9]+")
K1 = 1.2
B = 0.75


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    for match in LEXICAL_RE.finditer(normalized):
        value = match.group()
        if value.isascii():
            tokens.append(value)
        else:
            tokens.extend(value[i:i + size] for size in (2, 3) for i in range(len(value) - size + 1))
    return tokens


class SectionBM25:
    """检索以 doc/file/section_id 定位的完整文献 Section。"""

    def __init__(self, sections: list[dict[str, str]]) -> None:
        if not sections:
            raise ValueError("空文献库无法初始化 BM25")
        self.keys = ["|".join((s["doc"], s["file"], str(s["section_id"]))) for s in sections]
        self.counts = [Counter(tokenize(f"{s['title']} {s['text']}")) for s in sections]
        self.lengths = [sum(counts.values()) for counts in self.counts]
        self.average_length = sum(self.lengths) / len(self.lengths)
        frequencies: Counter[str] = Counter()
        for counts in self.counts:
            frequencies.update(counts.keys())
        n = len(sections)
        self.idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5))
                    for term, df in frequencies.items()}

    def search(self, question: str, k: int = 5) -> list[tuple[str, float]]:
        query = set(tokenize(question))
        ranked: list[tuple[str, float]] = []
        for key, counts, length in zip(self.keys, self.counts, self.lengths):
            score = 0.0
            for term in query:
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + K1 * (1 - B + B * length / self.average_length)
                score += self.idf[term] * frequency * (K1 + 1) / denominator
            if score > 0:
                ranked.append((key, score))
        return sorted(ranked, key=lambda item: (-item[1], item[0]))[:k]
