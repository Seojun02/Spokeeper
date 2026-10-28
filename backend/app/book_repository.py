"""Safe, persistent mapping from ``book_id`` to EPUB files.

Database and local metadata store paths relative to ``backend/data``.  Every
resolved path is checked again before it is handed to the EPUB parser.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from pathlib import Path, PurePath
from typing import TypedDict

from . import cfi_db


DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
REGISTRY_PATH = DATA_ROOT / "book_registry.json"
REGISTRY_VERSION = 1
_REGISTRY_LOCK = threading.RLock()
_DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test"}


class AvailableEpub(TypedDict):
    filename: str
    relative_path: str


class LocalBookMetadata(TypedDict):
    book_id: str
    title: str
    epub_path: str
    content_hash: str
    original_filename: str


class UnsafeEpubPathError(ValueError):
    """Raised when metadata points outside the managed data directory."""


class InvalidEpubPathError(ValueError):
    """Raised when metadata does not identify an EPUB file."""


def _is_development_environment() -> bool:
    return os.getenv("SPO_ENV", "development").strip().lower() in _DEVELOPMENT_ENVIRONMENTS


def _is_within_data_root(path: Path, data_root: Path) -> bool:
    try:
        path.relative_to(data_root)
    except ValueError:
        return False
    return True


def _normalize_relative_storage_path(stored_path: str) -> Path:
    raw_path = Path(stored_path.strip())
    if raw_path.is_absolute():
        raise UnsafeEpubPathError(
            "EPUB metadata must contain a path relative to backend/data."
        )

    # Read legacy values such as backend/data/uploaded_books/... while all new
    # writes use uploaded_books/... only.
    parts = list(PurePath(raw_path).parts)
    lowered = [part.lower() for part in parts]
    if len(parts) >= 2 and lowered[:2] == ["backend", "data"]:
        parts = parts[2:]
    elif parts and lowered[0] == "data":
        parts = parts[1:]

    if not parts:
        raise InvalidEpubPathError("The EPUB relative path is empty.")
    return Path(*parts)


def _validated_epub_path(relative_path: Path) -> Path:
    data_root = DATA_ROOT.resolve()
    candidate = (data_root / relative_path).resolve()

    if not _is_within_data_root(candidate, data_root):
        raise UnsafeEpubPathError(
            f"EPUB path points outside backend/data: {relative_path.as_posix()}"
        )
    if candidate.suffix.lower() != ".epub":
        raise InvalidEpubPathError(
            f"EPUB path does not have an .epub extension: {relative_path.as_posix()}"
        )
    if not candidate.is_file():
        raise FileNotFoundError(
            f"EPUB file does not exist: {relative_path.as_posix()}"
        )
    return candidate


def list_available_epubs() -> list[AvailableEpub]:
    """Return safe relative paths for EPUB files below ``backend/data``."""

    data_root = DATA_ROOT.resolve()
    if not data_root.is_dir():
        return []

    available: list[AvailableEpub] = []
    for path in data_root.rglob("*"):
        if path.suffix.lower() != ".epub" or not path.is_file():
            continue
        resolved = path.resolve()
        if not _is_within_data_root(resolved, data_root):
            continue
        relative_path = resolved.relative_to(data_root).as_posix()
        available.append({"filename": resolved.name, "relative_path": relative_path})

    return sorted(available, key=lambda item: item["relative_path"].casefold())


def _empty_registry() -> dict:
    return {"version": REGISTRY_VERSION, "books": {}}


def _read_registry() -> dict:
    with _REGISTRY_LOCK:
        if not REGISTRY_PATH.is_file():
            return _empty_registry()
        try:
            payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("Local EPUB registry is unreadable: book_registry.json") from error
        if payload.get("version") != REGISTRY_VERSION or not isinstance(payload.get("books"), dict):
            raise RuntimeError("Local EPUB registry has an unsupported schema: book_registry.json")
        return payload


def _write_registry(payload: dict) -> None:
    with _REGISTRY_LOCK:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        temporary_path = REGISTRY_PATH.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(REGISTRY_PATH)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register_local_epub(
    book_id: str,
    epub_path: str | Path,
    *,
    title: str = "",
    content_hash: str = "",
    original_filename: str = "",
) -> LocalBookMetadata:
    """Persist a safe relative EPUB mapping in the local JSON registry."""

    normalized_book_id = book_id.strip()
    if not normalized_book_id:
        raise ValueError("book_id is required")

    relative_path = _normalize_relative_storage_path(str(epub_path))
    resolved = _validated_epub_path(relative_path)
    canonical_relative_path = resolved.relative_to(DATA_ROOT.resolve()).as_posix()
    metadata: LocalBookMetadata = {
        "book_id": normalized_book_id,
        "title": title.strip() or resolved.stem,
        "epub_path": canonical_relative_path,
        "content_hash": content_hash or _sha256_file(resolved),
        "original_filename": original_filename.strip() or resolved.name,
    }

    with _REGISTRY_LOCK:
        registry = _read_registry()
        registry["books"][normalized_book_id] = metadata
        _write_registry(registry)
    return metadata


def get_local_book_metadata(book_id: str) -> LocalBookMetadata | None:
    item = _read_registry()["books"].get(book_id)
    return dict(item) if isinstance(item, dict) else None


def list_registered_books() -> list[LocalBookMetadata]:
    books = _read_registry()["books"]
    return [dict(books[book_id]) for book_id in sorted(books)]


def unregister_local_book(book_id: str) -> bool:
    """Remove only the metadata mapping; callers own deletion of EPUB bytes."""

    with _REGISTRY_LOCK:
        registry = _read_registry()
        removed = registry["books"].pop(book_id, None)
        if removed is None:
            return False
        _write_registry(registry)
        return True


def _generated_book_id(content_hash: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"spokeeper:epub:{content_hash}"))


def bootstrap_local_epubs() -> list[LocalBookMetadata]:
    """Register untracked EPUBs deterministically without exposing future data.

    Files in ``uploaded_books`` retain their UUID filename as ``book_id``.
    Other files receive a UUID5 derived from SHA-256, so repeated startup scans
    and file renames preserve the same identifier.
    """

    existing = list_registered_books()
    by_hash = {item.get("content_hash", ""): item for item in existing if item.get("content_hash")}
    by_path = {item.get("epub_path", ""): item for item in existing}
    candidates = sorted(
        list_available_epubs(),
        key=lambda item: (
            0 if PurePath(item["relative_path"]).parts[:1] == ("uploaded_books",) else 1,
            item["relative_path"].casefold(),
        ),
    )

    for candidate in candidates:
        relative_path = candidate["relative_path"]
        resolved = _validated_epub_path(Path(relative_path))
        content_hash = _sha256_file(resolved)
        current = by_path.get(relative_path) or by_hash.get(content_hash)
        if current is not None:
            if current.get("epub_path") != relative_path:
                try:
                    _validated_epub_path(Path(current["epub_path"]))
                except FileNotFoundError:
                    repaired = register_local_epub(
                        current["book_id"],
                        relative_path,
                        title=current.get("title", resolved.stem),
                        content_hash=content_hash,
                        original_filename=current.get("original_filename", resolved.name),
                    )
                    by_path[relative_path] = repaired
                    by_hash[content_hash] = repaired
            continue

        path = PurePath(relative_path)
        is_uploaded = path.parts[:1] == ("uploaded_books",)
        book_id = path.stem if is_uploaded else _generated_book_id(content_hash)
        metadata = register_local_epub(
            book_id,
            relative_path,
            title=resolved.stem,
            content_hash=content_hash,
            original_filename=resolved.name,
        )
        by_path[relative_path] = metadata
        by_hash[content_hash] = metadata

    return list_registered_books()


def _candidate_summary(available: list[AvailableEpub] | None = None) -> str:
    candidates = available if available is not None else list_available_epubs()
    return ", ".join(item["relative_path"] for item in candidates) or "none"


def _canonical_upload_path(book_id: str) -> Path | None:
    if Path(book_id).name != book_id or "/" in book_id or "\\" in book_id:
        return None
    relative_path = Path("uploaded_books") / f"{book_id}.epub"
    try:
        return _validated_epub_path(relative_path)
    except FileNotFoundError:
        return None


def resolve_epub_path(book_id: str) -> Path:
    """Resolve ``book_id`` through local metadata, DB metadata, or dev fallback."""

    normalized_book_id = book_id.strip()
    if not normalized_book_id:
        raise FileNotFoundError("book_id is required to resolve an EPUB")

    local_metadata = get_local_book_metadata(normalized_book_id)
    stored_path = (
        local_metadata.get("epub_path")
        if local_metadata is not None
        else cfi_db.get_book_storage_path(normalized_book_id)
    )
    if stored_path:
        try:
            return _validated_epub_path(_normalize_relative_storage_path(stored_path))
        except FileNotFoundError as error:
            canonical_path = _canonical_upload_path(normalized_book_id)
            if canonical_path is not None:
                return canonical_path
            raise FileNotFoundError(
                f"Mapped EPUB is missing for book_id={normalized_book_id}. "
                f"{error} Available EPUBs: {_candidate_summary()}"
            ) from error
        except (UnsafeEpubPathError, InvalidEpubPathError) as error:
            raise type(error)(
                f"Invalid EPUB mapping for book_id={normalized_book_id}. "
                f"{error} Available EPUBs: {_candidate_summary()}"
            ) from error

    canonical_path = _canonical_upload_path(normalized_book_id)
    if canonical_path is not None:
        return canonical_path

    available = list_available_epubs()
    candidates = _candidate_summary(available)
    if not _is_development_environment():
        raise FileNotFoundError(
            f"No EPUB mapping for book_id={normalized_book_id}; automatic fallback is disabled. "
            f"Available EPUBs: {candidates}"
        )
    if len(available) == 1:
        return _validated_epub_path(Path(available[0]["relative_path"]))
    if not available:
        raise FileNotFoundError(
            f"No EPUB mapping for book_id={normalized_book_id}, and backend/data contains no EPUB files."
        )
    raise FileNotFoundError(
        f"No EPUB mapping for book_id={normalized_book_id}; {len(available)} candidates exist. "
        f"Automatic selection is unsafe. Available EPUBs: {candidates}"
    )
