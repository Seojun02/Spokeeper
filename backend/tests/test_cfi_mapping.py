from backend.app import cfi_db
from backend.app.cfi_db import CfiParagraph
from backend.app.cfi_utils import cfi_to_path


def _paragraph(index: int, raw_cfi: str) -> CfiParagraph:
    return CfiParagraph(
        global_index=index,
        chapter_index=1,
        chapter_title="chapter",
        paragraph_index=index,
        cfi_raw=raw_cfi,
        cfi_path=cfi_to_path(raw_cfi),
        text_preview="",
    )


def test_indexer_and_epubjs_content_roots_are_equivalent() -> None:
    indexed = "epubcfi(/6/6!/2/4/18/1:0)"
    relocated = "epubcfi(/6/6!/4/18/1:0)"

    assert cfi_to_path(indexed) == cfi_to_path(relocated)


def test_relocated_cfi_does_not_jump_to_end_of_spine(monkeypatch) -> None:
    paragraphs = (
        _paragraph(0, "epubcfi(/6/4!/2/4/4/1)"),
        _paragraph(1, "epubcfi(/6/6!/2/4/4/1)"),
        _paragraph(2, "epubcfi(/6/6!/2/4/18/1)"),
        _paragraph(3, "epubcfi(/6/6!/2/4/204/1)"),
        _paragraph(4, "epubcfi(/6/6!/2/4/976/1)"),
    )
    monkeypatch.setattr(cfi_db, "get_paragraphs", lambda _book_id: paragraphs)

    mapped = cfi_db.find_global_index_by_cfi(
        "book",
        "epubcfi(/6/6!/4/18/1:0)",
    )

    assert mapped == 2
    assert mapped != paragraphs[-1].global_index
