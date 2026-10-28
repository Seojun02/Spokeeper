import pytest

from agents.tools.chunk_tool import make_chunks


def _chapter(length: int) -> list[dict]:
    return [
        {
            "chapter_index": 1,
            "title": "Chapter",
            "text": "x" * length,
        }
    ]


def test_default_chunks_use_finer_600_100_window(monkeypatch) -> None:
    monkeypatch.delenv("SPO_CHUNK_SIZE", raising=False)
    monkeypatch.delenv("SPO_CHUNK_OVERLAP", raising=False)

    chunks = make_chunks(_chapter(1500))

    assert [(chunk["start_char"], chunk["end_char"]) for chunk in chunks] == [
        (0, 600),
        (500, 1100),
        (1000, 1500),
    ]


def test_chunk_settings_can_be_overridden_by_environment(monkeypatch) -> None:
    monkeypatch.setenv("SPO_CHUNK_SIZE", "300")
    monkeypatch.setenv("SPO_CHUNK_OVERLAP", "50")

    chunks = make_chunks(_chapter(700))

    assert [(chunk["start_char"], chunk["end_char"]) for chunk in chunks] == [
        (0, 300),
        (250, 550),
        (500, 700),
    ]


def test_invalid_environment_chunk_size_is_explicit(monkeypatch) -> None:
    monkeypatch.setenv("SPO_CHUNK_SIZE", "small")

    with pytest.raises(ValueError, match="SPO_CHUNK_SIZE must be an integer"):
        make_chunks(_chapter(100))
