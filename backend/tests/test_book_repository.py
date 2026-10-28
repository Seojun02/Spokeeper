import io
import json
import zipfile
from pathlib import Path

import pytest

from backend.app import book_repository, upload_pipeline


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(book_repository, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(book_repository, "REGISTRY_PATH", tmp_path / "book_registry.json")
    monkeypatch.setenv("SPO_ENV", "development")
    return tmp_path


def set_mapping(monkeypatch: pytest.MonkeyPatch, stored_path: str | None) -> None:
    monkeypatch.setattr(
        book_repository.cfi_db,
        "get_book_storage_path",
        lambda _book_id: stored_path,
    )


def test_resolve_epub_path_uses_book_storage_mapping(data_root, monkeypatch):
    epub = data_root / "uploaded_books" / "book-1.epub"
    epub.parent.mkdir()
    epub.write_bytes(b"epub")
    set_mapping(monkeypatch, "uploaded_books/book-1.epub")

    assert book_repository.resolve_epub_path("book-1") == epub.resolve()
    assert book_repository.list_available_epubs() == [
        {"filename": "book-1.epub", "relative_path": "uploaded_books/book-1.epub"}
    ]


def test_resolve_epub_path_missing_book_and_no_epub(data_root, monkeypatch):
    set_mapping(monkeypatch, None)
    with pytest.raises(FileNotFoundError, match="book-missing"):
        book_repository.resolve_epub_path("book-missing")


def test_resolve_epub_path_uses_only_epub_as_development_fallback(data_root, monkeypatch):
    epub = data_root / "only.epub"
    epub.write_bytes(b"epub")
    set_mapping(monkeypatch, None)
    assert book_repository.resolve_epub_path("unmapped-book") == epub.resolve()


def test_resolve_epub_path_rejects_ambiguous_development_fallback(data_root, monkeypatch):
    (data_root / "first.epub").write_bytes(b"first")
    nested = data_root / "uploaded_books"
    nested.mkdir()
    (nested / "second.epub").write_bytes(b"second")
    set_mapping(monkeypatch, None)

    with pytest.raises(FileNotFoundError) as exc_info:
        book_repository.resolve_epub_path("unmapped-book")

    message = str(exc_info.value)
    assert "first.epub" in message
    assert "uploaded_books/second.epub" in message
    assert "Automatic selection is unsafe" in message


def test_resolve_epub_path_rejects_path_traversal(data_root, monkeypatch):
    outside = data_root.parent / "outside.epub"
    outside.write_bytes(b"outside")
    set_mapping(monkeypatch, "../outside.epub")
    with pytest.raises(book_repository.UnsafeEpubPathError, match="outside backend/data"):
        book_repository.resolve_epub_path("book-1")


def test_resolve_epub_path_rejects_non_epub_file(data_root, monkeypatch):
    text_file = data_root / "book.txt"
    text_file.write_text("not an epub", encoding="utf-8")
    set_mapping(monkeypatch, "book.txt")
    with pytest.raises(book_repository.InvalidEpubPathError, match="epub extension"):
        book_repository.resolve_epub_path("book-1")


def test_resolve_epub_path_disables_fallback_in_production(data_root, monkeypatch):
    (data_root / "only.epub").write_bytes(b"epub")
    set_mapping(monkeypatch, None)
    monkeypatch.setenv("SPO_ENV", "production")
    with pytest.raises(FileNotFoundError, match="fallback is disabled"):
        book_repository.resolve_epub_path("unmapped-book")


def test_resolve_epub_path_rejects_absolute_metadata_path(data_root, monkeypatch):
    epub = data_root / "book.epub"
    epub.write_bytes(b"epub")
    set_mapping(monkeypatch, str(epub.resolve()))
    with pytest.raises(book_repository.UnsafeEpubPathError, match="relative to backend/data"):
        book_repository.resolve_epub_path("book-1")


def test_resolve_epub_path_recovers_stale_mapping_with_canonical_book_file(data_root, monkeypatch):
    epub = data_root / "uploaded_books" / "book-1.epub"
    epub.parent.mkdir()
    epub.write_bytes(b"epub")
    set_mapping(monkeypatch, "uploaded_books/removed-name.epub")
    assert book_repository.resolve_epub_path("book-1") == epub.resolve()


def test_missing_mapping_error_includes_book_id_and_safe_candidates(data_root, monkeypatch):
    (data_root / "first.epub").write_bytes(b"first")
    (data_root / "second.epub").write_bytes(b"second")
    set_mapping(monkeypatch, None)
    with pytest.raises(FileNotFoundError) as exc_info:
        book_repository.resolve_epub_path("book-missing")

    message = str(exc_info.value)
    assert "book_id=book-missing" in message
    assert "first.epub" in message and "second.epub" in message
    assert str(data_root.resolve()) not in message


def test_reused_upload_persists_db_and_json_mapping(tmp_path, monkeypatch):
    uploaded_dir = tmp_path / "uploaded_books"
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(upload_pipeline, "UPLOADED_BOOKS_DIR", uploaded_dir)
    monkeypatch.setattr(book_repository, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(book_repository, "REGISTRY_PATH", tmp_path / "book_registry.json")
    monkeypatch.setattr(upload_pipeline.cfi_db, "find_book_by_hash", lambda _hash: "book-1")
    monkeypatch.setattr(upload_pipeline.cfi_db, "has_paragraphs", lambda _book_id: True)
    monkeypatch.setattr(upload_pipeline.cfi_db, "total_paragraphs", lambda _book_id: 7)
    monkeypatch.setattr(
        upload_pipeline.cfi_db,
        "set_storage_path",
        lambda book_id, storage_path: recorded.append((book_id, storage_path)),
    )
    set_mapping(monkeypatch, None)

    result = upload_pipeline.ingest_epub(b"same epub", "original.epub", "Original")

    assert result == {"book_id": "book-1", "reused": True, "paragraph_count": 7}
    assert (uploaded_dir / "book-1.epub").read_bytes() == b"same epub"
    assert recorded == [("book-1", "uploaded_books/book-1.epub")]
    assert book_repository.resolve_epub_path("book-1") == (uploaded_dir / "book-1.epub").resolve()


def test_new_upload_returns_book_id_and_resolves_after_persistent_registration(
    tmp_path, monkeypatch
):
    uploaded_dir = tmp_path / "uploaded_books"
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(upload_pipeline, "UPLOADED_BOOKS_DIR", uploaded_dir)
    monkeypatch.setattr(book_repository, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(book_repository, "REGISTRY_PATH", tmp_path / "book_registry.json")
    monkeypatch.setattr(upload_pipeline.cfi_db, "find_book_by_hash", lambda _hash: None)
    monkeypatch.setattr(
        upload_pipeline.cfi_db,
        "insert_book",
        lambda content_hash, title, storage_path: "new-book",
    )
    monkeypatch.setattr(
        upload_pipeline.cfi_db,
        "set_storage_path",
        lambda book_id, storage_path: recorded.append((book_id, storage_path)),
    )
    monkeypatch.setattr(
        upload_pipeline,
        "_run_cfi_script",
        lambda _unpacked, output: output.write_text('[{"global_index": 0}]', encoding="utf-8"),
    )
    monkeypatch.setattr(upload_pipeline.cfi_db, "insert_paragraphs", lambda _id, rows: len(rows))
    monkeypatch.setattr(upload_pipeline.cfi_db, "clear_cache", lambda: None)
    set_mapping(monkeypatch, None)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as epub_zip:
        epub_zip.writestr("mimetype", "application/epub+zip")

    result = upload_pipeline.ingest_epub(archive.getvalue(), "new.epub", "New Book")

    assert result == {"book_id": "new-book", "reused": False, "paragraph_count": 1}
    assert recorded == [("new-book", "uploaded_books/new-book.epub")]
    assert book_repository.resolve_epub_path(result["book_id"]) == (
        uploaded_dir / "new-book.epub"
    ).resolve()


def test_registry_mapping_survives_fresh_reads(data_root, monkeypatch):
    epub = data_root / "library" / "existing.epub"
    epub.parent.mkdir()
    epub.write_bytes(b"persistent epub")
    set_mapping(monkeypatch, None)
    book_repository.register_local_epub(
        "existing-book",
        "library/existing.epub",
        title="Existing",
        original_filename="original.epub",
    )

    assert book_repository.get_local_book_metadata("existing-book")["epub_path"] == "library/existing.epub"
    assert book_repository.resolve_epub_path("existing-book") == epub.resolve()
    assert book_repository.resolve_epub_path("existing-book") == epub.resolve()


def test_bootstrap_is_deterministic_and_deduplicates_by_sha256(data_root, monkeypatch):
    set_mapping(monkeypatch, None)
    (data_root / "manually-added.epub").write_bytes(b"same content")
    first = book_repository.bootstrap_local_epubs()
    first_id = first[0]["book_id"]

    duplicate_dir = data_root / "copies"
    duplicate_dir.mkdir()
    (duplicate_dir / "renamed.epub").write_bytes(b"same content")
    second = book_repository.bootstrap_local_epubs()

    assert len(first) == len(second) == 1
    assert second[0]["book_id"] == first_id
    assert second[0]["epub_path"] == "manually-added.epub"


def test_bootstrap_repairs_moved_file_with_same_hash(data_root, monkeypatch):
    set_mapping(monkeypatch, None)
    original = data_root / "original.epub"
    original.write_bytes(b"movable content")
    first = book_repository.bootstrap_local_epubs()[0]
    original.unlink()
    moved = data_root / "moved" / "renamed.epub"
    moved.parent.mkdir()
    moved.write_bytes(b"movable content")

    repaired = book_repository.bootstrap_local_epubs()[0]

    assert repaired["book_id"] == first["book_id"]
    assert repaired["epub_path"] == "moved/renamed.epub"
    assert book_repository.resolve_epub_path(first["book_id"]) == moved.resolve()


def test_registered_missing_file_has_clear_book_id_error(data_root, monkeypatch):
    set_mapping(monkeypatch, None)
    registry = {
        "version": 1,
        "books": {
            "missing-book": {
                "book_id": "missing-book",
                "title": "Missing",
                "epub_path": "removed.epub",
                "content_hash": "deadbeef",
                "original_filename": "removed.epub",
            }
        },
    }
    book_repository.REGISTRY_PATH.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(FileNotFoundError) as exc_info:
        book_repository.resolve_epub_path("missing-book")

    message = str(exc_info.value)
    assert "book_id=missing-book" in message and "removed.epub" in message
    assert str(data_root.resolve()) not in message


def test_register_local_epub_rejects_absolute_path(data_root):
    epub = data_root / "book.epub"
    epub.write_bytes(b"epub")
    with pytest.raises(book_repository.UnsafeEpubPathError):
        book_repository.register_local_epub("book", epub.resolve())
