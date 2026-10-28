"""EPUB CFI 문자열 <-> 정렬용 정수 배열 변환.

Supabase book_cfi_index.cfi_path(INTEGER[])와 동일한 규칙으로 변환해야 global_index
매칭이 정확하다. spokeeper_cfi_db/cfi_utils.py와 동일 로직 (mismatch 0건 검증됨).
"""
import re


def _normalize_content_path(inner: str) -> str:
    """Normalize equivalent content paths emitted by the two CFI libraries.

    ``epub-cfi-resolver`` (used while indexing) prefixes the content document
    with ``/2/4`` while epub.js relocation CFIs start at ``/4``.  The leading
    ``/2`` represents the document root and does not identify a different
    reading position.  Keeping it made every epub.js position compare *after*
    all indexed paragraphs in the same spine item, mapping an early page to the
    end of the chapter/book.
    """

    package_path, separator, content_path = inner.partition("!")
    if separator and re.match(r"^/2(?=/4(?:/|$))", content_path):
        content_path = content_path[2:]
    return f"{package_path}{separator}{content_path}" if separator else package_path


def cfi_to_path(cfi: str) -> list[int]:
    """EPUB CFI 문자열을 정렬 비교용 정수 배열로 변환.

    예: "epubcfi(/6/10!/2/4/2[pgepubid00003]/4/1)" -> [6,0,10,0,4,0,2,0,4,0,1,0]
    """
    inner = re.sub(r'^epubcfi\((.*)\)$', r'\1', cfi.strip())
    inner = re.sub(r'\[[^\]]*\]', '', inner)  # ID 어설션 제거
    inner = _normalize_content_path(inner)
    inner = inner.replace('!', '/')            # indirection -> 경로 연속

    steps: list[int] = []
    for token in inner.split('/'):
        if not token:
            continue
        if ':' in token:
            step, offset = token.split(':')
            steps.append(int(step))
            steps.append(int(offset))
        else:
            steps.append(int(token))
            steps.append(0)
    return steps
