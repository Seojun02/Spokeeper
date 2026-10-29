"""챕터 JSON(eval/prep_scarlet.py 산출물) → EPUB 변환. 앱에 업로드/등록할 수 있는 형태로 만든다.

사용: python eval/chapters_to_epub.py [챕터 JSON] [출력 EPUB]
기본값: eval/data/scarlet_chapters.json → backend/data/주홍색의_연구.epub
번역본 저작권 때문에 입력 JSON과 출력 EPUB은 .gitignore 대상이다.
"""
import json
import sys
from html import escape
from pathlib import Path

from ebooklib import epub

ROOT = Path(__file__).resolve().parents[1]
src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "eval" / "data" / "scarlet_chapters.json"
dst = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "backend" / "data" / "주홍색의_연구.epub"

data = json.loads(src.read_text(encoding="utf-8"))
book = epub.EpubBook()
book.set_identifier("spokeeper-study-in-scarlet")
book.set_title(data.get("title", "주홍색의 연구"))
book.set_language("ko")
book.add_author("아서 코난 도일")

items = []
for ch in data["chapters"]:
    item = epub.EpubHtml(title=ch["title"], file_name=f"ch{ch['chapter_index']:02d}.xhtml", lang="ko")
    paragraphs = "".join(f"<p>{escape(p)}</p>" for p in ch["text"].split("\n\n") if p.strip())
    item.content = f"<h2>{escape(ch['title'])}</h2>{paragraphs}"
    book.add_item(item)
    items.append(item)

book.toc = tuple(items)
book.add_item(epub.EpubNcx())
book.add_item(epub.EpubNav())
book.spine = ["nav", *items]
dst.parent.mkdir(parents=True, exist_ok=True)
epub.write_epub(str(dst), book)
print(f"{dst} ({len(items)}챕터)")
