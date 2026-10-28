from pathlib import Path
from ebooklib import epub, ITEM_DOCUMENT
from bs4 import BeautifulSoup


def clean_text(text: str) -> str:
    """
    EPUB에서 추출한 텍스트의 불필요한 공백과 빈 줄을 정리한다.
    """
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    return "\n\n".join(lines)


def extract_title(book) -> str:
    """
    EPUB 메타데이터에서 책 제목을 추출한다.
    """
    title_metadata = book.get_metadata("DC", "title")

    if title_metadata:
        return title_metadata[0][0]

    return "Untitled Book"


def extract_chapter_title(soup: BeautifulSoup, chapter_index: int) -> str:
    """
    챕터 제목을 추출한다.
    h1, h2, title 태그 순서로 확인한다.
    """
    for tag_name in ["h1", "h2", "title"]:
        tag = soup.find(tag_name)
        if tag and tag.get_text(strip=True):
            return tag.get_text(strip=True)

    return f"Chapter {chapter_index}"


def parse_epub(epub_path: str | Path) -> dict:
    """
    EPUB 파일을 파싱하여 책 제목과 챕터 목록을 반환한다.

    반환 형식:
    {
        "title": "책 제목",
        "chapters": [
            {
                "chapter_index": 1,
                "title": "챕터 제목",
                "text": "본문 텍스트"
            }
        ]
    }
    """
    epub_path = Path(epub_path)

    if not epub_path.exists():
        raise FileNotFoundError(f"EPUB 파일을 찾을 수 없습니다: {epub_path}")

    book = epub.read_epub(str(epub_path))
    book_title = extract_title(book)

    chapters = []
    chapter_index = 1

    for item in book.get_items():
        if item.get_type() != ITEM_DOCUMENT:
            continue

        soup = BeautifulSoup(item.get_content(), "html.parser")

        # script/style 제거
        for tag in soup(["script", "style", "nav"]):
            tag.decompose()

        raw_text = soup.get_text("\n", strip=True)
        cleaned_text = clean_text(raw_text)

        # 너무 짧은 문서는 표지, 목차, 저작권 페이지일 가능성이 높으므로 제외
        if len(cleaned_text) < 300:
            continue

        chapter_title = extract_chapter_title(soup, chapter_index)

        chapters.append(
            {
                "chapter_index": chapter_index,
                "title": chapter_title,
                "text": cleaned_text,
                "char_count": len(cleaned_text),
            }
        )

        chapter_index += 1

    return {
        "title": book_title,
        "chapter_count": len(chapters),
        "chapters": chapters,
    }