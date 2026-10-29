"""Supabase(Postgres)의 book_cfi_index 조회 계층.

CFI 통합의 핵심 아이디어: 지금까지 시스템 곳곳에 흩어져 있던 "offset"의 정의를
하나로 통일한다 — 여기서 offset 이란 `book_cfi_index`를 cfi_path 기준으로 정렬했을 때
해당 문단의 0부터 시작하는 순번(global_index)이다. BuildAgent의 chunk 순번, 스포일러
경계선, 프론트 페이지네이션이 전부 이 정수를 그대로 공유한다.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .cfi_utils import cfi_to_path
from .config import SUPABASE_DB_URL

try:  # Supabase 모드에서만 필요. 로컬 모드(SUPABASE_DB_URL 없음)는 설치 없이도 동작한다.
    import psycopg2
    import psycopg2.extras
except ImportError:  # pragma: no cover
    psycopg2 = None

# SUPABASE_DB_URL 이 없으면 DB 대신 backend/data/local_db/ 의 JSON 파일로 같은 함수들을 제공한다.
LOCAL_MODE = not SUPABASE_DB_URL
LOCAL_DB_DIR = Path(__file__).resolve().parent.parent / "data" / "local_db"
LOCAL_BOOKS_PATH = LOCAL_DB_DIR / "books.json"
CFI_SCRIPT = Path(__file__).resolve().parent.parent / "cfi_tools" / "build_cfi_index.js"


@dataclass(frozen=True)
class CfiParagraph:
    global_index: int
    chapter_index: int
    chapter_title: str
    paragraph_index: int
    cfi_raw: str
    cfi_path: list[int]
    text_preview: str


def _connect():
    if not SUPABASE_DB_URL:
        raise RuntimeError("SUPABASE_DB_URL 환경변수가 설정되어 있지 않습니다.")
    return psycopg2.connect(SUPABASE_DB_URL, connect_timeout=10)


# ── 로컬 모드 (DB 없이 JSON 파일 사용) ───────────────────────────────────

def _local_books() -> dict:
    if LOCAL_BOOKS_PATH.exists():
        return json.loads(LOCAL_BOOKS_PATH.read_text(encoding="utf-8"))
    return {}


def _save_local_books(books: dict) -> None:
    LOCAL_DB_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_BOOKS_PATH.write_text(json.dumps(books, ensure_ascii=False, indent=1), encoding="utf-8")


def _local_cfi_path(book_id: str) -> Path:
    return LOCAL_DB_DIR / "cfi" / f"{book_id}.json"


def _build_rows_from_epub(epub_path: Path) -> list[dict]:
    """업로드 파이프라인과 같은 Node 스크립트로 EPUB에서 CFI 문단 행을 만든다."""
    with tempfile.TemporaryDirectory() as tmp:
        unpacked = Path(tmp) / "unpacked"
        unpacked.mkdir()
        with zipfile.ZipFile(epub_path) as zf:
            zf.extractall(unpacked)
        out = Path(tmp) / "cfi_index.json"
        result = subprocess.run(
            ["node", str(CFI_SCRIPT), str(unpacked), str(out)],
            cwd=CFI_SCRIPT.parent, capture_output=True,
        encoding="utf-8",
        errors="replace", text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"CFI 생성 스크립트 실패 (exit={result.returncode}):\n{result.stderr}")
        return json.loads(out.read_text(encoding="utf-8"))


def _local_paragraphs(book_id: str) -> tuple["CfiParagraph", ...]:
    if not book_id:
        return ()
    path = _local_cfi_path(book_id)
    if not path.exists():
        # 등록된 EPUB 은 처음 읽을 때 한 번 인덱싱해서 저장한다.
        from .book_repository import get_local_book_metadata, resolve_epub_path

        if get_local_book_metadata(book_id) is None:
            return ()
        rows = _build_rows_from_epub(resolve_epub_path(book_id))
        if not rows:  # 문단을 인식하지 못한 EPUB 은 빈 책으로 취급
            return ()
        insert_paragraphs(book_id, rows)
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows.sort(key=lambda r: r["cfi_path"])
    return tuple(
        CfiParagraph(
            global_index=i,
            chapter_index=r["chapter_index"],
            chapter_title=r["chapter_title"] or f"Chapter {r['chapter_index']}",
            paragraph_index=r["paragraph_index"],
            cfi_raw=r["cfi_raw"],
            cfi_path=cfi_to_path(r["cfi_raw"]),
            text_preview=r["text_preview"],
        )
        for i, r in enumerate(rows)
    )


# maxsize=8이었을 때는 등록된 책이 8권을 넘으면 /api/books가 전체 책을 순회할 때마다
# LRU 캐시가 계속 밀려나서(스래싱) 캐시가 사실상 안 먹혀 매 요청마다 Supabase에 새
# 연결을 맺느라 몇 초씩 걸렸다 — 책 수가 작고 자연히 유계라 무제한으로 둔다.
@lru_cache(maxsize=None)
def get_paragraphs(book_id: str) -> tuple[CfiParagraph, ...]:
    """book_id의 전체 문단을 cfi_path 순서(=global_index)로 반환. 결과는 캐시됨."""
    if LOCAL_MODE:
        return _local_paragraphs(book_id)
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT chapter_index, chapter_title, paragraph_index, cfi_raw, cfi_path, text_preview
                FROM book_cfi_index
                WHERE book_id = %s
                ORDER BY cfi_path
                """,
                (book_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return tuple(
        CfiParagraph(
            global_index=i,
            chapter_index=row["chapter_index"],
            chapter_title=row["chapter_title"] or f"Chapter {row['chapter_index']}",
            paragraph_index=row["paragraph_index"],
            cfi_raw=row["cfi_raw"],
            # 기존 DB cfi_path는 인덱서의 ``!/2/4/...`` 형식을 그대로 담고 있다.
            # epub.js relocated CFI(``!/4/...``)와 동일한 규칙으로 비교하기 위해
            # 원본 CFI에서 정규화 경로를 다시 만든다. DB 마이그레이션 없이 기존
            # 인덱스도 즉시 안전하게 읽을 수 있다.
            cfi_path=cfi_to_path(row["cfi_raw"]),
            text_preview=row["text_preview"],
        )
        for i, row in enumerate(rows)
    )


def cfi_for_global_index(book_id: str, global_index: int) -> str | None:
    """global_index -> 원본 CFI 문자열 (역방향 조회, 새로고침 시 위치 복원용)."""
    paragraphs = get_paragraphs(book_id)
    if not paragraphs:
        return None
    clamped = max(0, min(global_index, len(paragraphs) - 1))
    return paragraphs[clamped].cfi_raw


def find_global_index_by_cfi(book_id: str, raw_cfi: str) -> int:
    """epub.js가 준 원본 CFI 문자열을 이 책의 global_index로 변환한다.

    정확히 일치하는 문단이 없으면(문단 사이의 임의 위치를 가리키는 CFI일 수 있음)
    그 위치보다 앞선 문단 중 가장 마지막 것의 global_index를 반환한다(cfi_path 배열의
    사전식 비교가 곧 문서 순서와 같다는 성질 이용, book_cfi_index README에서 검증됨).
    """
    # cfi_to_path canonicalizes both the indexer's !/2/4/... form and
    # epub.js's !/4/... form, so no one-sided path insertion is necessary.
    target = cfi_to_path(raw_cfi)
    paragraphs = get_paragraphs(book_id)
    if not paragraphs:
        return 0

    lo, hi = 0, len(paragraphs) - 1
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if paragraphs[mid].cfi_path <= target:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return paragraphs[best].global_index


def total_paragraphs(book_id: str) -> int:
    return len(get_paragraphs(book_id))


def paragraphs_up_to(book_id: str, boundary: int) -> tuple[CfiParagraph, ...]:
    """global_index <= boundary 인 문단만 반환 (스포일러 경계선 게이팅)."""
    return tuple(p for p in get_paragraphs(book_id) if p.global_index <= boundary)


def clear_cache() -> None:
    get_paragraphs.cache_clear()


# ── 쓰기 경로 (업로드 파이프라인용) ──────────────────────────────────────

def find_book_by_hash(content_hash: str) -> str | None:
    """같은 content_hash의 책이 이미 있으면 book_id를, 없으면 None을 반환."""
    if LOCAL_MODE:
        return next((bid for bid, b in _local_books().items() if b.get("content_hash") == content_hash), None)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT book_id FROM books WHERE content_hash = %s", (content_hash,))
            row = cur.fetchone()
            return str(row[0]) if row else None
    finally:
        conn.close()


def set_storage_path(book_id: str, storage_path: str) -> None:
    if LOCAL_MODE:
        books = _local_books()
        if book_id in books:
            books[book_id]["storage_path"] = storage_path
            _save_local_books(books)
        return
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE books SET storage_path=%s WHERE book_id=%s", (storage_path, book_id))
        conn.commit()
    finally:
        conn.close()


def get_book_storage_path(book_id: str) -> str | None:
    """books.storage_path를 반환하고, 해당 book_id가 없으면 None을 반환한다."""
    if LOCAL_MODE:
        return (_local_books().get(book_id) or {}).get("storage_path") or None
    conn = _connect()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT storage_path FROM books WHERE book_id = %s", (book_id,))
            except psycopg2.errors.InvalidTextRepresentation:
                conn.rollback()
                return None
            row = cur.fetchone()
            return str(row[0]).strip() if row and row[0] else None
    finally:
        conn.close()


def list_books() -> list[dict]:
    """status='ready'인 책 목록을 (book_id, title, storage_path)로 반환."""
    if LOCAL_MODE:
        return [
            {"book_id": bid, "title": b.get("title", ""), "storage_path": b.get("storage_path", "")}
            for bid, b in _local_books().items()
            if b.get("status") == "ready"
        ]
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT book_id, title, storage_path FROM books WHERE status='ready'")
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def has_paragraphs(book_id: str) -> bool:
    if LOCAL_MODE:
        return _local_cfi_path(book_id).exists()
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM book_cfi_index WHERE book_id = %s", (book_id,))
            return cur.fetchone()[0] > 0
    finally:
        conn.close()


def insert_book(content_hash: str, title: str, storage_path: str) -> str:
    """books row 생성(이미 있으면 기존 row 재사용). book_id 반환."""
    if LOCAL_MODE:
        books = _local_books()
        existing = next((bid for bid, b in books.items() if b.get("content_hash") == content_hash), None)
        book_id = existing or str(uuid.uuid4())
        status = books.get(book_id, {}).get("status", "processing")
        books[book_id] = {"content_hash": content_hash, "title": title, "storage_path": storage_path, "status": status}
        _save_local_books(books)
        return book_id
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO books (content_hash, title, storage_path, status)
                VALUES (%s, %s, %s, 'processing')
                ON CONFLICT (content_hash) DO UPDATE SET title = EXCLUDED.title
                RETURNING book_id
                """,
                (content_hash, title, storage_path),
            )
            book_id = str(cur.fetchone()[0])
        conn.commit()
        return book_id
    finally:
        conn.close()


def insert_paragraphs(book_id: str, rows: list[dict]) -> int:
    """CFI 생성 스크립트 결과(rows)를 book_cfi_index에 적재. 적재된 행 수 반환."""
    if not rows:
        return 0
    if LOCAL_MODE:
        path = _local_cfi_path(book_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        books = _local_books()
        if book_id in books:
            books[book_id]["status"] = "ready"
            _save_local_books(books)
        get_paragraphs.cache_clear()
        return len(rows)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO book_cfi_index
                    (book_id, chapter_index, chapter_title, paragraph_index, cfi_raw, cfi_path, text_preview)
                VALUES %s
                """,
                [
                    (
                        book_id,
                        r["chapter_index"],
                        r["chapter_title"],
                        r["paragraph_index"],
                        r["cfi_raw"],
                        r["cfi_path"],
                        r["text_preview"],
                    )
                    for r in rows
                ],
            )
            cur.execute("UPDATE books SET status='ready' WHERE book_id=%s", (book_id,))
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def delete_book(book_id: str) -> bool:
    """books row를 삭제한다. book_cfi_index/build_agent_snapshots/user_reading_position은
    전부 book_id에 ON DELETE CASCADE가 걸려있어 자동으로 같이 삭제된다.
    실제로 삭제된 행이 있었으면 True, 애초에 없던 book_id면 False.
    """
    if LOCAL_MODE:
        books = _local_books()
        existed = books.pop(book_id, None) is not None
        _save_local_books(books)
        _local_cfi_path(book_id).unlink(missing_ok=True)
        return existed
    conn = _connect()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM books WHERE book_id = %s", (book_id,))
            except psycopg2.errors.InvalidTextRepresentation:
                # book_id가 UUID 형식이 아니면(존재할 수 없는 id) 그냥 "없음"으로 취급.
                conn.rollback()
                return False
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()
