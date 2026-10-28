"""에이전트 출력 → 통합 계약 변환 어댑터.

BuildAgent(`spokeeper/agents/build_agent.py`)는 인물/관계/사건을 **이름 기반**으로 뽑는다:

    {
      "characters": [{"name", "description", "evidence"}],
      "relations":  [{"source", "target", "relation", "evidence"}],
      "events":     [{"summary", "participants": [name...], "evidence"}]
    }

프론트/백엔드 계약(SPEC §0.5)은 **id 기반** graph_json·reminders 를 요구한다. 이 모듈은
그 사이를 순수 함수로 변환한다 — LLM/외부 의존성 없음. '다음 에이전트' 담당자는 build 결과만
같은 모양으로 넘기면 `precompute` 가 이 어댑터로 계약 JSON 을 만들어 `AgentResultSource` 에 꽂는다.

기본값 정책 (원본에 근거 없으면 추측 금지 — 불변 규칙):
- entity.type = "person", entity.color = "blue" (build 결과에 optional type/color 있으면 존중)
- relation.tone = "neutral" (라벨 키워드로 ally/tense 약한 휴리스틱 적용, 그 외 neutral)
"""
from __future__ import annotations

import hashlib
from typing import Iterable

from agents.character_entity_filter import filter_generic_role_entities
from agents.build_agent import normalize_event

from .schemas import Entity, GraphJson, Relationship, ReminderLine, StoryEvent

# 관계 라벨 → tone 약한 휴리스틱 (근거 없는 강한 추측은 하지 않음)
_TENSE_HINTS = ("적", "추적", "압박", "의혹", "은폐", "배신", "대립", "감시", "위협")
_ALLY_HINTS = ("동료", "동맹", "협력", "친구", "가족", "연인", "동반")

_VALID_TYPES = {"person", "ship", "org", "place"}
_VALID_COLORS = {"blue", "dark"}
_VALID_TONES = {"neutral", "ally", "tense"}
_VALID_RELATION_KINDS = {"personal", "action"}


def entity_id(name: str) -> str:
    """이름 → 안정적 entity id. 순서·언어(한글 포함)에 무관하게 결정적."""
    digest = hashlib.md5(name.strip().encode("utf-8")).hexdigest()[:8]
    return f"e_{digest}"


def _relation_id(source_id: str, target_id: str, label: str) -> str:
    key = f"{source_id}|{target_id}|{label}".encode("utf-8")
    return f"r_{hashlib.md5(key).hexdigest()[:8]}"


def _infer_tone(label: str, explicit: str | None) -> str:
    if explicit in _VALID_TONES:
        return explicit
    text = label or ""
    if any(h in text for h in _TENSE_HINTS):
        return "tense"
    if any(h in text for h in _ALLY_HINTS):
        return "ally"
    return "neutral"


def to_graph_json(
    build_result: dict,
    boundary: int,
    *,
    spoiler_safe: bool = True,
    revision_offsets: dict[str, int] | None = None,
) -> GraphJson:
    """build_result → GraphJson. relationships 의 source/target 은 entity id 로 매핑된다.

    revision_offsets: 관계 id → 최초 등장 경계선. 없으면 boundary 로 채운다.
    """
    build_result = filter_generic_role_entities(build_result)
    revision_offsets = revision_offsets or {}
    entities: dict[str, Entity] = {}

    def ensure_entity(
        name: str, *, type_: str | None = None, color: str | None = None, description: str | None = None
    ) -> str:
        name = (name or "").strip()
        if not name:
            return ""
        eid = entity_id(name)
        if eid not in entities:
            entities[eid] = Entity(
                id=eid,
                name=name,
                type=type_ if type_ in _VALID_TYPES else "person",
                color=color if color in _VALID_COLORS else "blue",
                description=(description or "").strip() or None,
            )
        elif description and not entities[eid].description:
            entities[eid] = entities[eid].model_copy(update={"description": description.strip()})
        return eid

    for ch in build_result.get("characters", []):
        ensure_entity(
            ch.get("name", ""),
            type_=ch.get("type"),
            color=ch.get("color"),
            description=ch.get("description"),
        )

    relationships: list[Relationship] = []
    for rel in build_result.get("relations", []):
        src = ensure_entity(rel.get("source", ""))
        tgt = ensure_entity(rel.get("target", ""))
        if not src or not tgt:
            continue
        label = (rel.get("relation") or "").strip()
        rid = _relation_id(src, tgt, label)
        relation_kind = rel.get("relation_kind")
        relationships.append(
            Relationship(
                id=rid,
                source=src,
                target=tgt,
                label=label,
                tone=_infer_tone(label, rel.get("tone")),
                description=(rel.get("evidence") or rel.get("description") or label).strip(),
                revision_offset=revision_offsets.get(rid, boundary),
                relation_kind=relation_kind if relation_kind in _VALID_RELATION_KINDS else None,
            )
        )

    events: list[StoryEvent] = []
    for event in build_result.get("events", []):
        normalized_event = normalize_event(event, current_offset=boundary)
        participants = []
        for participant in normalized_event.get("participants", []):
            name = participant.get("character_name", "")
            if not name:
                continue
            ensure_entity(name)
            participants.append(participant)
        if not participants:
            continue
        events.append(
            StoryEvent.model_validate(
                {
                    **normalized_event,
                    "participants": participants,
                    "first_seen_chunk_offset": normalized_event.get("first_seen_chunk_offset", boundary),
                    "last_seen_chunk_offset": normalized_event.get("last_seen_chunk_offset", boundary),
                }
            )
        )

    return GraphJson(
        offset=boundary,
        spoiler_safe=spoiler_safe,
        entities=list(entities.values()),
        relationships=relationships,
        events=events,
    )


def to_reminder_lines(build_result: dict) -> list[ReminderLine]:
    """events → reminders. 각 사건 요약을 한 줄로, participants 를 entity id 로 매핑."""
    build_result = filter_generic_role_entities(build_result)
    lines: list[ReminderLine] = []
    for ev in build_result.get("events", []):
        normalized_event = normalize_event(ev)
        text = (normalized_event.get("event_summary") or normalized_event.get("summary") or "").strip()
        if not text:
            continue
        ids = [
            entity_id(p.get("character_name", "") if isinstance(p, dict) else p)
            for p in normalized_event.get("participants", [])
            if ((p.get("character_name", "") if isinstance(p, dict) else p) or "").strip()
        ]
        lines.append(ReminderLine(text=text, entity_ids=ids))
    return lines


def build_relation_ids(build_result: dict) -> Iterable[str]:
    """build_result 안 관계들의 계약 id 를 산출 (revision_offset 최초등장 추적용)."""
    for rel in build_result.get("relations", []):
        src = entity_id((rel.get("source") or "").strip())
        tgt = entity_id((rel.get("target") or "").strip())
        label = (rel.get("relation") or "").strip()
        if rel.get("source") and rel.get("target"):
            yield _relation_id(src, tgt, label)
