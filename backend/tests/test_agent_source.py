"""에이전트 어댑터 + AgentResultSource 계약 테스트.

BuildAgent 형태(이름 기반)를 계약(id 기반)으로 변환하고, precompute→로드→서빙이
FixtureSource 와 동일한 게이팅 시맨틱을 유지하는지 검증한다.
"""
from __future__ import annotations

from backend.app import agent_adapter as ad
from backend.app.content_source import AgentResultSource
from backend.app.precompute import build_entries, write_store
from backend.app.schemas import Entity, GraphJson, ReminderLine, Relationship
from backend.scripts.make_demo_store import BOOK_ID, DEMO_BUILD_RESULTS


def _disable_llm_verifier(monkeypatch):
    from agents import indirect_leakage_judge, reminder_writer_agent
    from agents import verifier_agent

    monkeypatch.setattr(verifier_agent, "verify_build_result", lambda result, book_id=None: result)
    monkeypatch.setattr(
        verifier_agent,
        "canonicalize_new_characters",
        lambda new_characters, canonical_registry, book_id=None: ({}, {}),
    )
    monkeypatch.setattr(reminder_writer_agent, "write_reminders", lambda result: {"lines": []})
    monkeypatch.setattr(indirect_leakage_judge, "judge_reminders", lambda lines: lines)


def test_adapter_maps_names_to_ids():
    result = DEMO_BUILD_RESULTS[0][1]
    graph = ad.to_graph_json(result, boundary=215)
    # 인물 3 + 관계 2
    assert len(graph.entities) == 3
    assert len(graph.relationships) == 2
    # source/target 은 entity id (이름이 아님)
    ids = {e.id for e in graph.entities}
    for rel in graph.relationships:
        assert rel.source in ids and rel.target in ids
    # 아틀라스 호는 optional type=ship 존중
    atlas = next(e for e in graph.entities if e.name == "아틀라스 호")
    assert atlas.type == "ship"


def test_adapter_id_is_stable():
    assert ad.entity_id("민우") == ad.entity_id(" 민우 ")


def test_adapter_maps_relation_kind_from_build_result():
    """BuildAgent가 판단한 relation_kind("personal"/"action")가 그대로 Relationship에
    실린다. 값이 없거나 잘못된 값이면(구버전 데이터 등) None으로 떨어진다."""
    result = {
        "characters": [{"name": "민준"}, {"name": "서연"}, {"name": "필주"}],
        "relations": [
            {"source": "민준", "target": "서연", "relation": "연인", "relation_kind": "personal"},
            {"source": "민준", "target": "필주", "relation": "목격자", "relation_kind": "action"},
            {"source": "서연", "target": "필주", "relation": "동료", "relation_kind": "모름"},
        ],
    }
    graph = ad.to_graph_json(result, boundary=100)
    by_label = {r.label: r for r in graph.relationships}

    assert by_label["연인"].relation_kind == "personal"
    assert by_label["목격자"].relation_kind == "action"
    assert by_label["동료"].relation_kind is None


def test_reminders_from_events():
    lines = ad.to_reminder_lines(DEMO_BUILD_RESULTS[0][1])
    assert len(lines) == 2
    assert all(l.entity_ids for l in lines)


def test_revision_offset_is_first_seen(monkeypatch):
    _disable_llm_verifier(monkeypatch)
    entries = build_entries(DEMO_BUILD_RESULTS)
    # 강 국장 관계(r3)는 320 에서 처음 등장 → 380 에서도 revision_offset=320 유지
    by_boundary = {e["boundary"]: e for e in entries}
    g380 = by_boundary[380]["graph"]
    kang_id = ad.entity_id("강 국장")
    seohyun_id = ad.entity_id("서현")
    rel = next(r for r in g380["relationships"]
               if {r["source"], r["target"]} == {seohyun_id, kang_id})
    assert rel["revision_offset"] == 320


def test_agent_source_gating(tmp_path, monkeypatch):
    _disable_llm_verifier(monkeypatch)
    entries = build_entries(DEMO_BUILD_RESULTS)
    write_store(BOOK_ID, entries, store_dir=tmp_path)
    src = AgentResultSource.from_json_file(tmp_path / f"{BOOK_ID}.json")

    # 215 미만: precompute 지점 없음 → 빈 그래프
    assert src.get_graph(BOOK_ID, 200, reveal_all=False).entities == []
    # 215: 인물 3
    assert len(src.get_graph(BOOK_ID, 215, reveal_all=False).entities) == 3
    # 379 (c3 경계 380 직전): 윤 팀장 미공개 → 여전히 320 스냅샷(인물 4)
    g379 = src.get_graph(BOOK_ID, 379, reveal_all=False)
    assert ad.entity_id("윤 팀장") not in {e.id for e in g379.entities}
    # 380: 인물 5
    assert len(src.get_graph(BOOK_ID, 380, reveal_all=False).entities) == 5


def test_agent_source_derives_entity_first_seen_without_future_snapshots():
    def graph(boundary, entity_ids):
        return GraphJson(
            offset=boundary,
            spoiler_safe=True,
            entities=[Entity(id=entity_id, name=entity_id, type="person", color="blue") for entity_id in entity_ids],
            relationships=[],
        )

    source = AgentResultSource(
        {
            ("book-layout", 10): {"graph": graph(10, ["a"]), "reminders": []},
            ("book-layout", 20): {"graph": graph(20, ["a", "b"]), "reminders": []},
            ("book-layout", 30): {"graph": graph(30, ["a", "b", "future"]), "reminders": []},
        }
    )

    result = source.get_graph("book-layout", 20, reveal_all=False)
    assert {entity.id: entity.first_seen_global_index for entity in result.entities} == {"a": 10, "b": 20}


def test_agent_source_applies_character_alias_dictionary_before_returning_snapshots():
    book_id = "3fb1a332-ae08-450b-8b20-3567a4da4180"
    graph = GraphJson(
        offset=10,
        spoiler_safe=True,
        entities=[
            Entity(id="e_full", name="셜록 홈즈", type="person", color="blue"),
            Entity(id="e_short", name="홈즈", type="person", color="blue"),
            Entity(id="e_watson", name="왓슨", type="person", color="blue"),
        ],
        relationships=[
            Relationship(
                id="r1",
                source="e_short",
                target="e_watson",
                label="동료",
                tone="ally",
                description="홈즈와 왓슨은 함께 조사했다.",
                revision_offset=10,
            ),
            Relationship(
                id="r2",
                source="e_full",
                target="e_watson",
                label="동료",
                tone="ally",
                description="홈즈와 왓슨은 함께 조사했다.",
                revision_offset=10,
            ),
        ],
    )
    src = AgentResultSource(
        {
            (book_id, 10): {
                "graph": graph,
                "reminders": [
                    ReminderLine(text="홈즈와 셜록 홈스가 왓슨과 만났다.", entity_ids=["e_short", "e_full", "e_watson"])
                ],
            }
        }
    )

    normalized_graph = src.get_graph(book_id, 10, reveal_all=False)
    names = [entity.name for entity in normalized_graph.entities]
    sherlock_id = next(entity.id for entity in normalized_graph.entities if entity.name == "셜록 홈즈")
    sherlock = next(entity for entity in normalized_graph.entities if entity.name == "셜록 홈즈")
    watson_id = next(entity.id for entity in normalized_graph.entities if entity.name == "존 H. 왓슨")

    assert names == ["셜록 홈즈", "존 H. 왓슨"]
    assert "홈즈" in sherlock.aliases
    assert len(normalized_graph.relationships) == 1
    assert normalized_graph.relationships[0].source == sherlock_id
    assert normalized_graph.relationships[0].target == watson_id

    reminders = src.get_reminders(book_id, 10, entity_id=sherlock_id)
    assert reminders.lines[0].entity_ids == [sherlock_id, watson_id]
    assert reminders.lines[0].text == "셜록 홈즈와 셜록 홈즈가 존 H. 왓슨과 만났다."


def test_agent_source_filters_legacy_snapshot_aliases_generic_roles_and_weak_entities():
    # default.json (스탬포드/그레그슨/조셉 스미스 별칭) is scoped to this book_id.
    book_id = "29f8f4f6-1cff-4b13-95e3-5405a19f8b11"
    graph = GraphJson(
        offset=20,
        spoiler_safe=True,
        entities=[
            Entity(id="e_stamford_a", name="스탬포드", type="person", color="blue"),
            Entity(id="e_stamford_b", name="스태퍼드", type="person", color="blue"),
            Entity(id="e_gregson_a", name="토비아스 그레그슨", type="person", color="blue"),
            Entity(id="e_gregson_b", name="그렉슨", type="person", color="blue"),
            Entity(id="e_smith_a", name="조셉 스미스", type="person", color="blue"),
            Entity(id="e_smith_b", name="요셉 스미스", type="person", color="blue"),
            Entity(id="e_doctor", name="의사", type="person", color="blue"),
            Entity(id="e_driver", name="마부", type="person", color="blue"),
            Entity(id="e_girl", name="여자아이", type="person", color="blue"),
            Entity(id="e_drunk", name="술에 취한 남자", type="person", color="blue"),
            Entity(id="e_stangerson_family", name="스텐거슨 형제", type="person", color="blue"),
        ],
        relationships=[
            Relationship(id="r1", source="e_stamford_b", target="e_gregson_b", label="소개", tone="neutral", description="스태퍼드와 그렉슨", revision_offset=20),
            Relationship(id="r2", source="e_stamford_a", target="e_gregson_a", label="소개", tone="neutral", description="스탬포드와 토비아스 그레그슨", revision_offset=20),
            Relationship(id="r3", source="e_smith_b", target="e_doctor", label="대화", tone="neutral", description="요셉 스미스와 의사", revision_offset=20),
            Relationship(id="r4", source="e_driver", target="e_girl", label="목격", tone="neutral", description="마부와 여자아이", revision_offset=20),
            Relationship(id="r6", source="e_stangerson_family", target="e_gregson_a", label="언급", tone="neutral", description="스텐거슨 형제", revision_offset=20),
        ],
    )
    src = AgentResultSource(
        {
            (book_id, 20): {
                "graph": graph,
                "reminders": [
                    ReminderLine(
                        text="스태퍼드와 그렉슨, 요셉 스미스가 의사와 마부를 만났다.",
                        entity_ids=["e_stamford_b", "e_gregson_b", "e_smith_b", "e_doctor", "e_driver"],
                    ),
                    ReminderLine(
                        text="스태퍼드와 그렉슨, 요셉 스미스가 다시 언급됐다.",
                        entity_ids=["e_stamford_b", "e_gregson_b", "e_smith_b"],
                    ),
                ],
            }
        }
    )

    normalized_graph = src.get_graph(book_id, 20, reveal_all=False)
    names = [entity.name for entity in normalized_graph.entities]

    assert names == [
        "스탬포드",
        "토비아스 그레그슨",
        "조셉 스미스",
        "스텐거슨 형제",
    ]
    assert "조셉 스텐저슨" not in names
    assert all(name not in names for name in ["의사", "마부", "여자아이", "술에 취한 남자"])
    assert {relationship.label for relationship in normalized_graph.relationships} == {"소개", "언급"}

    reminders = src.get_reminders(book_id, 20, entity_id=None)
    assert len(reminders.lines) == 1
    assert reminders.lines[0].text == "스탬포드와 토비아스 그레그슨, 조셉 스미스가 다시 언급됐다."
    assert len(reminders.lines[0].entity_ids) == 3


def test_agent_source_normalizes_hound_snapshot_without_merging_distinct_people():
    """정적 별칭 테이블로 표기 변형은 병합하되(스텁블턴→스태플턴), 실제로 다른
    사람(스태플턴 vs 스태플턴 양)은 병합하지 않고, 일반명사(술꾼들/목동/우편국장
    같이 특정 작품에 한정되지 않는 집단·역할 표현)는 걸러내는지 확인한다.
    가문/가족 같은 비인물 고유명사 제거는 이 결정론적 계층이 아니라 build 시점의
    ConsolidationAgent가 담당하므로 여기서는 다루지 않는다.
    """
    book_id = "29f8f4f6-1cff-4b13-95e3-5405a19f8b11"
    graph = GraphJson(
        offset=30,
        spoiler_safe=True,
        entities=[
            Entity(id="e_stapleton_a", name="스텁블턴", type="person", color="blue"),
            Entity(id="e_stapleton_b", name="스태플턴", type="person", color="blue"),
            Entity(id="e_miss_a", name="스텁블턴의 여동생", type="person", color="blue"),
            Entity(id="e_miss_b", name="스탤튼 양", type="person", color="blue"),
            Entity(id="e_drunkards", name="술꾼들", type="person", color="blue"),
            Entity(id="e_shepherd", name="목동", type="person", color="blue"),
            Entity(id="e_postmaster", name="우편국장", type="person", color="blue"),
            Entity(id="e_charles", name="찰스 배스커빌 경", type="person", color="blue"),
            Entity(id="e_henry", name="헨리 배스커빌", type="person", color="blue"),
            Entity(id="e_hugo", name="휴고 배스커빌", type="person", color="blue"),
            Entity(id="e_roger", name="로저 베스커빌", type="person", color="blue"),
        ],
        relationships=[
            Relationship(id="r1", source="e_stapleton_a", target="e_miss_a", label="남매", tone="neutral", description="스텁블턴과 여동생", revision_offset=30),
            Relationship(id="r2", source="e_stapleton_b", target="e_miss_b", label="남매", tone="neutral", description="스태플턴과 스탤튼 양", revision_offset=30),
            Relationship(id="r5", source="e_drunkards", target="e_shepherd", label="목격", tone="neutral", description="술꾼들과 목동", revision_offset=30),
            Relationship(id="r6", source="e_charles", target="e_henry", label="가족", tone="neutral", description="찰스 경과 헨리", revision_offset=30),
            Relationship(id="r7", source="e_hugo", target="e_roger", label="언급", tone="neutral", description="휴고와 로저", revision_offset=30),
        ],
    )
    src = AgentResultSource(
        {
            (book_id, 30): {
                "graph": graph,
                "reminders": [
                    ReminderLine(
                        text="스텁블턴과 스텁블턴의 여동생, 술꾼들과 목동이 언급됐다.",
                        entity_ids=["e_stapleton_a", "e_miss_a", "e_drunkards", "e_shepherd"],
                    ),
                    ReminderLine(
                        text="스텁블턴과 스탤튼 양이 따로 언급됐다.",
                        entity_ids=["e_stapleton_a", "e_miss_b"],
                    )
                ],
            }
        }
    )

    normalized_graph = src.get_graph(book_id, 30, reveal_all=False)
    names = [entity.name for entity in normalized_graph.entities]

    assert names == [
        "스태플턴",
        "스태플턴 양",
        "찰스 배스커빌 경",
        "헨리 배스커빌",
        "휴고 배스커빌",
        "로저 베스커빌",
    ]
    assert "술꾼들" not in names
    assert "목동" not in names
    assert "우편국장" not in names
    assert "스태플턴" in names and "스태플턴 양" in names
    assert {relationship.label for relationship in normalized_graph.relationships} == {"남매", "가족", "언급"}

    reminders = src.get_reminders(book_id, 30, entity_id=None)
    assert len(reminders.lines) == 1
    assert reminders.lines[0].text == "스태플턴과 스태플턴 양이 따로 언급됐다."
    assert len(reminders.lines[0].entity_ids) == 2


def test_agent_source_handles_hound_ambiguous_partial_names_conservatively():
    book_id = "29f8f4f6-1cff-4b13-95e3-5405a19f8b11"
    graph = GraphJson(
        offset=40,
        spoiler_safe=True,
        entities=[
            Entity(id="e_john", name="존", type="person", color="blue"),
            Entity(id="e_watson", name="존 H. 왓슨", type="person", color="blue"),
            Entity(id="e_clayton", name="존 클레이턴", type="person", color="blue"),
            Entity(id="e_roger_short", name="로저", type="person", color="blue"),
            Entity(id="e_roger_full", name="로저 베스커빌", type="person", color="blue"),
            Entity(id="e_selden_a", name="선든", type="person", color="blue"),
            Entity(id="e_selden_b", name="셀던", type="person", color="blue"),
        ],
        relationships=[
            Relationship(id="r1", source="e_john", target="e_watson", label="언급", tone="neutral", description="존", revision_offset=40),
            Relationship(id="r2", source="e_roger_short", target="e_selden_a", label="관련", tone="neutral", description="로저와 선든", revision_offset=40),
            Relationship(id="r3", source="e_roger_full", target="e_selden_b", label="관련", tone="neutral", description="로저 베스커빌과 셀던", revision_offset=40),
        ],
    )
    src = AgentResultSource(
        {
            (book_id, 40): {
                "graph": graph,
                "reminders": [
                    ReminderLine(text="존이 왓슨 또는 클레이턴인지 불명확하다.", entity_ids=["e_john"]),
                    ReminderLine(text="로저와 선든, 셀던이 언급됐다.", entity_ids=["e_roger_short", "e_selden_a", "e_selden_b"]),
                ],
            }
        }
    )

    normalized_graph = src.get_graph(book_id, 40, reveal_all=False)
    names = [entity.name for entity in normalized_graph.entities]

    assert "존" not in names
    assert "존 H. 왓슨" in names
    assert "존 클레이턴" in names
    assert "로저" not in names
    assert "로저 베스커빌" in names
    assert "선든" not in names
    assert "셀던" not in names
    assert "셀든" in names
    assert {relationship.label for relationship in normalized_graph.relationships} == {"관련"}

    reminders = src.get_reminders(book_id, 40, entity_id=None)
    assert len(reminders.lines) == 1
    assert reminders.lines[0].text == "로저 베스커빌와 셀든, 셀든이 언급됐다."


def test_agent_source_normalizes_hound_final_snapshot_entities():
    book_id = "29f8f4f6-1cff-4b13-95e3-5405a19f8b11"
    graph = GraphJson(
        offset=999,
        spoiler_safe=True,
        entities=[
            Entity(id="e_mortimer_a", name="모티머 박사", type="person", color="blue"),
            Entity(id="e_mortimer_b", name="제임스 모티머", type="person", color="blue"),
            Entity(id="e_stapleton_a", name="스태플턴 씨", type="person", color="blue"),
            Entity(id="e_stapleton_b", name="스탭틀턴 씨", type="person", color="blue"),
            Entity(id="e_stapleton_c", name="스탤프턴", type="person", color="blue"),
            Entity(id="e_miss_a", name="베릴", type="person", color="blue"),
            Entity(id="e_miss_b", name="스테플턴 부인", type="person", color="blue"),
            Entity(id="e_miss_c", name="스태플턴 양", type="person", color="blue"),
            Entity(id="e_frankland_a", name="프랭클랜드 씨", type="person", color="blue"),
            Entity(id="e_frankland_b", name="프랭크랜드 씨", type="person", color="blue"),
            Entity(id="e_selden_a", name="실덴", type="person", color="blue"),
            Entity(id="e_selden_b", name="션든", type="person", color="blue"),
            Entity(id="e_henry_a", name="헨리 바스커빌", type="person", color="blue"),
            Entity(id="e_henry_b", name="헨리 배스커빌 경", type="person", color="blue"),
            Entity(id="e_lyons_a", name="라이언스 부인", type="person", color="blue"),
            Entity(id="e_lyons_b", name="로라 라이언스 부인", type="person", color="blue"),
            Entity(id="e_barrymore", name="배리모어", type="person", color="blue"),
            Entity(id="e_mr_barrymore", name="배리모어 씨", type="person", color="blue"),
            Entity(id="e_mrs_barrymore", name="배리모어 부인", type="person", color="blue"),
            Entity(id="e_maid", name="처녀", type="person", color="blue"),
            Entity(id="e_prisoner", name="죄수", type="person", color="blue"),
            Entity(id="e_i", name="나", type="person", color="blue"),
            Entity(id="e_baroness", name="남작부인", type="person", color="blue"),
            Entity(id="e_convict", name="재소자", type="person", color="blue"),
            Entity(id="e_husband", name="남편", type="person", color="blue"),
            Entity(id="e_escapee", name="탈주범", type="person", color="blue"),
            Entity(id="e_unknown_a", name="미확인 인물", type="person", color="blue"),
            Entity(id="e_unknown_b", name="미지의 인물", type="person", color="blue"),
            Entity(id="e_investigator", name="수사관", type="person", color="blue"),
        ],
        relationships=[
            Relationship(id="r1", source="e_mortimer_a", target="e_henry_a", label="의뢰", tone="neutral", description="모티머와 헨리", revision_offset=999),
            Relationship(id="r2", source="e_stapleton_a", target="e_miss_a", label="관계", tone="neutral", description="스태플턴과 베릴", revision_offset=999),
            Relationship(id="r3", source="e_stapleton_b", target="e_miss_b", label="관계", tone="neutral", description="스탭틀턴과 부인", revision_offset=999),
            Relationship(id="r4", source="e_frankland_a", target="e_lyons_a", label="가족", tone="neutral", description="프랭클랜드와 라이언스", revision_offset=999),
            Relationship(id="r5", source="e_selden_a", target="e_selden_b", label="동일", tone="neutral", description="실덴과 션든", revision_offset=999),
            Relationship(id="r6", source="e_barrymore", target="e_mr_barrymore", label="애매", tone="neutral", description="배리모어 단독", revision_offset=999),
            Relationship(id="r7", source="e_maid", target="e_prisoner", label="제거", tone="neutral", description="generic", revision_offset=999),
            Relationship(id="r8", source="e_mr_barrymore", target="e_mrs_barrymore", label="부부", tone="neutral", description="개별 유지", revision_offset=999),
        ],
    )
    src = AgentResultSource(
        {
            (book_id, 999): {
                "graph": graph,
                "reminders": [
                    ReminderLine(
                        text="모티머 박사와 헨리 바스커빌, 베릴과 스탭틀턴 씨가 등장했다.",
                        entity_ids=["e_mortimer_a", "e_henry_a", "e_miss_a", "e_stapleton_b"],
                    ),
                    ReminderLine(text="처녀와 죄수가 언급됐다.", entity_ids=["e_maid", "e_prisoner"]),
                ],
            }
        }
    )

    normalized_graph = src.get_graph(book_id, 999, reveal_all=False)
    names = [entity.name for entity in normalized_graph.entities]

    assert names == [
        "제임스 모티머",
        "스태플턴",
        "스태플턴 양",
        "프랭크랜드 씨",
        "셀든",
        "헨리 배스커빌",
        "로라 라이언스 부인",
        "배리모어 씨",
        "배리모어 부인",
    ]
    assert "스태플턴" in names and "스태플턴 양" in names
    assert "배리모어" not in names
    assert all(
        name not in names
        for name in [
            "처녀",
            "죄수",
            "나",
            "남작부인",
            "재소자",
            "남편",
            "탈주범",
            "미확인 인물",
            "미지의 인물",
            "수사관",
        ]
    )
    assert {relationship.label for relationship in normalized_graph.relationships} == {"의뢰", "관계", "가족", "부부"}

    reminders = src.get_reminders(book_id, 999, entity_id=None)
    assert len(reminders.lines) == 1
    assert reminders.lines[0].text == "제임스 모티머와 헨리 배스커빌, 스태플턴 양과 스태플턴가 등장했다."


def test_agent_source_adds_entity_importance_without_changing_snapshot_contract():
    book_id = "29f8f4f6-1cff-4b13-95e3-5405a19f8b11"
    # 특정 인물명을 하드코딩해 가산점을 주지 않는다 — 관계 수/연결도/리마인드 언급
    # 횟수만으로 중요도를 매기므로, 이름과 무관하게 "중심 인물"이 높은 점수를 받는다.
    graph = GraphJson(
        offset=50,
        spoiler_safe=True,
        entities=[
            Entity(id="e_hub", name="중심 인물", type="person", color="blue"),
            Entity(id="e_a", name="인물A", type="person", color="blue"),
            Entity(id="e_b", name="인물B", type="person", color="blue"),
            Entity(id="e_c", name="인물C", type="person", color="blue"),
            Entity(id="e_minor", name="단역", type="person", color="blue"),
        ],
        relationships=[
            Relationship(id="r1", source="e_hub", target="e_a", label="동료", tone="ally", description="함께 조사", revision_offset=50),
            Relationship(id="r2", source="e_hub", target="e_b", label="조사", tone="neutral", description="사건 의뢰", revision_offset=50),
            Relationship(id="r3", source="e_hub", target="e_c", label="동행", tone="ally", description="동행", revision_offset=50),
            Relationship(id="r4", source="e_minor", target="e_a", label="언급", tone="neutral", description="짧은 언급", revision_offset=50),
        ],
    )
    src = AgentResultSource(
        {
            (book_id, 50): {
                "graph": graph,
                "reminders": [
                    ReminderLine(text="중심 인물이 사건을 정리했다.", entity_ids=["e_hub"]),
                    ReminderLine(text="중심 인물이 단서를 모았다.", entity_ids=["e_hub"]),
                    ReminderLine(text="중심 인물이 결론을 내렸다.", entity_ids=["e_hub"]),
                ],
            }
        }
    )

    normalized_graph = src.get_graph(book_id, 50, reveal_all=False)
    by_name = {entity.name: entity for entity in normalized_graph.entities}

    assert by_name["중심 인물"].importance_score == 5
    assert by_name["중심 인물"].importance_level == "major"
    assert by_name["단역"].importance_score < 4
    assert by_name["단역"].importance_level == "minor"
    assert by_name["단역"].id == "e_minor"


def test_agent_source_summarizes_relationships_for_story_graph():
    book_id = "29f8f4f6-1cff-4b13-95e3-5405a19f8b11"
    graph = GraphJson(
        offset=70,
        spoiler_safe=True,
        entities=[
            Entity(id="e_holmes", name="셜록 홈즈", type="person", color="blue"),
            Entity(id="e_watson", name="존 H. 왓슨", type="person", color="blue"),
            Entity(id="e_henry", name="헨리 배스커빌", type="person", color="blue"),
        ],
        relationships=[
            Relationship(id="r1", source="e_holmes", target="e_watson", label="동료", tone="ally", description="홈즈와 왓슨은 함께 조사한다.", revision_offset=60),
            Relationship(id="r2", source="e_watson", target="e_holmes", label="신뢰", tone="ally", description="왓슨은 홈즈를 신뢰한다.", revision_offset=65),
            Relationship(id="r3", source="e_holmes", target="e_henry", label="의뢰", tone="neutral", description="헨리의 사건을 조사한다.", revision_offset=70),
            Relationship(id="r4", source="e_holmes", target="e_henry", label="조사", tone="neutral", description="홈즈가 단서를 조사한다.", revision_offset=70),
        ],
    )
    src = AgentResultSource(
        {
            (book_id, 70): {
                "graph": graph,
                "reminders": [
                    ReminderLine(text="홈즈와 왓슨이 헨리 사건을 조사한다.", entity_ids=["e_holmes", "e_watson", "e_henry"])
                ],
            }
        }
    )

    normalized_graph = src.get_graph(book_id, 70, reveal_all=False)

    # 왓슨-헨리는 원본 relations도, 구조화된 사건도 없다 — 리마인더 공동 언급만으로는
    # 더 이상 관계를 안 만드니 아예 생기지 않는다. 홈즈-왓슨, 홈즈-헨리는 원본
    # relations가 있으므로 그대로 남는다.
    assert len(normalized_graph.relationships) == 2
    assert not any(
        {relationship.source, relationship.target} == {"e_watson", "e_henry"}
        for relationship in normalized_graph.relationships
    )
    holmes_henry = next(
        relationship
        for relationship in normalized_graph.relationships
        if {relationship.source, relationship.target} == {"e_holmes", "e_henry"}
    )
    # 원본 relations("의뢰"/"조사")가 있으므로 제네릭 role_pair_label로 덮이지 않고,
    # 서로 다른 원본 라벨 두 개는 시간순으로 "의뢰 → 조사"처럼 같이 노출된다(관계가
    # 어떻게 시작해서 어떻게 이어졌는지 정보를 보존하기 위함 — 둘 중 하나만 임의로
    # 골라서 다른 쪽 정보를 버리지 않는다).
    assert holmes_henry.display_label == "의뢰 → 조사"
    assert holmes_henry.has_direct_evidence is True
    assert holmes_henry.relationship_summary
    assert holmes_henry.directionality == "directed"
    assert holmes_henry.relation_importance_level == "major"
    assert holmes_henry.is_new_at_current_position
    assert "헨리의 사건" in holmes_henry.detail
