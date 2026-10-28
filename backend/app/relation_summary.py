from __future__ import annotations

from collections import Counter, defaultdict

from .schemas import Entity, GraphJson, Relationship


_CATEGORY_HINTS = {
    "ally": ("친구", "동료", "조력", "신뢰", "협력", "동행", "도움"),
    "family": ("가족", "부인", "남편", "아내", "후계자", "가문", "형제", "남매", "부부", "딸", "아들"),
    "conflict": ("갈등", "의심", "적대", "추적", "살해", "위협", "공격", "범인", "고발"),
    "crime": ("살인", "살해", "죽", "사망", "시체", "범인", "피해자", "독살", "공격"),
    "investigation": ("조사", "수사", "추적", "의심", "용의", "단서", "탐문", "밝히"),
    "deception": ("속", "기만", "위장", "거짓", "은폐", "숨김", "비밀", "협박", "함정"),
    "protection": ("보호", "도움", "돕", "동행", "구출", "지키", "경호"),
    "romance": ("사랑", "연인", "약혼", "질투", "청혼", "결혼"),
    "work": ("의뢰", "고용", "조사", "업무", "주치의", "집사", "하인", "고용인"),
    "mystery": ("정체", "비밀", "단서", "미스터리", "수수께끼", "숨김", "은폐"),
}

_CATEGORY_PRIORITY = (
    "crime",
    "investigation",
    "deception",
    "protection",
    "family",
    "romance",
    "conflict",
    "work",
    "ally",
    "mystery",
    "neutral",
)
_DIRECTED_HINTS = ("의뢰", "고용", "추적", "살해", "위협", "공격", "고발", "조사", "도움", "보냄", "지시", "속임", "보호")
_STORY_CATEGORIES = {"crime", "investigation", "deception", "protection"}

# 상호적(대칭) 관계 — 두 사람을 서로 바꿔 불러도 같은 말인 경우만 undirected로 둔다.
# "아버지/어머니/아들/딸/삼촌/변호사/관리인/수사관"처럼 한쪽에서 다른 쪽으로 향하는
# 대부분의 관계 단어는 방향이 있는 게 정상이라, 화이트리스트(대칭)만 undirected로
# 판정하고 나머지는 기본값을 directed로 둔다 — "누가 누구의 X인지" 화살표 없이는
# 헷갈리는 관계(부모/자식, 직함 등)가 undirected로 잘못 표시되는 문제를 막기 위함.
_SYMMETRIC_LABEL_HINTS = (
    "부부",
    "형제",
    "자매",
    "남매",
    "친구",
    "동료",
    "연인",
    "동업자",
    "공모자",
    "공범",
    "동창",
    "동기",
    "라이벌",
    "맞수",
    "부모자식",
    "공동 피해자",
    "공동 목격자",
    "공동 용의자",
)


def _relation_text(relationship: Relationship) -> str:
    return " ".join(
        part
        for part in [
            relationship.label,
            relationship.description,
            relationship.display_label or "",
            relationship.detail or "",
        ]
        if part
    )


def _category_for(relationships: list[Relationship]) -> str:
    # 라벨과 마찬가지로, 원본(비-합성) 관계의 텍스트를 우선 근거로 카테고리를
    # 판단한다 — 합성 관계의 category는 이벤트 공동 참여만으로 자동 매겨진
    # 값이라, 같은 쌍에 원본 관계가 있으면 그쪽 문맥이 더 정확하다.
    non_story = [relationship for relationship in relationships if not relationship.is_story_relation]
    text = " ".join(_relation_text(relationship) for relationship in (non_story or relationships))
    counts = {
        category: sum(1 for hint in hints if hint in text)
        for category, hints in _CATEGORY_HINTS.items()
    }
    if any(counts.values()):
        return max(_CATEGORY_PRIORITY, key=lambda category: (counts.get(category, 0), -_CATEGORY_PRIORITY.index(category)))

    story_categories = [
        relationship.relation_category
        for relationship in relationships
        if relationship.is_story_relation and relationship.relation_category in _STORY_CATEGORIES
    ]
    if story_categories:
        return max(
            _CATEGORY_PRIORITY,
            key=lambda category: (story_categories.count(category), -_CATEGORY_PRIORITY.index(category)),
        )

    return "neutral"


_SYMMETRIC_RELATION_ROLES = {"accomplice", "co_victim", "co_witness", "co_suspect"}


def _directionality_for(relationships: list[Relationship], category: str) -> str:
    # relation_role 자체가 "같은 역할을 공유하는 두 사람"(공범, 공동 목격자 등)이면
    # category가 crime/investigation처럼 보통 방향 있는 카테고리여도 대칭 관계다.
    # 이 시점엔 role_pair_label("공범" 등)이 아직 apply_relationship_presentation에서
    # 안 붙어있어 라벨 기반 판정(아래)이 못 잡으므로 relation_role로 먼저 확인한다.
    if any(relationship.relation_role in _SYMMETRIC_RELATION_ROLES for relationship in relationships):
        return "undirected"
    if category in {"crime", "investigation", "deception", "protection"}:
        return "directed"

    labels = [
        (relationship.display_label or relationship.label or "").strip()
        for relationship in relationships
        if (relationship.display_label or relationship.label or "").strip()
    ]
    if labels and any(hint in label for label in labels for hint in _SYMMETRIC_LABEL_HINTS):
        return "undirected"
    if labels:
        # 라벨이 있는데 위 대칭 목록에 없으면(예: "아버지", "관리인", "고문 변호사")
        # 기본적으로 방향이 있는 관계로 본다.
        return "directed"

    text = " ".join(_relation_text(relationship) for relationship in relationships)
    if category in {"family", "romance", "ally"}:
        return "undirected"
    if any(hint in text for hint in _DIRECTED_HINTS):
        return "directed"
    return "undirected"


def _display_label_for(relationships: list[Relationship], category: str) -> str:
    # BuildAgent가 근거 기반으로 뽑은 원본 라벨(예: "협박자")이 있으면 항상 그걸
    # 우선한다 — 합성(story) 관계는 이벤트 공동 참여 등에서 자동 생성된 제네릭
    # 라벨(조사/보호 등)이라 정보량이 적다. 같은 인물 쌍에 합성 관계가 같이 있다는
    # 이유로 더 구체적인 원본 라벨이 가려지면 안 된다.
    #
    # 원본 라벨이 여러 개면(예: "초면" → 나중에 "협력자") 단순히 더 자주 나온 쪽이나
    # 가장 먼저 나온 쪽을 무조건 고르지 않는다 — "가장 자주"는 관계가 깊어진 결과를
    # 놓치고("초면"만 남음), "가장 최근"만 쓰면 반대로 여러 인물 쌍이 전부 흔한
    # 후반부 라벨(예: "협력자")로 수렴해서 서로 구분이 안 되는 문제가 생긴다. 그래서
    # 시간순으로 처음과 마지막 라벨을 "초면 → 협력자"처럼 같이 보여줘서, 관계가 어떻게
    # 시작해서 어떻게 발전했는지 정보를 둘 다 보존한다.
    non_story = [
        relationship
        for relationship in relationships
        if not relationship.is_story_relation and relationship.label.strip()
    ]
    if non_story:
        ordered = sorted(non_story, key=lambda relationship: relationship.revision_offset)
        stages: list[str] = []
        for relationship in ordered:
            label = relationship.label.strip()[:12]
            if not stages or stages[-1] != label:
                stages.append(label)
        if len(stages) > 1:
            return f"{stages[0]} → {stages[-1]}"
        return stages[0]

    story_labels = [
        (relationship.display_label or relationship.label).strip()
        for relationship in relationships
        if relationship.is_story_relation and (relationship.display_label or relationship.label).strip()
    ]
    if story_labels:
        label, _ = Counter(story_labels).most_common(1)[0]
        return label[:12]
    return {
        "ally": "협력",
        "family": "가족",
        "conflict": "갈등",
        "crime": "사건",
        "investigation": "조사",
        "deception": "속임",
        "protection": "보호",
        "romance": "관계",
        "work": "업무",
        "mystery": "단서",
        "neutral": "관련",
    }[category]


def _relation_kind_for(relationships: list[Relationship]) -> str | None:
    # 원본(BuildAgent) 관계가 직접 판단한 relation_kind가 있으면 그걸 우선한다 —
    # LLM이 문맥을 보고 직접 내린 판단이라 키워드 추측보다 신뢰도가 높다. 원본에
    # 없고 합성(구조화된 사건/리마인드 조합) 관계뿐이면 그건 태생적으로 "action"이다.
    non_story_kinds = [
        relationship.relation_kind
        for relationship in relationships
        if not relationship.is_story_relation and relationship.relation_kind
    ]
    if non_story_kinds:
        return Counter(non_story_kinds).most_common(1)[0][0]
    if any(relationship.is_story_relation for relationship in relationships):
        return "action"
    return None


def _importance_for(
    relationships: list[Relationship],
    entities_by_id: dict[str, Entity],
    reminder_entity_ids: set[str],
) -> int:
    source = relationships[0].source
    target = relationships[0].target
    score = 1
    if len(relationships) >= 2:
        score += 1
    if len(relationships) >= 4:
        score += 1
    if entities_by_id.get(source) and entities_by_id[source].importance_level == "major":
        score += 1
    if entities_by_id.get(target) and entities_by_id[target].importance_level == "major":
        score += 1
    if source in reminder_entity_ids and target in reminder_entity_ids:
        score += 1
    if any((relationship.description or "").strip() for relationship in relationships):
        score += 1
    if any(relationship.is_story_relation for relationship in relationships):
        score += 2
    if any(relationship.relation_category in {"crime", "investigation", "deception"} for relationship in relationships):
        score += 1
    score = max(1, min(5, score))

    # 한 사람이 같은 사건에서 여러 명과 동시에 같은 역할 쌍을 맺으면(예: 형사 한 명이
    # 용의자 10명을 한꺼번에 심문) story_relations.py가 related_events에 fan_out을
    # 남긴다. 이 쌍의 story relation이 전부(하나도 빠짐없이) 그런 허브-스포크
    # 사건에서만 나왔다면 — 즉 이 둘만의 개별적인 사건이 따로 없다면 — major로
    # 올리지 않는다. 안 그러면 똑같은 제네릭 라벨을 단 엣지 여러 개가 전부 강조돼
    # 그래프 텍스트가 도배된다. 허브 사건 외에 개별 사건이 하나라도 있으면(예:
    # 그 형사가 이 사람만 따로 조사한 적도 있다면) 그대로 major로 남는다.
    story_relationships = [relationship for relationship in relationships if relationship.is_story_relation]
    if story_relationships and all(
        any(event.get("fan_out", 1) > 2 for event in relationship.related_events)
        for relationship in story_relationships
    ):
        score = min(score, 3)
    return score


def _pair_key(relationship: Relationship) -> tuple[str, str]:
    return tuple(sorted([relationship.source, relationship.target]))


def summarize_relationships(
    graph: GraphJson,
    *,
    current_boundary_global_index: int,
    reminder_entity_ids: list[str],
) -> GraphJson:
    grouped: dict[tuple[str, str], list[Relationship]] = defaultdict(list)
    for relationship in graph.relationships:
        first_seen = relationship.first_seen_global_index or relationship.revision_offset
        if first_seen > current_boundary_global_index:
            continue
        grouped[_pair_key(relationship)].append(relationship)

    entities_by_id = {entity.id: entity for entity in graph.entities}
    reminder_ids = set(reminder_entity_ids)
    summarized: list[Relationship] = []

    for relationships in grouped.values():
        # 원본(BuildAgent) 관계도 없고, 구조화된 사건(역할이 명확히 배정된 event)의
        # 뒷받침도 없이 "같은 문장에 같이 언급됐다"는 것만으로 만들어진 약한 추측성
        # 쌍인지 판정한다. 사건에서 역할(가해자/피해자, 기만자/피기만자 등)까지
        # 구체적으로 뽑힌 경우는 원본 relations 배열에 없어도 근거가 있는 정보로
        # 취급한다 — related_events에 event_id가 있으면 구조화된 사건에서 왔다는
        # 뜻이다(리마인드 조합으로 만든 것은 event_id가 없다).
        # 근거 없는 쌍이라도 데이터에서 완전히 지우지는 않는다 — has_direct_evidence
        # 로만 표시해서, 기본 관계도 엣지로는 안 그리되(프론트에서 필터링) 해당 인물을
        # 클릭했을 때는 볼 수 있게 남겨둔다.
        has_direct_evidence = any(
            not relationship.is_story_relation
            or any(event.get("event_id") for event in relationship.related_events)
            for relationship in relationships
        )

        relationships = sorted(
            relationships,
            key=lambda relationship: (
                not relationship.is_story_relation,
                relationship.revision_offset,
            ),
        )
        first = relationships[0]
        category = _category_for(relationships)
        directionality = _directionality_for(relationships, category)
        display_label = _display_label_for(relationships, category)
        first_seen = min(
            relationship.first_seen_global_index or relationship.revision_offset
            for relationship in relationships
        )
        last_seen = max(
            relationship.last_seen_global_index
            or relationship.first_seen_global_index
            or relationship.revision_offset
            for relationship in relationships
        )
        importance_score = _importance_for(relationships, entities_by_id, reminder_ids)
        detail_parts = []
        related_events = []
        for relationship in relationships:
            detail = relationship.detail or relationship.description or relationship.label
            if detail and detail not in detail_parts:
                detail_parts.append(detail)
            for related_event in relationship.related_events:
                if related_event not in related_events:
                    related_events.append(related_event)
        if len(detail_parts) > 6:
            detail_parts = detail_parts[:6]
        detail = "\n".join(detail_parts)
        story_relation = next((relationship for relationship in relationships if relationship.is_story_relation), None)

        summarized.append(
            first.model_copy(
                update={
                    "label": display_label,
                    "display_label": display_label,
                    "relation_category": category,
                    "directionality": directionality,
                    "relation_importance_score": importance_score,
                    "relation_importance_level": "major" if importance_score >= 4 else "minor",
                    "first_seen_global_index": first_seen,
                    "first_seen_boundary": first_seen,
                    "is_new_at_current_position": first_seen == current_boundary_global_index,
                    "detail": detail,
                    "description": detail or first.description,
                    "revision_offset": first_seen,
                    "event_name": story_relation.event_name if story_relation else first.event_name,
                    "event_summary": story_relation.event_summary if story_relation else first.event_summary,
                    "relation_role": story_relation.relation_role if story_relation else first.relation_role,
                    "confidence": max((relationship.confidence or 0.5) for relationship in relationships),
                    "is_story_relation": any(relationship.is_story_relation for relationship in relationships),
                    # display_label이 실제로 원본(비-합성) 라벨에서 왔는지 여부. 원본
                    # 라벨이 하나라도 있으면 그게 display_label로 채택되므로(단일 라벨
                    # 또는 "초면 → 협력자" 같은 시간순 조합) False가 되고,
                    # apply_relationship_presentation이 이후 제네릭 role_pair_label로
                    # 덮어쓰지 않는다. (is_story_relation은 "그룹에 합성 관계가 하나라도
                    # 있었는지"라는 다른 의미로 계속 쓰이므로 별도 필드로 둔다.) 문자열을
                    # display_label과 정확히 비교하지 않는다 — 라벨 조합이나 12자
                    # 절단([:12]) 때문에 원본 텍스트와 완전히 같지 않을 수 있어서다.
                    "label_is_generic": not any(
                        not relationship.is_story_relation and relationship.label.strip()
                        for relationship in relationships
                    ),
                    "has_direct_evidence": has_direct_evidence,
                    "relation_kind": _relation_kind_for(relationships),
                    "last_seen_global_index": last_seen,
                    "related_events": related_events,
                }
            )
        )

    summarized.sort(
        key=lambda relationship: (
            relationship.relation_importance_level != "major",
            -(relationship.relation_importance_score or 1),
            relationship.revision_offset,
        )
    )
    return graph.model_copy(update={"relationships": summarized})
