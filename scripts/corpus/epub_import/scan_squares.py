from pathlib import Path
from collections import Counter

from bs4 import BeautifulSoup
from ebooklib import epub, ITEM_DOCUMENT


book = epub.read_epub(str(Path("data/raw/历代名家词集精华录.epub")))

counts = Counter()

for item in book.get_items_of_type(ITEM_DOCUMENT):
    soup = BeautifulSoup(item.get_content(), "lxml")
    text = soup.get_text()

    for char in ["□", "�"]:
        count = text.count(char)

        if count:
            counts[char] += count
            print(f"{item.get_name()}: {repr(char)} × {count}")

print("\n总计：", dict(counts))

item = book.get_item_with_href("text00231.html")
soup = BeautifulSoup(item.get_content(), "lxml")

hits = []

for tag in soup.find_all(["h1", "h2", "p"]):
    text = tag.get_text(" ", strip=True)
    if "□" in text:
        hits.append((tag.name, text))

print(f"含方框的节点：{len(hits)}")

for tag_name, text in hits[:12]:
    print(f"[{tag_name}] {text[:160]}")
