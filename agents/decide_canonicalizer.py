"""solar-decide(분류형, /v1/systemone)로 '인물 정리' 두 가지를 한 번의 호출로 처리하는 canonicalize_new_characters 대체 구현.

  (a) 새 이름이 '특정 개인의 이름'인가, 직업·관계로 부르는 '일반 지칭'인가  → 일반 지칭이면 제거 대상
  (b) 새 이름 × 기존 후보가 '같은 인물'인가                                  → 같으면 병합

기존 구현(verifier_agent.canonicalize_new_characters)은 LLM 이 JSON 을 '생성'하고 파싱한다(형식 오류·실행마다 편차).
여기서는 선택지 확률을 받아 임계값으로 보수성을 조절한다. 호출은 경계선당 1회(질문 N개), 입력은 이름+짧은 설명뿐이다.

입출력 규약은 원본과 동일: ({새 인물 원래 이름: 최종 대표 이름}, {이전 대표 이름: 새 대표 이름}).
추가로 '일반 지칭으로 판정되어 버려야 할 이름'은 pop_dropped_names(registry)로 받아 drop_entities(result, names)로 결과에서 제거한다.
정적 별칭 테이블 적용, 레지스트리 제자리 갱신, 실패 시 '전부 유지·새 인물 등록'(오탐 방지) 정책은 원본과 같다.

환경변수: DECIDE_SAME_THRESHOLD(기본 0.5, 이 값 이상이면 병합), DECIDE_PERSON_THRESHOLD(기본 0.3, 미만이면 일반 지칭으로 제거),
          DECIDE_PERSON_FILTER(기본 1, 0이면 (a) 생략)
"""
from __future__ import annotations

import os
import time

import requests

from agents.character_aliases import load_character_alias_map
from agents.config import UPSTAGE_API_KEY
from agents.verifier_agent import _preferred_canonical, _select_candidates

SAME_THRESHOLD = float(os.getenv("DECIDE_SAME_THRESHOLD", "0.5"))
PERSON_THRESHOLD = float(os.getenv("DECIDE_PERSON_THRESHOLD", "0.3"))
PERSON_FILTER = os.getenv("DECIDE_PERSON_FILTER", "1") != "0"
_CACHE: dict | None = None  # 평가 시 동일 요청 재호출을 피하기 위한 선택적 캐시
STATS = {"calls": 0, "seconds": 0.0}
_DROPPED: dict[int, set[str]] = {}  # 레지스트리 객체별로 지금까지 일반 지칭으로 판정된 이름

_PERSON_DEF = (
    "일반 지칭이란 고유한 이름 없이 직업·관계·신분·외형으로만 부르는 표기입니다(예: 순경, 이웃 남자, 약사, 하인). "
    "성이나 이름이 하나라도 있거나 그 이름에 호칭이 붙은 표기(예: 무어 박사, 존스 경감, 톰 장로)는 개인 이름입니다. "
    "대부분의 표기는 개인 이름입니다."
)
_PERSON_INSTR = "'{a}'은(는) 개인 이름입니까? " + _PERSON_DEF + " 개인 이름이면 yes, 일반 지칭이면 no."
_SAME_INSTR = (
    "'{a}'와(과) '{b}'는 같은 사람을 가리킵니까? "
    "표기 변형(음역 차이, 성만/이름만 부르기, 직함·괄호 설명 추가, 별명)이면 yes. "
    "성이 같아도 서로 다른 사람(가족·친척 등)이거나 직함·직업만 비슷하면 no."
)


def _post(state: str, questions: dict) -> dict:
    key = repr((state, sorted(questions.items()))) if _CACHE is not None else None
    if key is not None and key in _CACHE:
        return _CACHE[key]
    t0 = time.time()
    for attempt in range(7):
        resp = requests.post(
            "https://api.upstage.ai/v1/systemone",
            headers={"Authorization": f"Bearer {UPSTAGE_API_KEY}"},
            json={"model": "solar-decide", "state": state, "questions": questions},
            timeout=120,
        )
        if resp.status_code not in (429, 500, 502, 503, 504) or attempt == 6:
            break
        time.sleep(10 * 2**attempt)
    resp.raise_for_status()
    out = resp.json()["answers"]
    STATS["calls"] += 1
    STATS["seconds"] += time.time() - t0
    if key is not None:
        _CACHE[key] = out
    return out


def _short(text: str, n: int = 140) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= n else text[:n] + "…"


def pop_dropped_names(canonical_registry: list[dict]) -> set[str]:
    """이 레지스트리에서 지금까지 일반 지칭으로 판정된 이름 전체(누적). 매 경계선에서 결과에 적용한다."""
    return set(_DROPPED.get(id(canonical_registry), set()))


def drop_entities(result: dict, names: set[str]) -> dict:
    """일반 지칭으로 판정된 이름을 인물·관계·사건에서 제거한다."""
    if not names:
        return result
    characters = [c for c in result.get("characters", []) if c.get("name") not in names]
    relations = [
        r for r in result.get("relations", []) if r.get("source") not in names and r.get("target") not in names
    ]
    events = []
    for e in result.get("events", []):
        parts = [
            p for p in e.get("participants", [])
            if (p.get("character_name") if isinstance(p, dict) else p) not in names
        ]
        if parts or not e.get("participants"):
            events.append({**e, "participants": parts})
    return {**result, "characters": characters, "relations": relations, "events": events}


def canonicalize_new_characters(
    new_characters: list[dict],
    canonical_registry: list[dict],
    book_id: str | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    if not new_characters:
        return {}, {}

    def _register_as_new(c: dict) -> str:
        name = c.get("name", "")
        canonical_registry.append(
            {"name": name, "description": c.get("description", ""), "evidence": c.get("evidence", "")}
        )
        return name

    json_alias_map = load_character_alias_map(book_id)
    registry_names = {c.get("name", "") for c in canonical_registry}

    result_map: dict[str, str] = {}
    still_new: list[dict] = []
    for c in new_characters:
        name = c.get("name", "")
        alias_target = json_alias_map.get(name)
        if not alias_target:
            still_new.append(c)
            continue
        if alias_target not in registry_names:
            canonical_registry.append(
                {"name": alias_target, "description": c.get("description", ""), "evidence": c.get("evidence", "")}
            )
            registry_names.add(alias_target)
        result_map[name] = alias_target
    new_characters = [c for c in still_new if c.get("name")]
    if not new_characters:
        return result_map, {}

    # 신규별 후보(이름 유사 + 최근 등록) — 원본과 동일한 후보 추림 로직 재사용
    cands_per_new = [_select_candidates(c["name"], canonical_registry) if canonical_registry else [] for c in new_characters]
    uniq: list[dict] = []
    seen: set[str] = set()
    for cands in cands_per_new:
        for cand in cands:
            if cand.get("name") and cand["name"] not in seen:
                seen.add(cand["name"])
                uniq.append(cand)

    described: dict[str, str] = {}
    for c in list(new_characters) + uniq:
        if c.get("name") and c["name"] not in described:
            described[c["name"]] = _short(c.get("description", ""))
    state = "인물 설명:\n" + "\n".join(f"- {n}: {d}" for n, d in described.items())
    eidx = {c["name"]: e for e, c in enumerate(uniq)}

    questions: dict[str, dict] = {}
    for n, c in enumerate(new_characters):
        if PERSON_FILTER:
            questions[f"p{n}"] = {
                "type": "choice",
                "instructions": _PERSON_INSTR.format(a=c["name"]),
                "criteria": {"yes": "개인 이름이다.", "no": "일반 지칭이다."},
            }
        for cand in cands_per_new[n]:
            e = eidx.get(cand.get("name", ""))
            if e is None or cand["name"] == c["name"]:
                continue
            questions[f"n{n}e{e}"] = {
                "type": "choice",
                "instructions": _SAME_INSTR.format(a=c["name"], b=cand["name"]),
                "criteria": {"yes": "같은 사람이다.", "no": "다른 사람이다."},
            }

    probs: dict[str, float] = {}
    if questions:
        try:
            ans = _post(state, questions)
            probs = {k: v["probabilities"].get("yes", 0.0) for k, v in ans.items()}
        except Exception:  # noqa: BLE001 - 실패 시 안전하게: 아무것도 제거·병합하지 않고 전부 새 인물로 등록
            probs = {}

    dropped = _DROPPED.setdefault(id(canonical_registry), set())
    existing_names = {c["name"] for c in canonical_registry}
    rename_map: dict[str, str] = {}
    applied_renames: dict[str, str] = {}
    for n, c in enumerate(new_characters):
        name = c["name"]
        if PERSON_FILTER and f"p{n}" in probs and probs[f"p{n}"] < PERSON_THRESHOLD:
            dropped.add(name)  # 일반 지칭 — 등록·병합하지 않고 호출부가 결과에서 제거
            continue
        best, best_p = None, 0.0
        for cand in cands_per_new[n]:
            e = eidx.get(cand.get("name", ""))
            p = probs.get(f"n{n}e{e}", 0.0) if e is not None else 0.0
            if p > best_p:
                best, best_p = cand["name"], p
        if best is not None and best_p >= SAME_THRESHOLD:
            match_to = applied_renames.get(best, best)
            if match_to in existing_names:
                preferred = _preferred_canonical([match_to, name])
                final_name = match_to
                if preferred != match_to:  # 더 구체적인 표기가 있으면 대표 이름 교체(규칙 기반)
                    for entry in canonical_registry:
                        if entry.get("name") == match_to:
                            entry["name"] = preferred
                            break
                    existing_names.discard(match_to)
                    existing_names.add(preferred)
                    applied_renames[match_to] = preferred
                    rename_map[match_to] = preferred
                    final_name = preferred
                result_map[name] = final_name
                continue
        result_map[name] = _register_as_new(c)
    return result_map, rename_map


def classify_generic_names(
    new_characters: list[dict],
    canonical_registry: list[dict],
    book_id: str | None = None,
) -> set[str]:
    """하이브리드용: 새 이름이 '일반 지칭'인지만 solar-decide 로 판별한다(질문 = 새 이름 수, 호출 1회).

    일반 지칭으로 판정된 이름은 레지스트리별 누적 집합에 기록되며(pop_dropped_names), 호출부가 결과에서 제거하고
    동일 인물 병합(기존 LLM 방식)에는 넘기지 않는다. 별칭 표에 있는 이름은 판별 대상에서 제외하고, 실패 시 아무것도 제거하지 않는다.
    """
    alias_map = load_character_alias_map(book_id)
    targets = [c for c in new_characters if c.get("name") and c["name"] not in alias_map]
    if not PERSON_FILTER or not targets:
        return set()
    state = "인물 설명:\n" + "\n".join(f"- {c['name']}: {_short(c.get('description', ''))}" for c in targets)
    questions = {
        f"p{n}": {
            "type": "choice",
            "instructions": _PERSON_INSTR.format(a=c["name"]),
            "criteria": {"yes": "개인 이름이다.", "no": "일반 지칭이다."},
        }
        for n, c in enumerate(targets)
    }
    try:
        ans = _post(state, questions)
    except Exception:  # noqa: BLE001 - 실패 시 안전하게 아무것도 제거하지 않음
        return set()
    flagged = {
        c["name"]
        for n, c in enumerate(targets)
        if f"p{n}" in ans and ans[f"p{n}"]["probabilities"].get("yes", 1.0) < PERSON_THRESHOLD
    }
    _DROPPED.setdefault(id(canonical_registry), set()).update(flagged)
    return flagged
