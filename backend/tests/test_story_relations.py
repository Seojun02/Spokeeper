from backend.app.content_source import AgentResultSource
from backend.app.precompute import _remap_position_value_to_global_index
from backend.app.schemas import Entity, GraphJson, Relationship, ReminderLine
from agents.build_agent import merge_events


BOOK_ID = "29f8f4f6-1cff-4b13-95e3-5405a19f8b11"


def _entity(entity_id: str, name: str) -> Entity:
    return Entity(id=entity_id, name=name, type="person", color="blue")


def _relationship(
    relationship_id: str,
    source: str,
    target: str,
    label: str,
    description: str,
    revision_offset: int = 100,
    **extra,
) -> Relationship:
    return Relationship(
        id=relationship_id,
        source=source,
        target=target,
        label=label,
        tone="neutral",
        description=description,
        revision_offset=revision_offset,
        **extra,
    )


def _source(graph: GraphJson, reminders: list[ReminderLine], boundary: int = 100) -> AgentResultSource:
    return AgentResultSource({(BOOK_ID, boundary): {"graph": graph, "reminders": reminders}})


def test_reminder_co_mention_no_longer_fabricates_relations():
    """리마인더 한 줄에 같이 언급됐다는 것만으로는 더 이상 관계를 만들지 않는다 —
    문장 안에서 누가 조사자이고 누가 용의자/조력자인지 구분 못 한 채 언급된 사람
    전원을 대칭적으로 묶던 예전 방식은 실제로는 없는 관계(예: 이미 죽은 피해자가
    "조사자"로 엮이는 등)를 만드는 버그가 있어 제거했다. 원본 relations에 실제로
    있는 쌍(홈즈-왓슨)만 그대로 노출된다.
    """
    graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[
            _entity("e_holmes", "셜록 홈즈"),
            _entity("e_watson", "존 H. 왓슨"),
            _entity("e_stapleton", "스태플턴"),
        ],
        relationships=[
            _relationship("r1", "e_holmes", "e_watson", "동료", "홈즈와 왓슨은 함께 움직인다."),
        ],
    )
    reminders = [
        ReminderLine(
            text="셜록 홈즈와 존 H. 왓슨은 스태플턴을 조사하고 추적했다.",
            entity_ids=["e_holmes", "e_watson", "e_stapleton"],
        )
    ]

    normalized_graph = _source(graph, reminders).get_graph(BOOK_ID, 100, reveal_all=False)
    pairs = {frozenset((r.source, r.target)) for r in normalized_graph.relationships}

    # 홈즈-스태플턴, 왓슨-스태플턴은 원본 관계도 구조화된 사건도 없으니 아예 안 생긴다.
    assert frozenset(("e_holmes", "e_stapleton")) not in pairs
    assert frozenset(("e_watson", "e_stapleton")) not in pairs
    # 홈즈-왓슨은 원본 관계가 있으므로 그대로 노출되고, 라벨도 원본("동료")을 유지한다.
    holmes_watson = next(r for r in normalized_graph.relationships if frozenset((r.source, r.target)) == frozenset(("e_holmes", "e_watson")))
    assert holmes_watson.has_direct_evidence is True
    assert holmes_watson.display_label == "동료"


def test_summary_preserves_multiple_relations_in_detail_and_related_events():
    graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[
            _entity("e_holmes", "셜록 홈즈"),
            _entity("e_stapleton", "스태플턴"),
        ],
        relationships=[
            _relationship("r1", "e_holmes", "e_stapleton", "의심", "홈즈는 스태플턴을 의심한다."),
            _relationship("r2", "e_holmes", "e_stapleton", "추적", "홈즈는 스태플턴의 행적을 추적한다."),
        ],
    )
    normalized_graph = _source(graph, []).get_graph(BOOK_ID, 100, reveal_all=False)

    assert len(normalized_graph.relationships) == 1
    relationship = normalized_graph.relationships[0]
    assert "의심한다" in relationship.detail
    assert "행적을 추적" in relationship.detail
    # 두 원본 relations의 텍스트("의심"/"추적")가 investigation 카테고리로 인식돼
    # _enrich_existing_relationship이 이벤트 정보를 채운다.
    assert relationship.related_events


def test_future_story_relationship_is_not_exposed_before_boundary():
    graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[
            _entity("e_holmes", "셜록 홈즈"),
            _entity("e_stapleton", "스태플턴"),
        ],
        relationships=[
            _relationship(
                "r_future",
                "e_holmes",
                "e_stapleton",
                "폭로",
                "미래 위치에서 밝혀지는 관계다.",
                revision_offset=200,
                first_seen_global_index=200,
                is_story_relation=True,
                relation_category="investigation",
            ),
        ],
    )

    normalized_graph = _source(graph, []).get_graph(BOOK_ID, 100, reveal_all=False)

    assert normalized_graph.relationships == []


def test_alias_and_generic_filter_apply_even_when_relations_lack_direct_evidence():
    """별칭 정규화("홈즈"→"셜록 홈즈")와 일반명사 필터("의사" 제외)는 관계 유무와
    무관하게 인물(entity) 목록에 그대로 적용된다. 리마인더 공동 언급만으로는 더 이상
    관계를 안 만드니, 이 케이스는 관계 없이 인물 목록만 채워진다.
    """
    graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[
            _entity("e_holmes_alias", "홈즈"),
            _entity("e_watson", "왓슨"),
            _entity("e_stapleton", "스태플턴"),
            _entity("e_doctor", "의사"),
        ],
        relationships=[],
    )
    reminders = [
        ReminderLine(
            text="홈즈와 왓슨은 의사를 지나 스태플턴을 조사했다.",
            entity_ids=["e_holmes_alias", "e_watson", "e_doctor", "e_stapleton"],
        )
    ]

    normalized_graph = _source(graph, reminders).get_graph(BOOK_ID, 100, reveal_all=False)
    names = {entity.name for entity in normalized_graph.entities}

    assert "셜록 홈즈" in names
    assert "존 H. 왓슨" in names
    assert "의사" not in names
    assert normalized_graph.relationships == []


def test_structured_event_creates_perpetrator_victim_relation():
    graph = GraphJson(
        offset=300,
        spoiler_safe=True,
        entities=[
            _entity("e_stapleton", "스태플턴"),
            _entity("e_charles", "찰스 배스커빌 경"),
        ],
        relationships=[],
        events=[
            {
                "event_id": "ev_charles_death",
                "event_name": "찰스 배스커빌 사망",
                "event_summary": "스태플턴이 찰스 배스커빌 경의 죽음에 관여했다.",
                "participants": [
                    {"character_name": "스태플턴", "role": "perpetrator", "confidence": 0.9},
                    {"character_name": "찰스 배스커빌 경", "role": "victim", "confidence": 0.9},
                ],
                "evidence": "스태플턴의 범행이 드러났다.",
                "first_seen_global_index": 280,
                "last_seen_global_index": 300,
            }
        ],
    )

    normalized_graph = _source(graph, [], boundary=300).get_graph(BOOK_ID, 300, reveal_all=False)
    relationship = normalized_graph.relationships[0]

    assert relationship.source == "e_stapleton"
    assert relationship.target == "e_charles"
    assert relationship.relation_category == "crime"
    assert relationship.relation_role == "crime"
    assert relationship.is_story_relation
    assert relationship.related_events[0]["event_id"] == "ev_charles_death"


def test_structured_event_creates_co_accomplice_relation():
    """가해자와 공범처럼 "같은 사건에서 같은 편"인 역할끼리는 _add_role_pairs의
    교차 역할 규칙(가해자→피해자 등)으로는 관계가 안 만들어진다. 특정 장르 하나에
    "공범" 라벨만 땜질하는 게 아니라 역할 taxonomy 전체에 적용되는 _add_co_role_pairs가
    이걸 "공범" 관계로 만들어주는지 확인한다.
    """
    graph = GraphJson(
        offset=300,
        spoiler_safe=True,
        entities=[
            _entity("e_segyeong", "오세경"),
            _entity("e_kihwan", "최기환"),
        ],
        relationships=[],
        events=[
            {
                "event_id": "ev_conspiracy",
                "event_name": "은폐 공모",
                "event_summary": "오세경과 최기환이 함께 사고를 은폐했다.",
                "participants": [
                    {"character_name": "오세경", "role": "perpetrator", "confidence": 0.9},
                    {"character_name": "최기환", "role": "accomplice", "confidence": 0.9},
                ],
                "evidence": "최기환이 공모를 자백했다.",
                "first_seen_global_index": 280,
                "last_seen_global_index": 300,
            }
        ],
    )

    normalized_graph = _source(graph, [], boundary=300).get_graph(BOOK_ID, 300, reveal_all=False)
    relationships = normalized_graph.relationships
    accomplice = next(r for r in relationships if {r.source, r.target} == {"e_segyeong", "e_kihwan"})

    assert accomplice.relation_role == "accomplice"
    assert accomplice.display_label == "공범"
    assert accomplice.directionality == "undirected"
    assert accomplice.has_direct_evidence is True
    # 구조화된 사건에서 자동 생성된 관계는 태생적으로 "행동 기반"이라 relation_kind가
    # 항상 action이다 — 원본 BuildAgent 관계처럼 LLM이 personal/action을 새로 판단할
    # 필요가 없다(역할 자체가 이미 행동을 뜻하므로).
    assert accomplice.relation_kind == "action"


def test_original_relation_kind_is_preserved_over_synthetic_relations():
    """원본(BuildAgent) 관계에 이미 relation_kind="personal"이 있으면, 같은 쌍에
    합성 관계가 섞여도 원본 판단이 우선한다(카테고리 키워드 추측보다 신뢰도가 높음)."""
    graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[
            _entity("e_a", "김민준"),
            _entity("e_b", "이서연"),
        ],
        relationships=[
            _relationship(
                "r1",
                "e_a",
                "e_b",
                "연인",
                "민준과 서연은 연인 사이다.",
                relation_kind="personal",
            ),
        ],
    )
    reminders = [
        ReminderLine(text="민준과 서연은 함께 사건을 조사했다.", entity_ids=["e_a", "e_b"]),
    ]

    normalized_graph = _source(graph, reminders).get_graph(BOOK_ID, 100, reveal_all=False)
    relationship = next(
        r for r in normalized_graph.relationships if {r.source, r.target} == {"e_a", "e_b"}
    )

    assert relationship.relation_kind == "personal"


def test_structured_event_creates_investigator_perpetrator_relation():
    """조사 관계는 "진범/공범"처럼 확정된 상대를 조사하는 경우만 만든다."""
    graph = GraphJson(
        offset=300,
        spoiler_safe=True,
        entities=[
            _entity("e_holmes", "셜록 홈즈"),
            _entity("e_stapleton", "스태플턴"),
        ],
        relationships=[],
        events=[
            {
                "event_id": "ev_investigation",
                "event_name": "스태플턴 조사",
                "event_summary": "홈즈가 진범 스태플턴을 추적했다.",
                "participants": [
                    {"character_name": "셜록 홈즈", "role": "investigator", "confidence": 0.9},
                    {"character_name": "스태플턴", "role": "perpetrator", "confidence": 0.8},
                ],
                "evidence": "홈즈가 스태플턴을 추적했다.",
                "first_seen_global_index": 300,
                "last_seen_global_index": 300,
            }
        ],
    )

    normalized_graph = _source(graph, [], boundary=300).get_graph(BOOK_ID, 300, reveal_all=False)
    relationships = normalized_graph.relationships
    investigation = next(r for r in relationships if {r.source, r.target} == {"e_holmes", "e_stapleton"})

    assert investigation.relation_category == "investigation"
    assert investigation.relation_role == "investigation"
    assert investigation.display_label == "수사관 → 범인"


def test_suspect_role_alone_does_not_create_investigation_relation():
    """"용의자(suspect)"는 아직 확정 안 된 의심 단계라, investigator-suspect 쌍만으로는
    관계를 만들지 않는다 — "의심하는 단계"는 조사 관계로 안 친다는 요구사항."""
    graph = GraphJson(
        offset=300,
        spoiler_safe=True,
        entities=[
            _entity("e_holmes", "셜록 홈즈"),
            _entity("e_stapleton", "스태플턴"),
        ],
        relationships=[],
        events=[
            {
                "event_id": "ev_suspicion",
                "event_name": "스태플턴 의심",
                "event_summary": "홈즈는 스태플턴을 의심스러운 인물로 보았다.",
                "participants": [
                    {"character_name": "셜록 홈즈", "role": "investigator", "confidence": 0.9},
                    {"character_name": "스태플턴", "role": "suspect", "confidence": 0.8},
                ],
                "evidence": "홈즈는 스태플턴을 의심했다.",
                "first_seen_global_index": 300,
                "last_seen_global_index": 300,
            }
        ],
    )

    normalized_graph = _source(graph, [], boundary=300).get_graph(BOOK_ID, 300, reveal_all=False)

    assert normalized_graph.relationships == []


def test_structured_event_creates_deception_relation():
    graph = GraphJson(
        offset=300,
        spoiler_safe=True,
        entities=[
            _entity("e_stapleton", "스태플턴"),
            _entity("e_lyons", "로라 라이언스 부인"),
        ],
        relationships=[],
        events=[
            {
                "event_id": "ev_lyons_deceived",
                "event_name": "라이언스 부인 기만",
                "event_summary": "스태플턴은 로라 라이언스 부인을 속였다.",
                "participants": [
                    {"character_name": "스태플턴", "role": "deceiver", "confidence": 0.9},
                    {"character_name": "로라 라이언스 부인", "role": "deceived", "confidence": 0.9},
                ],
                "evidence": "라이언스 부인이 기만당한 사실이 드러났다.",
                "first_seen_global_index": 300,
                "last_seen_global_index": 300,
            }
        ],
    )

    normalized_graph = _source(graph, [], boundary=300).get_graph(BOOK_ID, 300, reveal_all=False)
    relationship = normalized_graph.relationships[0]

    assert relationship.source == "e_stapleton"
    assert relationship.target == "e_lyons"
    assert relationship.relation_category == "deception"
    assert relationship.relation_role == "deception"


def test_merge_events_updates_existing_event_instead_of_duplicating():
    merged = merge_events(
        [
            {
                "event_name": "찰스 배스커빌 사망",
                "event_summary": "찰스 배스커빌 경이 사망했다.",
                "participants": [{"character_name": "찰스 배스커빌 경", "role": "victim"}],
                "first_seen_chunk_offset": 10,
                "last_seen_chunk_offset": 10,
            },
            {
                "event_name": "찰스 배스커빌 사망",
                "event_summary": "찰스 배스커빌 경의 사망 사건이 다시 언급된다.",
                "participants": [
                    {"character_name": "찰스 배스커빌 경", "role": "victim"},
                    {"character_name": "스태플턴", "role": "suspect"},
                ],
                "first_seen_chunk_offset": 20,
                "last_seen_chunk_offset": 20,
            },
        ]
    )

    assert len(merged) == 1
    assert merged[0]["first_seen_chunk_offset"] == 10
    assert merged[0]["last_seen_chunk_offset"] == 20
    assert {participant["role"] for participant in merged[0]["participants"]} == {"victim", "suspect"}


def test_structured_future_event_is_blocked_by_boundary():
    graph = GraphJson(
        offset=300,
        spoiler_safe=True,
        entities=[
            _entity("e_stapleton", "스태플턴"),
            _entity("e_charles", "찰스 배스커빌 경"),
        ],
        relationships=[],
        events=[
            {
                "event_id": "ev_future",
                "event_name": "미래 폭로",
                "event_summary": "아직 읽지 않은 위치에서 밝혀지는 사건이다.",
                "participants": [
                    {"character_name": "스태플턴", "role": "perpetrator"},
                    {"character_name": "찰스 배스커빌 경", "role": "victim"},
                ],
                "first_seen_global_index": 500,
                "last_seen_global_index": 500,
            }
        ],
    )

    normalized_graph = _source(graph, [], boundary=300).get_graph(BOOK_ID, 300, reveal_all=False)

    assert normalized_graph.relationships == []


def test_structured_event_alias_and_generic_filter_before_relation_generation():
    graph = GraphJson(
        offset=300,
        spoiler_safe=True,
        entities=[
            _entity("e_holmes", "홈즈"),
            _entity("e_stapleton", "스태플턴"),
            _entity("e_doctor", "의사"),
        ],
        relationships=[],
        events=[
            {
                "event_id": "ev_alias",
                "event_name": "진범 검거",
                "event_summary": "홈즈가 의사를 지나 진범 스태플턴을 검거했다.",
                "participants": [
                    {"character_name": "홈즈", "role": "investigator"},
                    {"character_name": "의사", "role": "witness"},
                    {"character_name": "스태플턴", "role": "perpetrator"},
                ],
                "first_seen_global_index": 300,
                "last_seen_global_index": 300,
            }
        ],
    )

    normalized_graph = _source(graph, [], boundary=300).get_graph(BOOK_ID, 300, reveal_all=False)
    names = {entity.name for entity in normalized_graph.entities}
    relationship = normalized_graph.relationships[0]

    assert "셜록 홈즈" in names
    assert "의사" not in names
    assert relationship.source == "e_holmes"
    assert relationship.target == "e_stapleton"
    assert relationship.relation_category == "investigation"


def test_precompute_can_map_event_chunk_offsets_to_global_index():
    mapping = {10: 101, 20: 205}

    assert _remap_position_value_to_global_index(10, mapping) == 101
    assert _remap_position_value_to_global_index(20, mapping) == 205
