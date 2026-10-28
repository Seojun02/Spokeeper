from __future__ import annotations

import hashlib
from itertools import combinations

from .schemas import GraphJson, Relationship, ReminderLine


STORY_CATEGORIES = {
    "crime": (
        "살인",
        "살해",
        "죽",
        "사망",
        "시체",
        "범인",
        "피해자",
        "죄",
        "독살",
        "공격",
    ),
    "investigation": (
        "조사",
        "수사",
        "추적",
        "의심",
        "용의",
        "단서",
        "밝히",
        "찾",
        "탐문",
    ),
    "deception": (
        "속",
        "기만",
        "위장",
        "거짓",
        "은폐",
        "숨김",
        "비밀",
        "협박",
        "함정",
    ),
    "protection": (
        "보호",
        "돕",
        "도움",
        "동행",
        "구출",
        "지키",
        "경호",
    ),
    "work": (
        "의뢰",
        "고용",
        "부탁",
        "임무",
    ),
    "family": (
        "가족",
        "부인",
        "남편",
        "아내",
        "후계자",
        "상속",
        "가문",
        "형제",
        "남매",
        "부부",
    ),
    "ally": (
        "친구",
        "동료",
        "협력",
        "조력",
        "신뢰",
    ),
    "romance": (
        "사랑",
        "연인",
        "약혼",
        "질투",
        "결혼",
    ),
    "mystery": (
        "정체",
        "미스터리",
        "수수께끼",
        "의문",
    ),
}

STORY_PRIORITY = (
    "crime",
    "investigation",
    "deception",
    "protection",
    "work",
    "family",
    "romance",
    "ally",
    "mystery",
)

STORY_LABELS = {
    "crime": "사건",
    "investigation": "조사",
    "deception": "속임",
    "protection": "보호",
    "work": "의뢰",
    "family": "가족",
    "ally": "협력",
    "romance": "관계",
    "mystery": "단서",
}

STORY_ROLES = {
    "crime": "사건 관련",
    "investigation": "조사/추적",
    "deception": "속임/은폐",
    "protection": "보호/도움",
    "work": "의뢰/업무",
    "family": "가족/상속",
    "ally": "협력",
    "romance": "애정 관계",
    "mystery": "미스터리 단서",
}

CORE_STORY_CATEGORIES = {"crime", "investigation", "deception", "protection"}


def _structured_story_id(source: str, target: str, category: str, event_id: str, role: str) -> str:
    raw = f"{source}|{target}|{category}|{event_id}|{role}".encode("utf-8")
    return f"sr_{hashlib.md5(raw).hexdigest()[:10]}"


def _category_for_text(text: str) -> str | None:
    counts = {
        category: sum(1 for hint in hints if hint in text)
        for category, hints in STORY_CATEGORIES.items()
    }
    if not any(counts.values()):
        return None
    return max(STORY_PRIORITY, key=lambda category: (counts.get(category, 0), -STORY_PRIORITY.index(category)))


def _is_directed(category: str) -> bool:
    return category in {"crime", "investigation", "deception", "protection", "work"}


def _event_payload(summary: str, category: str, boundary_global_index: int, confidence: float) -> dict:
    return {
        "event_name": summary[:40],
        "event_summary": summary,
        "relation_category": category,
        "first_seen_global_index": boundary_global_index,
        "last_seen_global_index": boundary_global_index,
        "confidence": confidence,
    }


def _structured_event_payload(
    event, category: str, relation_role: str, confidence: float, *, fan_out: int = 1
) -> dict:
    first_seen = event.first_seen_global_index or event.first_seen_chunk_offset or 0
    last_seen = event.last_seen_global_index or event.last_seen_chunk_offset or first_seen
    return {
        "event_id": event.event_id,
        "event_name": event.event_name,
        "event_summary": event.event_summary,
        "relation_category": category,
        "relation_role": relation_role,
        "first_seen_global_index": first_seen,
        "last_seen_global_index": last_seen,
        "confidence": confidence,
        "evidence": event.evidence,
        # 한 사람이 같은 사건에서 이 역할 쌍으로 몇 명과 동시에 엮였는지(예: 형사 한 명이
        # 용의자 10명을 한꺼번에 심문). 크면 relation_summary._importance_for가 중요도를
        # 낮춰서, 라벨이 반복되는 엣지들이 그래프를 도배하지 않게 한다.
        "fan_out": fan_out,
    }


def _make_structured_story_relationship(
    source: str,
    target: str,
    *,
    category: str,
    relation_role: str,
    event,
    confidence: float,
    fan_out: int = 1,
) -> Relationship:
    first_seen = event.first_seen_global_index or event.first_seen_chunk_offset or 0
    last_seen = event.last_seen_global_index or event.last_seen_chunk_offset or first_seen
    label = STORY_LABELS.get(category, "사건")
    related_event = _structured_event_payload(event, category, relation_role, confidence, fan_out=fan_out)
    # 한 사람(예: 형사)이 같은 사건에서 여러 명과 동시에 이 역할 쌍을 맺으면 엣지마다
    # 똑같은 제네릭 라벨이 반복돼 그래프 텍스트가 도배된다. fan_out이 크면 중요도를
    # 낮춰서 기본 그래프에서는 라벨 없이 얇게만 보이게 한다(정보 자체는 related_events에
    # 그대로 남아 클릭하면 보인다) — 한두 명만 연결된 경우는 그대로 강조 표시한다.
    is_hub = fan_out > 2
    return Relationship(
        id=_structured_story_id(source, target, category, event.event_id, relation_role),
        source=source,
        target=target,
        label=label,
        tone="tense" if category in {"crime", "deception"} else "neutral",
        description=event.event_summary,
        revision_offset=first_seen,
        display_label=label,
        relation_category=category,
        directionality="directed" if _is_directed(category) else "undirected",
        relation_importance_score=(3 if is_hub else 5) if category in {"crime", "investigation", "deception"} else (2 if is_hub else 4),
        relation_importance_level="minor" if is_hub else "major",
        first_seen_global_index=first_seen,
        first_seen_boundary=first_seen,
        is_new_at_current_position=False,
        detail=event.event_summary,
        event_name=event.event_name,
        event_summary=event.event_summary,
        relation_role=relation_role,
        confidence=confidence,
        is_story_relation=True,
        relation_kind="action",
        last_seen_global_index=last_seen,
        related_events=[related_event],
    )


def _participants_by_role(event) -> dict[str, list]:
    by_role: dict[str, list] = {}
    for participant in event.participants:
        by_role.setdefault(participant.role, []).append(participant)
    return by_role


def _add_role_pairs(
    relationships: list[Relationship],
    seen_story_ids: set[str],
    event,
    names_to_ids: dict[str, str],
    source_roles: tuple[str, ...],
    target_roles: tuple[str, ...],
    *,
    category: str,
    relation_role: str,
) -> None:
    by_role = _participants_by_role(event)
    pairs: list[tuple] = []
    for source_role in source_roles:
        for target_role in target_roles:
            for source_participant in by_role.get(source_role, []):
                for target_participant in by_role.get(target_role, []):
                    if source_participant.character_name == target_participant.character_name:
                        continue
                    pairs.append((source_participant, target_participant))

    # 한 사람이 이 사건에서 몇 명과 이 역할 쌍으로 엮이는지(예: 형사 한 명이 용의자
    # 10명을 한꺼번에 심문) — 크면 _make_structured_story_relationship이 중요도를
    # 낮춰서 라벨 반복으로 그래프가 도배되지 않게 한다.
    fan_out_by_source: dict[str, int] = {}
    for source_participant, _ in pairs:
        fan_out_by_source[source_participant.character_name] = (
            fan_out_by_source.get(source_participant.character_name, 0) + 1
        )

    for source_participant, target_participant in pairs:
        source = names_to_ids.get(source_participant.character_name)
        target = names_to_ids.get(target_participant.character_name)
        if not source or not target:
            continue
        confidence = min(
            event.confidence,
            source_participant.confidence,
            target_participant.confidence,
        )
        relationship = _make_structured_story_relationship(
            source,
            target,
            category=category,
            relation_role=relation_role,
            event=event,
            confidence=confidence,
            fan_out=fan_out_by_source.get(source_participant.character_name, 1),
        )
        if relationship.id in seen_story_ids:
            continue
        seen_story_ids.add(relationship.id)
        relationships.append(relationship)


# _add_role_pairs는 "서로 다른 역할"끼리만 엮는다(가해자→피해자, 조사자→용의자 등).
# 그래서 "같은 사건에서 같은 역할을 공유하는 두 사람"(공범과 공범, 목격자와 목격자
# 등)은 대응하는 규칙이 없으면 아예 관계가 안 만들어지거나, 근거 부족한 리마인드
# 조합으로만 잡혀서 엉뚱한 카테고리(예: "조사자→용의자")로 잘못 라벨링된다. 특정
# 역할 하나(예: 공범)만 땜질하면 다른 역할 조합에서 똑같은 문제가 재발하므로,
# EventParticipant.role 전체 목록 중 "같은 역할을 공유하면 의미 있는 대칭 관계가
# 되는" 역할군을 한 번에 다뤄서 장르에 상관없이 동일하게 적용되게 한다.
# "공동 용의자"(suspect끼리)는 넣지 않는다 — 용의자는 확정 안 된 의심 단계라,
# 여러 명이 같이 의심받는다는 것만으로 관계를 만들면 "의심하는 단계"가 그대로
# 그래프에 노출된다.
_CO_ROLE_GROUPS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    # (role 집합, category, relation_role — relation_presenter.ROLE_PAIR_LABELS 키)
    (("perpetrator", "accomplice"), "crime", "accomplice"),
    (("victim",), "crime", "co_victim"),
    (("witness",), "mystery", "co_witness"),
)


def _add_co_role_pairs(
    relationships: list[Relationship],
    seen_story_ids: set[str],
    event,
    names_to_ids: dict[str, str],
) -> None:
    by_role = _participants_by_role(event)
    for roles, category, relation_role in _CO_ROLE_GROUPS:
        participants = [participant for role in roles for participant in by_role.get(role, [])]
        # 그룹이 크면(예: "용의자 10명") 조합 수가 급격히 늘어난다(n명 → n*(n-1)/2쌍).
        # 각자의 fan_out을 그룹 크기-1로 넘겨서, 큰 그룹일수록 엣지 중요도가 낮아지고
        # 기본 그래프에서는 라벨 없이 얇게만 보이게 한다.
        fan_out = max(1, len(participants) - 1)
        for a, b in combinations(participants, 2):
            source = names_to_ids.get(a.character_name)
            target = names_to_ids.get(b.character_name)
            if not source or not target or source == target:
                continue
            confidence = min(event.confidence, a.confidence, b.confidence)
            relationship = _make_structured_story_relationship(
                source,
                target,
                category=category,
                relation_role=relation_role,
                event=event,
                confidence=confidence,
                fan_out=fan_out,
            )
            if relationship.id in seen_story_ids:
                continue
            seen_story_ids.add(relationship.id)
            relationships.append(relationship)


def _relationships_from_structured_events(
    graph: GraphJson,
    *,
    current_boundary_global_index: int,
) -> list[Relationship]:
    names_to_ids = {entity.name: entity.id for entity in graph.entities}
    relationships: list[Relationship] = []
    seen_story_ids: set[str] = set()

    for event in graph.events:
        first_seen = event.first_seen_global_index or event.first_seen_chunk_offset or 0
        if first_seen > current_boundary_global_index:
            continue

        _add_role_pairs(
            relationships,
            seen_story_ids,
            event,
            names_to_ids,
            ("perpetrator", "accomplice"),
            ("victim",),
            category="crime",
            relation_role="crime",
        )
        _add_role_pairs(
            relationships,
            seen_story_ids,
            event,
            names_to_ids,
            ("perpetrator", "threatener", "deceiver"),
            ("target", "threatened"),
            category="crime",
            relation_role="threat",
        )
        # "용의자(suspect)"는 아직 확정 안 된 의심 단계일 뿐이라 관계로 안 만든다 —
        # 실제로 경찰/수사관이 진범(perpetrator)이나 공범(accomplice)을 조사하는
        # 경우만, 혹은 은닉/도주처럼 능동적인 행동(concealer/pursued)이 있는 경우만
        # "조사" 관계로 취급한다. "의심스러워 보인다"는 것만으로는 조사 관계가 아니다.
        _add_role_pairs(
            relationships,
            seen_story_ids,
            event,
            names_to_ids,
            ("investigator", "pursuer"),
            ("perpetrator", "accomplice", "deceiver", "concealer", "pursued"),
            category="investigation",
            relation_role="investigation",
        )
        _add_role_pairs(
            relationships,
            seen_story_ids,
            event,
            names_to_ids,
            ("protector", "helper"),
            ("target", "victim", "threatened", "pursued"),
            category="protection",
            relation_role="protection",
        )
        # helper/beneficiary는 BuildAgent가 "뚜렷한 관계로 못 박기 애매할 때" 쓰는
        # 약한 기본 역할이라, 이걸로 그래프에 "조력자→수혜자" 엣지까지 만들면 정보량
        # 없이 반복적으로만 보인다. 사건 설명(리마인드)에는 이미 그대로 남으니,
        # 관계 그래프 엣지로는 만들지 않는다.
        _add_role_pairs(
            relationships,
            seen_story_ids,
            event,
            names_to_ids,
            ("deceiver", "concealer", "threatener"),
            ("deceived", "exposed", "threatened"),
            category="deception",
            relation_role="deception",
        )
        _add_role_pairs(
            relationships,
            seen_story_ids,
            event,
            names_to_ids,
            ("concealer",),
            ("pursued",),
            category="deception",
            relation_role="concealment",
        )
        _add_role_pairs(
            relationships,
            seen_story_ids,
            event,
            names_to_ids,
            ("witness",),
            ("victim",),
            category="mystery",
            relation_role="witness",
        )
        _add_role_pairs(
            relationships,
            seen_story_ids,
            event,
            names_to_ids,
            ("employer",),
            ("employee", "investigator", "helper"),
            category="work",
            relation_role="work",
        )
        _add_role_pairs(
            relationships,
            seen_story_ids,
            event,
            names_to_ids,
            ("beneficiary", "heir"),
            ("victim", "employer"),
            category="family",
            relation_role="inheritance",
        )
        _add_co_role_pairs(relationships, seen_story_ids, event, names_to_ids)

    return relationships


def _enrich_existing_relationship(
    relationship: Relationship,
    *,
    current_boundary_global_index: int,
) -> Relationship | None:
    if relationship.revision_offset > current_boundary_global_index:
        return None

    text = " ".join(
        part
        for part in [
            relationship.label,
            relationship.description,
            relationship.display_label or "",
            relationship.detail or "",
        ]
        if part
    )
    category = _category_for_text(text)
    if not category:
        return relationship

    is_story = category in CORE_STORY_CATEGORIES
    event_summary = relationship.detail or relationship.description or relationship.label
    update = {
        "relation_category": category,
        "directionality": "directed" if _is_directed(category) else relationship.directionality,
        "event_name": relationship.event_name or event_summary[:40],
        "event_summary": relationship.event_summary or event_summary,
        "relation_role": relationship.relation_role or STORY_ROLES.get(category, "사건 관련"),
        "confidence": max(relationship.confidence or 0.5, 0.75 if is_story else 0.6),
        # BuildAgent가 이미 구체적 라벨(예: "협박자")을 붙인 관계는, 설명 문장에
        # 조사/보호 계열 키워드가 우연히 섞여 있다는 이유만으로 "조사자→용의자" 같은
        # 제네릭 역할 라벨로 화면 표시가 강제 교체되면 안 된다(apply_relationship_
        # presentation이 is_story_relation=True인 관계는 display_label을 role_pair_label로
        # 덮어쓴다). 그래서 여기서는 원래 is_story_relation 값을 그대로 유지하고 — 이미
        # 저장된 관계는 애초에 False이므로 원래 라벨이 보존된다 — 실제로 라벨이 없는
        # 새로 생성된 관계(구조화 이벤트/리마인드 조합)에만 role_pair_label을 쓰게 한다.
        "is_story_relation": relationship.is_story_relation,
        "first_seen_global_index": relationship.first_seen_global_index or relationship.revision_offset,
        "first_seen_boundary": relationship.first_seen_boundary or relationship.revision_offset,
        "last_seen_global_index": relationship.last_seen_global_index or relationship.revision_offset,
    }
    if is_story and not relationship.related_events:
        update["related_events"] = [
            _event_payload(event_summary, category, relationship.revision_offset, update["confidence"])
        ]
    return relationship.model_copy(update=update)


def expand_story_relationships(
    graph: GraphJson,
    reminders: list[ReminderLine],
    *,
    current_boundary_global_index: int,
) -> GraphJson:
    names_by_id = {entity.id: entity.name for entity in graph.entities}
    valid_ids = set(names_by_id)
    relationships: list[Relationship] = _relationships_from_structured_events(
        graph,
        current_boundary_global_index=current_boundary_global_index,
    )

    for relationship in graph.relationships:
        enriched = _enrich_existing_relationship(
            relationship,
            current_boundary_global_index=current_boundary_global_index,
        )
        if enriched is not None:
            relationships.append(enriched)

    # 예전엔 여기서 리마인더 한 줄에 같이 언급된 사람들을 전부 조합(combinations)으로
    # 묶어서 "조사자→용의자"류 관계를 만들었다. 그런데 이 방식은 문장 안에서 누가
    # 실제로 조사자이고 누가 용의자/조력자인지 구분하지 못한 채 언급된 사람 전원을
    # 대칭적으로 짝짓는다 — 그 결과 "서은교가 조사자 역할을 했고 노경수/정다혜가
    # 도왔다"는 문장에서 이미 죽은 피해자 서인호까지 노경수/정다혜와 "조사자→용의자"로
    # 잘못 엮이는 등 사실과 다른 관계가 만들어졌다. 이제는 (1) BuildAgent가 원본
    # 관계를 뽑을 때 소스/타깃과 relation_kind를 직접 판단하고, (2) 구조화된 사건이
    # EventParticipant.role로 누가 무슨 역할인지 명확히 구분해서 관계를 만들기
    # 때문에, 역할을 모른 채 추측하던 이 조합 생성 방식은 완전히 제거한다 — 정보를
    # 덜 보여주더라도 틀린 방향의 관계를 만드는 것보다 낫다.

    return graph.model_copy(update={"relationships": relationships})
