from __future__ import annotations

import re

from .schemas import GraphJson, Relationship


ROLE_PAIR_LABELS = {
    "crime": ("가해자", "피해자"),
    # "용의자"(아직 확정 안 된 의심 단계)는 조사 관계로 안 치므로, 여기 남는 건
    # 항상 진범/공범/은닉자/도주자처럼 확정된 상대를 조사하는 경우뿐이다
    # (story_relations.py의 investigation 규칙이 이미 "suspect"를 걸러낸다).
    "investigation": ("수사관", "범인"),
    "protection": ("보호자", "보호 대상"),
    "deception": ("기만자", "기만당한 인물"),
    "threat": ("위협한 인물", "위협받은 인물"),
    "witness": ("목격자", "피해자"),
    "concealment": ("은닉자", "숨어 있는 인물"),
    "help": ("조력자", "수혜자"),
    "work": ("의뢰인", "조사자"),
    "inheritance": ("사망자", "상속인"),
    "family": ("가족", "가족"),
    "ally": ("조력자", "조력자"),
    # 같은 사건에서 같은 역할을 공유하는 두 사람(예: 공범 두 명) — 특정 장르 하나만
    # 땜질하지 않도록 story_relations.py의 _CO_ROLE_GROUPS가 역할 전체를 훑어서 만든다.
    "accomplice": ("공범", "공범"),
    "co_victim": ("공동 피해자", "공동 피해자"),
    "co_witness": ("공동 목격자", "공동 목격자"),
}

CATEGORY_LABELS = {
    "crime": ("가해자", "피해자"),
    "investigation": ("조사자", "용의자"),
    "deception": ("기만자", "기만당한 인물"),
    "protection": ("보호자", "보호 대상"),
    "work": ("의뢰인", "조사자"),
    "family": ("가족", "가족"),
    "ally": ("조력자", "동료"),
    "romance": ("관계 인물", "관계 인물"),
    "mystery": ("단서 제공자", "관련 인물"),
    "conflict": ("대립 인물", "대립 인물"),
    "neutral": ("관련 인물", "관련 인물"),
}

MECHANICAL_PHRASES = (
    "사건 관련 인물",
    "피해 인물",
    "조사하는 인물",
    "조사 대상",
    "가해와 피해 맥락",
    "조사와 의심의 맥락",
    "사건 맥락으로 연결",
    "같은 사건 안에서 관련 인물",
)


def _name_of(graph: GraphJson, entity_id: str) -> str:
    return next((entity.name for entity in graph.entities if entity.id == entity_id), entity_id)


def _clean_text(text: str | None, *, limit: int = 180) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _short_name(name: str) -> str:
    return name


def _context_text(relationship: Relationship) -> str:
    parts = [
        relationship.event_name or "",
        relationship.event_summary or "",
        relationship.detail or "",
        relationship.description or "",
    ]
    for event in relationship.related_events:
        parts.extend(
            str(event.get(key, ""))
            for key in ("event_name", "event_summary", "evidence", "relation_role")
        )
    return " ".join(part for part in parts if part)


def _event_name(relationship: Relationship) -> str:
    if relationship.event_name:
        return _clean_text(relationship.event_name, limit=48)
    for event in relationship.related_events:
        name = event.get("event_name")
        if name:
            return _clean_text(str(name), limit=48)
    return relationship.display_label or relationship.label or "관계"


def _role_pair(relationship: Relationship) -> tuple[str, str]:
    if relationship.relation_role and relationship.relation_role in ROLE_PAIR_LABELS:
        return ROLE_PAIR_LABELS[relationship.relation_role]
    category = relationship.relation_category or "neutral"
    return CATEGORY_LABELS.get(category, CATEGORY_LABELS["neutral"])


def _contextual_role_pair(relationship: Relationship, source_name: str, target_name: str) -> tuple[str, str]:
    return _role_pair(relationship)


def _evidence_items(relationship: Relationship) -> list[str]:
    candidates: list[str] = []
    for event in relationship.related_events:
        for key in ("evidence", "event_summary"):
            value = event.get(key)
            if value:
                candidates.append(str(value))
    candidates.extend(
        value
        for value in [relationship.event_summary, relationship.detail, relationship.description]
        if value
    )

    evidence: list[str] = []
    for candidate in candidates:
        cleaned = _clean_text(candidate, limit=220)
        if cleaned and cleaned not in evidence:
            evidence.append(cleaned)
        if len(evidence) >= 2:
            break
    return evidence


def _summary_from_event_text(text: str | None, *, source_name: str, target_name: str, limit: int = 150) -> str:
    cleaned = _clean_text(text, limit=limit)
    if not cleaned:
        return ""
    if len(cleaned) <= 120 and source_name in cleaned and target_name in cleaned:
        return cleaned
    return cleaned


def _summary_for(relationship: Relationship, source_name: str, target_name: str, event_name: str) -> str:
    category = relationship.relation_category or "neutral"
    source = _short_name(source_name)
    target = _short_name(target_name)
    text = _context_text(relationship)

    # 예전엔 여기에 역할쌍 문자열별로 고정 문장이 하드코딩돼 있었다(예: "의뢰인 → 조사자"면
    # 무조건 "찰스 경의 죽음과 가문의 저주" 운운). role_pair_label은 카테고리에서 자동으로
    # 생성되는 범용 라벨이라 어떤 책에서든 똑같이 매칭되는데, 그 고정 문장은 셜록 홈즈
    # 테스트북 하나를 보고 쓴 것이었다 — 그래서 전혀 다른 책(예: 심청전)의 관계에도 "찰스
    # 경"이 그대로 튀어나오는 환각이 발생했다. 실제 사건 텍스트(event_summary)나 카테고리
    # 기반의 범용 문장만 쓰도록 전부 제거한다.
    event_summary = _summary_from_event_text(relationship.event_summary, source_name=source_name, target_name=target_name)
    if event_summary and not any(phrase in event_summary for phrase in MECHANICAL_PHRASES):
        return event_summary

    if category == "work":
        return f"{source}와 {target}은 의뢰나 조사 요청을 통해 사건 해결 과정에서 연결된다."
    if category == "family":
        return f"{source}와 {target}은 가족이나 상속 문제를 통해 사건의 배경과 연결된다."
    if category == "ally":
        return f"{source}와 {target}은 사건을 해결하거나 위험을 피하는 과정에서 서로 협력한다."
    if category == "deception":
        return f"{source}와 {target}은 속임수나 은폐가 드러나는 과정에서 연결된다."
    if category == "mystery":
        return f"{source}와 {target}은 사건의 단서나 의문을 밝히는 과정에서 연결된다."
    if text:
        return _clean_text(text, limit=150)
    return f"{source}와 {target}은 '{event_name}'을 통해 서로 관련된다."


def apply_relationship_presentation(graph: GraphJson) -> GraphJson:
    relationships: list[Relationship] = []
    for relationship in graph.relationships:
        source_name = _name_of(graph, relationship.source)
        target_name = _name_of(graph, relationship.target)
        source_role, target_role = _contextual_role_pair(relationship, source_name, target_name)
        # 둘이 같은 역할을 공유하는 대칭 관계(공범-공범, 공동 목격자-공동 목격자 등)는
        # "공범 → 공범"처럼 화살표로 잇는 대신 그냥 한 번만 보여준다 — 화살표는
        # 방향이 있다는 인상을 주는데 이런 관계는 애초에 방향이 없다.
        role_pair_label = source_role if source_role == target_role else f"{source_role} → {target_role}"
        event_name = _event_name(relationship)
        existing_label = (relationship.display_label or relationship.label or "").strip()
        display_label = role_pair_label if (relationship.label_is_generic or not existing_label) else existing_label
        summary = _summary_for(relationship, source_name, target_name, event_name)
        evidence = _evidence_items(relationship)

        relationships.append(
            relationship.model_copy(
                update={
                    "role_label": source_role,
                    "role_pair_label": role_pair_label,
                    "event_name": event_name,
                    "display_label": display_label,
                    "relationship_summary": summary,
                    "evidence": evidence,
                }
            )
        )

    return graph.model_copy(update={"relationships": relationships})
