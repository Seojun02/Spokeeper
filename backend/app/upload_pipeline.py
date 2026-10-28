"""EPUB 업로드 → CFI 인덱스 생성 → Supabase 적재 파이프라인.

같은 파일(content_hash 동일)이 다시 업로드되면 재분석 없이 기존 book_id를 재사용한다.
CFI 생성 자체는 Node(`cfi_tools/build_cfi_index.js`)에 위임한다 — CFI는 EPUB의 실제
DOM 구조를 기준으로 만들어지는 값이라, 프론트(epub.js)와 같은 방식으로 계산해야
나중에 두 값이 어긋나지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

from . import cfi_db
from .book_repository import register_local_epub

CFI_TOOLS_DIR = Path(__file__).resolve().parent.parent / "cfi_tools"
CFI_SCRIPT = CFI_TOOLS_DIR / "build_cfi_index.js"

# 실제 Supabase Storage 연동 전까지, 업로드된 원본 EPUB을 로컬에 보관해 본문 서빙에 사용한다.
UPLOADED_BOOKS_DIR = Path(__file__).resolve().parent.parent / "data" / "uploaded_books"


def epub_path_for(book_id: str) -> Path:
    return UPLOADED_BOOKS_DIR / f"{book_id}.epub"


def _storage_path_for(book_id: str) -> str:
    """DB에 저장할 backend/data 기준 POSIX 상대경로."""
    return (Path("uploaded_books") / f"{book_id}.epub").as_posix()


class CfiBuildError(RuntimeError):
    pass


def _content_hash(epub_bytes: bytes) -> str:
    return hashlib.sha256(epub_bytes).hexdigest()


def _run_cfi_script(unpacked_dir: Path, output_json: Path) -> None:
    result = subprocess.run(
        ["node", str(CFI_SCRIPT), str(unpacked_dir), str(output_json)],
        cwd=CFI_TOOLS_DIR,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise CfiBuildError(
            f"CFI 생성 스크립트 실패 (exit={result.returncode}):\n{result.stderr}"
        )


def ingest_epub(epub_bytes: bytes, filename: str, title: str) -> dict:
    """EPUB 바이트를 받아 Supabase에 적재하고 book_id 등을 반환.

    반환: {"book_id": str, "reused": bool, "paragraph_count": int}
    """
    content_hash = _content_hash(epub_bytes)

    existing_book_id = cfi_db.find_book_by_hash(content_hash)
    if existing_book_id and cfi_db.has_paragraphs(existing_book_id):
        # 예전에 로컬 저장 없이 적재된 책일 수 있으니, 없으면 지금이라도 채워 넣는다.
        local_path = epub_path_for(existing_book_id)
        if not local_path.exists():
            UPLOADED_BOOKS_DIR.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(epub_bytes)
        cfi_db.set_storage_path(existing_book_id, _storage_path_for(existing_book_id))
        register_local_epub(
            existing_book_id,
            _storage_path_for(existing_book_id),
            title=title,
            content_hash=content_hash,
            original_filename=filename,
        )
        return {
            "book_id": existing_book_id,
            "reused": True,
            "paragraph_count": cfi_db.total_paragraphs(existing_book_id),
        }

    book_id = existing_book_id or cfi_db.insert_book(
        content_hash=content_hash,
        title=title,
        storage_path="",  # 아래에서 book_id 확정 후 채움
    )

    UPLOADED_BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    local_epub_path = epub_path_for(book_id)
    local_epub_path.write_bytes(epub_bytes)
    cfi_db.set_storage_path(book_id, _storage_path_for(book_id))
    register_local_epub(
        book_id,
        _storage_path_for(book_id),
        title=title,
        content_hash=content_hash,
        original_filename=filename,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        unpacked_dir = tmp_path / "unpacked"
        unpacked_dir.mkdir()
        with zipfile.ZipFile(local_epub_path) as zf:
            zf.extractall(unpacked_dir)

        output_json = tmp_path / "cfi_index.json"
        _run_cfi_script(unpacked_dir, output_json)

        rows = json.loads(output_json.read_text(encoding="utf-8"))

    if not rows:
        raise CfiBuildError("CFI 인덱스가 비어 있습니다 (EPUB 구조를 인식하지 못했을 수 있음).")

    count = cfi_db.insert_paragraphs(book_id, rows)
    cfi_db.clear_cache()

    return {"book_id": book_id, "reused": False, "paragraph_count": count}
