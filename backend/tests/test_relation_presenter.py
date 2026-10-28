from backend.app.relation_presenter import apply_relationship_presentation
from backend.app.schemas import Entity, GraphJson, Relationship


def _entity(entity_id: str, name: str) -> Entity:
    return Entity(id=entity_id, name=name, type="person", color="blue")


def test_presenter_never_leaks_hardcoded_baskerville_text_into_unrelated_book():
    """실제로 재현됐던 사고: 심청전(홈즈와 전혀 무관한 책)의 "옥황상제-용왕" 같은
    work/의뢰 계열 관계에 셜록 홈즈용 하드코딩 문장("찰스 경의 죽음과 가문의
    저주")이 그대로 노출됐다. event_summary가 없어도 하드코딩된 특정 책 내용이
    나오면 안 되고, 범용 카테고리 문장으로만 귀결돼야 한다."""
    graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[_entity("e_a", "옥황상제"), _entity("e_b", "인당수 용왕")],
        relationships=[
            Relationship(
                id="r1",
                source="e_a",
                target="e_b",
                label="명령자-수령자",
                tone="neutral",
                description="옥황상제의 명령을 받은 용왕",
                revision_offset=100,
                relation_category="work",
                relation_role="work",
            )
        ],
    )

    relationship = apply_relationship_presentation(graph).relationships[0]

    assert "찰스" not in relationship.relationship_summary
    assert "배스커빌" not in relationship.relationship_summary
    assert "저주" not in relationship.relationship_summary


def test_presenter_builds_korean_role_pair_from_structured_story_relation():
    graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[
            _entity("e_stapleton", "스태플턴"),
            _entity("e_charles", "찰스 배스커빌 경"),
        ],
        relationships=[
            Relationship(
                id="r1",
                source="e_stapleton",
                target="e_charles",
                label="사건",
                tone="tense",
                description="원문 문장입니다. " * 50,
                revision_offset=100,
                relation_category="crime",
                relation_role="crime",
                is_story_relation=True,
                label_is_generic=True,
                event_name="찰스 배스커빌 사망 사건",
                event_summary="스태플턴은 찰스 경의 죽음에 관여했다.",
                related_events=[
                    {
                        "event_name": "찰스 배스커빌 사망 사건",
                        "event_summary": "스태플턴은 찰스 경의 죽음에 관여했다.",
                        "evidence": "긴 원문 근거입니다. " * 40,
                    }
                ],
            )
        ],
    )

    presented = apply_relationship_presentation(graph)
    relationship = presented.relationships[0]

    assert relationship.role_pair_label == "가해자 → 피해자"
    assert relationship.display_label == "가해자 → 피해자"
    assert relationship.event_name == "찰스 배스커빌 사망 사건"
    assert "원문 문장입니다" not in relationship.relationship_summary
    assert "스태플턴" in relationship.relationship_summary
    assert len(relationship.evidence) == 2
    assert len(relationship.evidence[0]) <= 220
    assert "가해와 피해 맥락" not in relationship.relationship_summary
    assert "사건 관련 인물" not in relationship.relationship_summary


def test_presenter_separates_evidence_from_summary():
    raw_evidence = "모티머 박사가 소리쳤다. 그는 안경을 밀어올리며 길게 설명했다. " * 20
    graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[_entity("e_mortimer", "제임스 모티머"), _entity("e_holmes", "셜록 홈즈")],
        relationships=[
            Relationship(
                id="r1",
                source="e_mortimer",
                target="e_holmes",
                label="의뢰",
                tone="neutral",
                description=raw_evidence,
                revision_offset=100,
                relation_category="work",
                detail=raw_evidence,
            )
        ],
    )

    relationship = apply_relationship_presentation(graph).relationships[0]

    assert relationship.relationship_summary
    assert raw_evidence not in relationship.relationship_summary
    assert relationship.evidence
    assert "모티머 박사" in relationship.evidence[0]


def test_presenter_creates_short_legacy_summary():
    graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[_entity("e_watson", "존 H. 왓슨"), _entity("e_henry", "헨리 배스커빌")],
        relationships=[
            Relationship(
                id="r1",
                source="e_watson",
                target="e_henry",
                label="동행",
                tone="ally",
                description="왓슨은 헨리와 동행했다.",
                revision_offset=100,
                relation_category="ally",
            )
        ],
    )

    relationship = apply_relationship_presentation(graph).relationships[0]

    assert relationship.role_pair_label == "조력자 → 동료"
    assert relationship.display_label == "동행"
    assert relationship.relationship_summary
    assert len(relationship.relationship_summary) < 180


def test_presenter_falls_back_to_category_label_without_hardcoded_names():
    """특정 작품의 인물명을 하드코딩해서 "주치의/환자" 같은 세부 역할을 판단하지
    않는다 — 다른 소설에도 그대로 적용되도록, 이름과 무관하게 relation_category
    기준의 일반 역할 라벨(CATEGORY_LABELS)로 귀결되는지 확인한다.
    """
    graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[_entity("e_a", "김민준"), _entity("e_b", "이서연")],
        relationships=[
            Relationship(
                id="r1",
                source="e_a",
                target="e_b",
                label="증언",
                tone="neutral",
                description="민준은 서연의 주치의였고 그의 죽음을 이상하게 여겼다.",
                revision_offset=100,
                relation_category="mystery",
                event_name="사망 사건",
                event_summary="민준은 서연의 주치의였고 그의 죽음을 이상하게 여겼다.",
            )
        ],
    )

    relationship = apply_relationship_presentation(graph).relationships[0]

    assert relationship.role_pair_label == "단서 제공자 → 관련 인물"
    assert relationship.relationship_summary


def test_presenter_uses_event_text_not_hardcoded_sentence_for_work_category():
    """예전엔 role_pair_label이 "의뢰인 → 조사자"일 때 셜록 홈즈 테스트북 문장이
    그대로 하드코딩돼 있어서, 다른 책(예: 심청전)의 관계에도 "찰스 경의 죽음과
    가문의 저주" 같은 엉뚱한 문장이 그대로 노출되는 환각 버그가 있었다. 이제는
    실제 event_summary 텍스트(있으면) 또는 카테고리 기반 범용 문장만 쓴다."""
    graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[_entity("e_mortimer", "제임스 모티머"), _entity("e_holmes", "셜록 홈즈")],
        relationships=[
            Relationship(
                id="r1",
                source="e_mortimer",
                target="e_holmes",
                label="의뢰",
                tone="neutral",
                description="모티머는 홈즈에게 조사를 부탁했다.",
                revision_offset=100,
                relation_category="work",
                relation_role="work",
                event_name="배스커빌 사건 의뢰",
                event_summary="모티머는 홈즈에게 사건 조사를 의뢰했다.",
            )
        ],
    )

    relationship = apply_relationship_presentation(graph).relationships[0]

    assert relationship.role_pair_label == "의뢰인 → 조사자"
    # 하드코딩된 "찰스 경의 죽음과 가문의 저주" 문장이 아니라 실제 event_summary가 쓰인다.
    assert "찰스" not in relationship.relationship_summary
    assert "홈즈에게" in relationship.relationship_summary


def test_presenter_falls_back_to_family_category_without_hardcoded_names():
    """마찬가지로 "삼촌/상속인" 같은 세부 역할도 이름 하드코딩 없이, category
    기준 일반 라벨(가족/가족)로 귀결되는지 확인한다."""
    graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[_entity("e_a", "김민준"), _entity("e_b", "이서연")],
        relationships=[
            Relationship(
                id="r1",
                source="e_a",
                target="e_b",
                label="상속",
                tone="neutral",
                description="민준이 사망한 뒤 서연이 재산과 작위를 상속했다.",
                revision_offset=100,
                relation_category="family",
                event_name="상속",
                event_summary="민준이 사망한 뒤 서연이 재산과 작위를 상속했다.",
            )
        ],
    )

    relationship = apply_relationship_presentation(graph).relationships[0]

    # 둘 다 같은 역할("가족")을 공유하는 대칭 쌍이라 화살표 없이 한 번만 표시한다.
    assert relationship.role_pair_label == "가족"
    assert "재산과 작위" in relationship.relationship_summary


def test_presenter_avoids_mechanical_labels_for_same_category_different_contexts():
    investigation_graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[_entity("e_holmes", "셜록 홈즈"), _entity("e_stapleton", "스태플턴")],
        relationships=[
            Relationship(
                id="r1",
                source="e_holmes",
                target="e_stapleton",
                label="조사",
                tone="neutral",
                description="홈즈는 스태플턴을 추적했다.",
                revision_offset=100,
                relation_category="investigation",
                relation_role="investigation",
                event_name="스태플턴 추적",
            )
        ],
    )
    protection_graph = GraphJson(
        offset=100,
        spoiler_safe=True,
        entities=[_entity("e_watson", "존 H. 왓슨"), _entity("e_henry", "헨리 배스커빌")],
        relationships=[
            Relationship(
                id="r2",
                source="e_watson",
                target="e_henry",
                label="보호",
                tone="ally",
                description="왓슨은 헨리를 보호하며 동행했다.",
                revision_offset=100,
                relation_category="protection",
                relation_role="protection",
                event_name="헨리 보호",
            )
        ],
    )

    investigation = apply_relationship_presentation(investigation_graph).relationships[0]
    protection = apply_relationship_presentation(protection_graph).relationships[0]

    assert investigation.role_pair_label == "수사관 → 범인"
    assert protection.role_pair_label == "보호자 → 보호 대상"
    assert investigation.relationship_summary != protection.relationship_summary
    forbidden = ("조사 대상", "사건 관련 인물", "조사와 의심의 맥락")
    assert not any(phrase in investigation.relationship_summary for phrase in forbidden)
    assert not any(phrase in protection.relationship_summary for phrase in forbidden)
