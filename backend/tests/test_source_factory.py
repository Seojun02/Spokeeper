import json

import pytest

from backend.app.content_source import AgentResultSource, FixtureSource
from backend.app.schemas import GraphJson
from backend.app.source_factory import make_content_source


def _write_store(path, book_id="book_local", boundary=10):
    payload = {
        "book_id": book_id,
        "entries": [
            {
                "boundary": boundary,
                "graph": {
                    "offset": boundary,
                    "spoiler_safe": True,
                    "entities": [
                        {
                            "id": "e_holmes",
                            "name": "셜록 홈즈",
                            "type": "person",
                            "color": "blue",
                        }
                    ],
                    "relationships": [],
                    "events": [],
                },
                "reminders": [
                    {"text": "홈즈가 사건을 살핀다.", "entity_ids": ["e_holmes"]},
                ],
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return book_id


def test_source_local_uses_only_local_precomputed_without_supabase(tmp_path, monkeypatch):
    # default.json alias resolution ("홈즈" -> "셜록 홈즈") is scoped to this
    # book_id, so it must be used here for the reminder-text alias assertion below.
    book_id = _write_store(tmp_path / "local.json", book_id="29f8f4f6-1cff-4b13-95e3-5405a19f8b11")

    def fail_if_called():
        raise AssertionError("Supabase must not be called in SPO_SOURCE=local")

    monkeypatch.setattr(AgentResultSource, "from_supabase", staticmethod(fail_if_called))

    source = make_content_source("local", tmp_path)
    graph = source.get_graph(book_id, 10, reveal_all=False)
    reminders = source.get_reminders(book_id, 10, entity_id=None)

    assert [entity.name for entity in graph.entities] == ["셜록 홈즈"]
    assert reminders.lines[0].text == "셜록 홈즈가 사건을 살핀다."


def test_source_agent_keeps_supabase_first_then_local_fallback(tmp_path, monkeypatch):
    _write_store(tmp_path / "local.json", book_id="book_local", boundary=10)
    supabase_source = AgentResultSource(
        {
            ("book_remote", 20): {
                "graph": GraphJson(
                    offset=20,
                    spoiler_safe=True,
                    entities=[],
                    relationships=[],
                    events=[],
                ),
                "reminders": [],
            }
        }
    )
    monkeypatch.setattr(AgentResultSource, "from_supabase", staticmethod(lambda: supabase_source))

    source = make_content_source("agent", tmp_path)

    assert source.get_graph("book_remote", 20, reveal_all=False).offset == 20
    assert source.get_graph("book_local", 10, reveal_all=False).entities[0].name == "셜록 홈즈"


def test_source_local_falls_back_to_fixture_when_no_local_json(tmp_path, monkeypatch):
    monkeypatch.setattr(
        AgentResultSource,
        "from_supabase",
        staticmethod(lambda: pytest.fail("Supabase must not be called in local mode")),
    )

    source = make_content_source("local", tmp_path)

    assert isinstance(source, FixtureSource)
