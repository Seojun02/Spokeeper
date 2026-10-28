"""Page metadata is additive; spoiler decisions remain global_index based."""
import os
import tempfile
from pathlib import Path

os.environ["SPO_DB"] = (
    f"sqlite:///{Path(tempfile.gettempdir()) / f'spokeeper_page_contract_{os.getpid()}.db'}"
)

from backend.app import db  # noqa: E402
from backend.app.content_source import AgentResultSource  # noqa: E402
from backend.app.schemas import (  # noqa: E402
    Entity,
    GraphJson,
    Progress,
    ProgressUpdate,
    ReminderLine,
)

db.init_db()


def test_legacy_progress_update_fields_remain_valid():
    update = ProgressUpdate(reading_offset=215, cfi="epubcfi(/6/2)")
    assert update.reading_offset == 215
    assert update.current_global_index is None
    assert update.cfi == "epubcfi(/6/2)"


def test_progress_keeps_page_and_global_index_together():
    row = db.put_progress(
        "page-contract-v2",
        "book-page-contract",
        215,
        reading_page=27,
        total_pages=120,
        current_cfi="epubcfi(/6/4)",
    )
    response = Progress(
        user_id=row.user_id,
        book_id=row.book_id,
        reading_offset=row.reading_offset,
        spoiler_boundary=row.spoiler_boundary,
        current_global_index=row.reading_offset,
        current_cfi=row.current_cfi,
        reading_page=row.reading_page,
        current_page=row.reading_page,
        total_pages=row.total_pages,
        spoiler_boundary_page=row.spoiler_boundary_page,
    )
    assert response.reading_offset == response.current_global_index == 215
    assert response.reading_page == response.current_page == 27
    assert response.total_pages == 120
    assert response.spoiler_boundary_page == 27
    assert response.current_cfi == "epubcfi(/6/4)"


def test_same_global_index_can_repaginate_without_changing_guard():
    user_id = "repaginate-v2"
    book_id = "book-repaginate"
    db.put_progress(user_id, book_id, 215, reading_page=27, total_pages=120)
    row = db.put_progress(user_id, book_id, 215, reading_page=31, total_pages=137)
    assert row.spoiler_boundary == 215
    assert row.spoiler_boundary_page == 31
    assert row.total_pages == 137


def test_render_source_filters_only_with_global_index():
    graph = GraphJson(
        offset=215,
        spoiler_safe=True,
        entities=[Entity(id="e1", name="공개 인물", type="person", color="blue")],
        relationships=[],
    )
    source = AgentResultSource(
        {
            ("book-guard", 215): {
                "graph": graph,
                "reminders": [ReminderLine(text="공개 사건", entity_ids=["e1"])],
            }
        }
    )
    assert source.get_graph("book-guard", 214, reveal_all=False).entities == []
    assert source.get_reminders("book-guard", 214, entity_id=None).lines == []
    assert source.get_graph("book-guard", 215, reveal_all=False).entities[0].id == "e1"


def test_page_metadata_can_be_added_without_changing_graph_offset():
    graph = GraphJson(offset=215, spoiler_safe=True, entities=[], relationships=[])
    response = graph.model_copy(
        update={
            "current_global_index": 215,
            "current_page": 27,
            "total_pages": 120,
            "spoiler_boundary_page": 27,
        }
    )
    assert response.offset == 215
    assert response.current_global_index == 215
    assert response.current_page == response.spoiler_boundary_page == 27
