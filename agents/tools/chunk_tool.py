import os


DEFAULT_CHUNK_SIZE = 600
DEFAULT_CHUNK_OVERLAP = 100


def _configured_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer: {raw}") from error


def make_chunks(
    chapters: list[dict],
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[dict]:
    """
    EPUB에서 파싱된 chapter 목록을 chunk 단위로 분할한다.

    각 chunk는 SpoKeeper의 읽기 위치 기준이 되는 offset을 가진다.
    overlap을 두어 chunk 경계에서 문맥이 끊기는 문제를 줄인다.
    기본값은 페이지별 관계도 갱신이 너무 성기지 않도록 600/100으로 두고,
    SPO_CHUNK_SIZE/SPO_CHUNK_OVERLAP 환경변수로 책 특성에 맞게 조정할 수 있다.
    """
    chunk_size = chunk_size if chunk_size is not None else _configured_int(
        "SPO_CHUNK_SIZE", DEFAULT_CHUNK_SIZE
    )
    overlap = overlap if overlap is not None else _configured_int(
        "SPO_CHUNK_OVERLAP", DEFAULT_CHUNK_OVERLAP
    )
    if chunk_size <= 0:
        raise ValueError("chunk_size는 0보다 커야 합니다.")

    if overlap < 0:
        raise ValueError("overlap은 0 이상이어야 합니다.")

    if overlap >= chunk_size:
        raise ValueError("overlap은 chunk_size보다 작아야 합니다.")

    chunks = []
    offset = 0
    chunk_id = 0

    for chapter in chapters:
        text = chapter["text"]
        chapter_index = chapter["chapter_index"]
        chapter_title = chapter.get("title", f"Chapter {chapter_index}")

        start = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "chapter_index": chapter_index,
                        "chapter_title": chapter_title,
                        "offset": offset,
                        "start_char": start,
                        "end_char": end,
                        "text": chunk_text,
                        "char_count": len(chunk_text),
                        "preview": make_preview(chunk_text),
                    }
                )

                chunk_id += 1
                offset += 1

            if end == len(text):
                break

            start = end - overlap

    return chunks


def make_preview(text: str, max_length: int = 120) -> str:
    """
    UI에서 chunk를 빠르게 구분하기 위한 미리보기 문자열을 만든다.
    """
    text = " ".join(text.split())

    if len(text) <= max_length:
        return text

    return text[:max_length] + "..."
