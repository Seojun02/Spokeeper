import hashlib
import json
import re
from langchain_upstage import ChatUpstage
from langchain_core.messages import SystemMessage, HumanMessage

from agents.config import UPSTAGE_API_KEY
from agents.character_entity_filter import filter_generic_role_entities
from agents.llm_utils import invoke_with_retry


BUILD_AGENT_SYSTEM_PROMPT = """
당신은 SpoKeeper의 BuildAgent입니다.

역할:
- 소설 본문에서 현재 읽은 위치까지 확인된 정보만 추출합니다.
- 인물, 관계, 사건을 JSON 형태로 정리합니다.
- 추측, 예측, 해석은 금지합니다.
- 원문에 근거가 없는 정보는 출력하지 않습니다.

characters에 포함할지 판단하는 기준 (매우 중요, 반드시 지키세요):
- **실존하는 개별 인물(사람 한 명)만** characters에 넣습니다.
- 다음은 인물이 아니므로 절대 characters에 넣지 마세요:
  - 가문/가족/혈통 이름 (예: "배스커빌 가문", "○○ 가"). 가문 구성원 개인(예: "헨리 배스커빌")은
    인물이지만, 가문 자체는 인물이 아닙니다.
  - 기관/조직/장소 이름 (예: "차링 크로스 병원", "런던 경찰청", "베이커가")
  - 집단을 가리키는 일반명사 (예: "술꾼들", "마을 사람들", "하인들")
  - 특정 개인을 가리키지 않는 일반명사 (예: "처녀", "목동", "농부" — 실제 이름이나 뚜렷한
    호칭 없이 막연히 등장하는 경우. 단, 이후 본문에서 그 인물을 계속 가리키는 유일한
    표현이라면(예: 이름이 끝까지 안 나오는 조연) 예외적으로 포함 가능)
  - 동물, 사물, 탈것 (사람이 아닌 것은 전부 제외)

사건(events) 추출 원칙:
- 먼저 "사건"을 찾고, 그 사건에서 각 인물이 어떤 역할을 했는지 구조화하세요.
- 단순 친분/동료 관계보다 범행, 피해, 조사, 의심, 추적, 협박, 은폐, 속임, 보호, 도움,
  상속, 의뢰처럼 이야기 진행을 바꾸는 사건을 우선 기록하세요.
- 범인(perpetrator), 피해자(victim), 용의자(suspect)처럼 강한 역할은 evidence에 명확한
  근거가 있을 때만 사용하세요. 애매하면 suspect/helper/witness처럼 약한 역할을 쓰세요.
- 같은 사건이 다시 언급되면 event_name을 최대한 같은 이름으로 유지하세요.
- event_name과 event_summary는 반드시 당신이 이해한 내용을 현대 한국어 문장으로 새로
  써야 합니다. 원문이 고어체·방언·옛 표기(예: 아래아 ㆍ, 옛 한글 자모)처럼 읽기 어려운
  경우에도 절대로 원문을 그대로 베끼거나 발췌해서 event_name/event_summary에 넣지
  마세요 — 그 경우일수록 더 적극적으로 뜻을 현대어로 풀어써야 합니다. 원문 인용은
  evidence 필드에만 넣습니다.

지원 participant role:
- perpetrator, victim, investigator, suspect, accomplice, witness, target, protector,
  deceiver, deceived, helper, beneficiary, heir, employer, employee, informant,
  pursuer, pursued, threatened, threatener, concealer, exposed

relations의 relation_kind 판단 기준:
- "personal": 관계 자체가 두 사람의 정체성/신분인 경우. 예: 가족(부모/자식/형제/부부),
  연인, 친구, 동료, 원수, 라이벌, 동창처럼 특정 사건이 없어도 계속 성립하는 관계.
- "action": 특정 사건/행동 때문에 일시적으로 생긴 관계인 경우. 예: 목격자, 조사자-용의자,
  공범, 가해자-피해자, 협력자(사건 해결을 도움), 의뢰인-조사자처럼 그 사건이 없었다면
  존재하지 않았을 관계.
- 애매하면(예: "동료"가 실제로는 직장에서 오래 알고 지낸 사이인지, 이번 사건 때문에만
  잠깐 협력한 사이인지 불확실하면) evidence 문맥을 보고 판단하되, 그래도 확신이 없으면
  "action"을 선택하세요.

출력은 반드시 아래 JSON 형식을 따르세요.

{
  "characters": [
    {
      "name": "인물명",
      "entity_kind": "named_character | generic_role | important_unknown",
      "keep_as_character": true,
      "description": "현재 본문에서 확인된 설명",
      "evidence": "근거 문장"
    }
  ],
  "relations": [
    {
      "source": "인물A",
      "target": "인물B",
      "relation": "관계",
      "relation_kind": "personal | action",
      "evidence": "근거 문장"
    }
  ],
  "events": [
    {
      "event_id": "짧고 안정적인 사건 id. 모르면 빈 문자열",
      "event_name": "사건명",
      "event_summary": "사건 요약",
      "participants": [
        {"character_name": "인물A", "role": "investigator", "confidence": 0.8},
        {"character_name": "인물B", "role": "suspect", "confidence": 0.6}
      ],
      "evidence": "근거 문장"
    }
  ]
}
"""


SUPPORTED_EVENT_ROLES = {
    "perpetrator",
    "victim",
    "investigator",
    "suspect",
    "accomplice",
    "witness",
    "target",
    "protector",
    "deceiver",
    "deceived",
    "helper",
    "beneficiary",
    "heir",
    "employer",
    "employee",
    "informant",
    "pursuer",
    "pursued",
    "threatened",
    "threatener",
    "concealer",
    "exposed",
}


def _event_id(event_name: str, event_summary: str, participants: list[dict]) -> str:
    role_key = "|".join(
        f"{p.get('character_name', '')}:{p.get('role', '')}"
        for p in sorted(participants, key=lambda p: (p.get("character_name", ""), p.get("role", "")))
    )
    raw = f"{event_name}|{event_summary}|{role_key}".encode("utf-8")
    return f"ev_{hashlib.md5(raw).hexdigest()[:10]}"


def _event_similarity_key(event: dict) -> tuple:
    name = re.sub(r"\s+", "", event.get("event_name") or event.get("summary") or "").lower()
    if name:
        return ("name", name)
    participants = tuple(
        sorted(
            p.get("character_name", "")
            for p in normalize_event(event).get("participants", [])
            if p.get("character_name")
        )
    )
    summary = re.sub(r"\s+", "", event.get("event_summary") or event.get("summary") or "").lower()[:40]
    return ("participants", participants, summary)


def normalize_event(event: dict, *, current_offset: int | None = None) -> dict:
    event_name = (event.get("event_name") or event.get("name") or event.get("summary") or "").strip()
    event_summary = (event.get("event_summary") or event.get("summary") or event_name).strip()
    raw_participants = event.get("participants", [])
    participants: list[dict] = []

    for participant in raw_participants:
        if isinstance(participant, str):
            name = participant.strip()
            role = "witness"
            confidence = 0.5
        elif isinstance(participant, dict):
            name = (participant.get("character_name") or participant.get("name") or "").strip()
            role = (participant.get("role") or "witness").strip()
            confidence = participant.get("confidence", 0.7)
        else:
            continue
        if not name:
            continue
        if role not in SUPPORTED_EVENT_ROLES:
            role = "witness"
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.7
        participants.append(
            {
                "character_name": name,
                "role": role,
                "confidence": max(0.0, min(1.0, confidence)),
            }
        )

    normalized = {
        **event,
        "event_name": event_name or event_summary[:40],
        "event_summary": event_summary,
        "summary": event_summary,
        "participants": participants,
        "evidence": (event.get("evidence") or "").strip(),
    }
    normalized["event_id"] = event.get("event_id") or _event_id(
        normalized["event_name"],
        normalized["event_summary"],
        participants,
    )
    if current_offset is not None:
        normalized.setdefault("first_seen_chunk_offset", current_offset)
        normalized.setdefault("last_seen_chunk_offset", current_offset)
    return normalized


def normalize_events(events: list[dict], *, current_offset: int | None = None) -> list[dict]:
    return [normalize_event(event, current_offset=current_offset) for event in events]


def extract_json_from_text(text: str) -> dict:
    """
    LLM 응답에서 JSON 부분만 안전하게 추출한다.
    JSON 파싱 실패 시에도 앱이 멈추지 않도록 빈 결과를 반환한다.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if "```json" in text:
        start = text.find("```json") + len("```json")
        end = text.find("```", start)

        if end != -1:
            json_text = text[start:end].strip()
            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                pass

    start = text.find("{")
    end = text.rfind("}") + 1

    if start != -1 and end > start:
        json_text = text[start:end]
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass

    return {
        "characters": [],
        "relations": [],
        "events": [],
        "parse_error": True,
        "raw_text": text,
    }


def build_agent(chunks: list[dict], current_offset: int) -> dict:
    """
    현재 offset까지의 chunk를 기반으로 인물, 관계, 사건을 추출한다.
    """
    if not UPSTAGE_API_KEY:
        raise ValueError("UPSTAGE_API_KEY가 설정되지 않았습니다.")

    readable_chunks = chunks

    context_text = "\n\n".join(
        [
            f"[offset={chunk['offset']} / chapter={chunk['chapter_index']}]\n{chunk['text']}"
            for chunk in readable_chunks
        ]
    )

    llm_factory = lambda: ChatUpstage(
        model="solar-pro2",
        api_key=UPSTAGE_API_KEY,
        temperature=0,
        timeout=120,
    )

    response = invoke_with_retry(
        llm_factory,
        [
            SystemMessage(content=BUILD_AGENT_SYSTEM_PROMPT),
            HumanMessage(
                content=f"""
다음은 사용자가 현재까지 읽은 소설 본문입니다.

현재 offset: {current_offset}

본문:
{context_text}

위 본문에서 확인된 인물, 관계, 사건만 추출하세요.
"""
            ),
        ],
    )

    result = extract_json_from_text(response.content)

    build_result = {
        "current_offset": current_offset,
        "used_chunk_count": len(readable_chunks),
        "characters": result.get("characters", []),
        "relations": result.get("relations", []),
        "events": normalize_events(result.get("events", []), current_offset=current_offset),
        "parse_error": result.get("parse_error", False),
        "raw_response": response.content,
    }
    return filter_generic_role_entities(build_result)

def incremental_build_agent(
    chunks: list[dict],
    current_offset: int,
    last_built_offset: int,
    previous_results: dict,
    ) -> dict:
    """
    마지막으로 분석한 offset 이후의 chunk만 분석하고,
    기존 결과에 새 결과를 누적한다.
    """
    new_chunks = [
        chunk for chunk in chunks
        if last_built_offset < chunk["offset"] <= current_offset
    ]

    MAX_NEW_CHUNKS = 5

    new_chunks = new_chunks[:MAX_NEW_CHUNKS]

    if not new_chunks:
        return {
            "current_offset": current_offset,
            "last_built_offset": last_built_offset,
            "used_chunk_count": 0,
            "characters": previous_results.get("characters", []),
            "relations": previous_results.get("relations", []),
            "events": previous_results.get("events", []),
            "message": "새로 분석할 chunk가 없습니다.",
        }

    partial_result = build_agent(
    chunks=new_chunks,
    current_offset=max(chunk["offset"] for chunk in new_chunks),
    )

    merged_result = merge_build_results(
        previous_results=previous_results,
        new_result=partial_result,
    )

    return {
        "current_offset": current_offset,
        "last_built_offset": current_offset,
        "used_chunk_count": len(new_chunks),
        "characters": merged_result["characters"],
        "relations": merged_result["relations"],
        "events": merged_result["events"],
        "message": "증분 분석 완료",
    }


def merge_build_results(previous_results: dict, new_result: dict) -> dict:
    """
    기존 인물/관계/사건 결과에 새 결과를 병합한다.
    완전한 동일성 판단은 아직 하지 않고, 단순 중복 제거만 수행한다.
    (표기가 다른 동일 인물 병합은 이름 유사도로는 오탐이 커서, VerifierAgent의
    LLM 판단으로 옮겼다 — agents/verifier_agent.py의 canonicalize_new_characters 참고.)
    """
    characters = deduplicate_by_key(
        previous_results.get("characters", []) + new_result.get("characters", []),
        key="name",
    )

    relations = deduplicate_relation(
        previous_results.get("relations", []) + new_result.get("relations", [])
    )

    events = merge_events(previous_results.get("events", []) + new_result.get("events", []))

    return filter_generic_role_entities({
        "characters": characters,
        "relations": relations,
        "events": events,
    })


def deduplicate_by_key(items: list[dict], key: str) -> list[dict]:
    seen = set()
    result = []

    for item in items:
        value = item.get(key)

        if not value:
            result.append(item)
            continue

        if value in seen:
            continue

        seen.add(value)
        result.append(item)

    return result


def deduplicate_relation(relations: list[dict]) -> list[dict]:
    seen = set()
    result = []

    for relation in relations:
        source = relation.get("source", "")
        target = relation.get("target", "")
        rel = relation.get("relation", "")

        key = (source, target, rel)

        if key in seen:
            continue

        seen.add(key)
        result.append(relation)

    return result


def merge_events(events: list[dict]) -> list[dict]:
    merged: dict[tuple, dict] = {}

    for raw_event in events:
        event = normalize_event(raw_event)
        key = _event_similarity_key(event)
        if key not in merged:
            merged[key] = event
            continue

        existing = merged[key]
        existing_participants = {
            (p.get("character_name"), p.get("role")): p
            for p in existing.get("participants", [])
        }
        for participant in event.get("participants", []):
            participant_key = (participant.get("character_name"), participant.get("role"))
            if participant_key not in existing_participants:
                existing["participants"].append(participant)
                continue
            existing_participants[participant_key]["confidence"] = max(
                existing_participants[participant_key].get("confidence", 0.7),
                participant.get("confidence", 0.7),
            )

        if event.get("evidence") and event["evidence"] not in existing.get("evidence", ""):
            existing["evidence"] = "\n".join(part for part in [existing.get("evidence", ""), event["evidence"]] if part)
        if event.get("event_summary") and event["event_summary"] not in existing.get("event_summary", ""):
            existing["event_summary"] = existing.get("event_summary") or event["event_summary"]
            existing["summary"] = existing["event_summary"]

        first_offsets = [
            value
            for value in [
                existing.get("first_seen_chunk_offset"),
                event.get("first_seen_chunk_offset"),
            ]
            if isinstance(value, int)
        ]
        last_offsets = [
            value
            for value in [
                existing.get("last_seen_chunk_offset"),
                event.get("last_seen_chunk_offset"),
            ]
            if isinstance(value, int)
        ]
        if first_offsets:
            existing["first_seen_chunk_offset"] = min(first_offsets)
        if last_offsets:
            existing["last_seen_chunk_offset"] = max(last_offsets)

    return list(merged.values())
