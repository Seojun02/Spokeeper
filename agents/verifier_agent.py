import json
import re
from langchain_upstage import ChatUpstage
from langchain_core.messages import SystemMessage, HumanMessage

from agents.config import UPSTAGE_API_KEY
from agents.build_agent import extract_json_from_text
from agents.character_aliases import load_character_alias_map
from agents.llm_utils import invoke_with_retry


VERIFIER_SYSTEM_PROMPT = """
당신은 SpoKeeper의 VerifierAgent입니다 (읽기 경로 1차 가드).

역할:
- BuildAgent가 추출한 인물/관계/사건 각 항목에 붙은 evidence(근거 문장)가
  실제로 그 항목의 내용을 뒷받침하는지 검증합니다.
- evidence가 비어있거나, 항목 내용과 무관하거나, evidence 자체가 추측/해석이면
  invalid로 판정합니다.
- 근거가 명확한 항목만 valid로 남깁니다. 새로운 정보를 추가하거나 추측하지 않습니다.

출력은 반드시 아래 JSON 형식으로만 작성하세요.

{
  "valid_relation_keys": ["source|target|relation", ...],
  "valid_event_summaries": ["사건 요약 원문", ...],
  "invalid_event_roles": [
    {"event_summary": "사건 요약 원문", "character_name": "인물명", "role": "역할명"}
  ]
}
"""


_STRONG_EVENT_ROLES = {
    "perpetrator",
    "victim",
    "suspect",
    "accomplice",
    "target",
    "threatened",
    "threatener",
    "deceiver",
    "deceived",
    "concealer",
}


CHARACTER_MATCH_SYSTEM_PROMPT = """
당신은 SpoKeeper의 VerifierAgent입니다. 여기서 맡은 역할은 "새로 등장한 인물이
이미 알고 있는 인물 중 하나와 같은 사람인지 판단"하는 것입니다.

배경:
이미 여러 구간에 걸쳐 확정된 인물 목록(existing_characters)이 있습니다. 이번에
새로 추출된 인물(new_characters) 각각에 대해, existing_characters 중 하나와
표기만 다를 뿐 실제로는 같은 사람인지, 아니면 처음 등장하는 새로운 인물인지
판단하세요. **전체 목록을 다시 클러스터링하는 게 아니라, 새 인물 각각을 기존
목록과만 비교**하면 됩니다 — 목록이 커져도 비교 범위는 항상 "새 인물 수" 정도로
작게 유지됩니다.

절대 규칙:
- 이름 문자열이 비슷하거나 겹친다는 이유만으로 매칭하지 마세요. 반드시 각 인물의
  description/evidence 내용을 읽고, 실제로 같은 사람을 가리키는지 확인한 뒤에만
  매칭하세요.
- 성이나 일부 음절이 겹치는 서로 다른 인물(예: 형제자매, 부부, 우연히 성이 같은
  타인)은 절대 매칭하지 않습니다.
- 번역/음역 표기 차이(예: 모음 하나 차이로 갈리는 외래어 이름)는 같은 인물일
  가능성이 높으니 description/evidence 맥락이 일치하면 매칭하세요.
- 한국식 이름은 성을 뗀 이름만으로 불리는 경우가 흔합니다(예: "박태수"를 그냥
  "태수"라고 부름). 이것도 표기 차이일 뿐이니, description/evidence 맥락이
  일치하면 같은 인물로 매칭하세요 — 다만 그 이름만으로 다른 사람과 혼동될
  근거가 있으면(예: 흔한 이름이라 여러 인물이 있을 가능성) 매칭하지 마세요.
- 확실하지 않으면(애매하면) 매칭하지 않고 새 인물로 등록하는 쪽을 선택하세요 —
  잘못 합치는 것이 안 합치는 것보다 훨씬 나쁩니다.

판단 예시 (참고용이며, 실제 판단은 항상 주어진 description/evidence를 따르세요):

예시 1 — 같은 인물, 직함 유무 차이
  existing: "제임스 모티머 박사" (description: "M.R.C.S. 자격을 가진 의사, 지팡이 주인")
  new: "제임스 모티머" (description: "지팡이를 두고 간 방문객, 의사")
  판단: 같은 인물 → match_to: "제임스 모티머 박사"

예시 2 — 같은 인물, 애칭/축약
  existing: "셜록 홈즈" (description: "베이커가에 사는 탐정, 왓슨의 동료")
  new: "홈즈" (description: "추리하는 탐정")
  판단: 같은 인물 → match_to: "셜록 홈즈"

예시 3 — 성만 겹치는 다른 인물 (매칭 금지)
  existing: "존스 형사" (description: "런던 경찰청 소속 수사관")
  new: "톰슨 존스" (description: "피해자의 이웃, 목격자")
  판단: 다른 인물 → match_to: null

예시 4 — 가족 관계 (매칭 금지)
  existing: "왓슨" (description: "주인공의 동료 의사")
  new: "왓슨 부인" (description: "왓슨의 아내")
  판단: 다른 인물 → match_to: null

예시 5 — 같은 인물, 한국식 이름의 성 생략
  existing: "김민준" (description: "주인공의 대학 동기, 회사원")
  new: "민준" (description: "다른 인물들이 그를 부르는 이름, 같은 회사 동료")
  판단: 같은 인물 (같은 역할·맥락, 성만 생략된 표기) → match_to: "김민준", preferred_display_name: "김민준"

같은 인물로 판단했다면(match_to가 null이 아니면) preferred_display_name도 반드시
채우세요 — existing 쪽 이름과 new 쪽 이름 중, 그리고 그 둘을 조합한 표기 중에서
이 인물을 가장 명확하고 자연스럽게 나타내는 대표 이름을 고르세요(직함/성이 포함된
쪽이 보통 더 명확합니다. 예: "민준"보다 "김민준", "홈즈"보다 "셜록 홈즈"). 특별히
더 나은 표기가 없으면 그냥 match_to와 동일한 값을 쓰세요. match_to가 null이면
preferred_display_name도 null로 두세요.

출력은 반드시 아래 JSON 형식으로만 작성하세요. new_characters 전부에 대해 하나씩
판정하세요 (매칭 안 되면 match_to와 preferred_display_name을 모두 null로).

{
  "matches": [
    {
      "new_name": "새 인물 이름",
      "match_to": "기존 대표 이름 또는 null",
      "preferred_display_name": "매칭된 경우 최종 대표 이름(match_to와 같아도 됨) 또는 null"
    }
  ]
}
"""


_HONORIFIC_SUFFIXES = (
    "씨",
    "님",
    "군",
    "양",
    "경",
)
_TITLE_SUFFIXES = (
    "박사",
    "교수",
    "선생",
    "형사",
    "경감",
    "경위",
)
_FAMILY_OR_ROLE_WORDS = (
    "부인",
    "아내",
    "남편",
    "아버지",
    "어머니",
    "딸",
    "아들",
    "형",
    "누나",
    "언니",
    "동생",
    "가정부",
    "하인",
)
_GENERIC_REFERENCES = {"나", "화자", "서술자", "주인공"}


def _normalize_alias_text(name: str) -> str:
    """표기 흔들림 비교용 이름 정규화. 표시 이름 자체는 바꾸지 않는다."""
    text = (name or "").strip()
    text = re.sub(r"[\"'“”‘’.,!?]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _without_parentheses(name: str) -> str:
    return re.sub(r"\([^)]*\)", "", name or "").strip()


def _strip_suffixes(name: str) -> str:
    text = _without_parentheses(_normalize_alias_text(name))
    changed = True
    while changed:
        changed = False
        for suffix in _HONORIFIC_SUFFIXES + _TITLE_SUFFIXES:
            if text.endswith(suffix) and len(text) > len(suffix):
                text = text[: -len(suffix)].strip()
                changed = True
    return text


def _alias_key(name: str) -> str:
    return re.sub(r"\s+", "", _strip_suffixes(name)).lower()


def _parenthetical_aliases(name: str) -> list[str]:
    aliases: list[str] = []
    for raw in re.findall(r"\(([^)]*)\)", name or ""):
        alias = raw.strip()
        if alias and alias not in _GENERIC_REFERENCES:
            aliases.append(alias)
    return aliases


def _is_generic_reference(name: str) -> bool:
    return _strip_suffixes(name) in _GENERIC_REFERENCES


def _has_family_or_role_word(name: str) -> bool:
    stripped = _strip_suffixes(name)
    return any(word in stripped for word in _FAMILY_OR_ROLE_WORDS)


_HANGUL_RE = re.compile(r"^[가-힣]+$")


def _short_alias_candidates(canonical: str) -> set[str]:
    """짧은 표기(성 생략 등)로 흔히 불리는 별칭 후보를 결정론적으로 계산한다.
    LLM 판단 없이 항상 동일하게 적용되므로, 실행마다 결과가 흔들리지 않는다.

    - 서양식 "성 이름"(공백 구분) 표기: 마지막 토큰(성)을 별칭으로 본다
      (예: "Sherlock Holmes" -> "Holmes").
    - 한국식 3글자 이름(성 1자 + 이름 2자, 붙여 쓰기) 표기: 이름 2글자를
      별칭으로 본다(예: "윤가람" -> "가람"). 특정 작품의 이름을 하드코딩한 게
      아니라 이름 길이·한글 여부만으로 판단하는 일반 규칙이라 어떤 소설에도
      동일하게 적용된다.
    """
    if _has_family_or_role_word(canonical):
        return set()

    base = _strip_suffixes(canonical)
    parts = [part for part in base.split(" ") if part]

    if len(parts) >= 2:
        return {parts[-1]}

    if len(parts) == 1 and len(parts[0]) == 3 and _HANGUL_RE.match(parts[0]):
        return {parts[0][1:]}

    return set()


def _canonical_score(name: str) -> tuple[int, int, int]:
    stripped = _without_parentheses(_normalize_alias_text(name))
    return (
        0 if _is_generic_reference(name) else 1,
        1 if " " in stripped else 0,
        len(stripped),
    )


def _preferred_canonical(names: list[str]) -> str:
    return max(names, key=_canonical_score)


def _normalize_canonical_display(name: str) -> str:
    return (name or "").strip()


def _deduplicate_relations(relations: list[dict]) -> list[dict]:
    seen = set()
    result = []

    for relation in relations:
        key = (
            relation.get("source", ""),
            relation.get("target", ""),
            relation.get("relation", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(relation)

    return result


def _deduplicate_events(events: list[dict]) -> list[dict]:
    seen = set()
    result = []

    for event in events:
        participants = event.get("participants", [])
        participant_key = tuple(
            (
                participant.get("character_name", ""),
                participant.get("role", ""),
            )
            if isinstance(participant, dict)
            else (participant, "")
            for participant in participants
        )
        key = (
            event.get("event_id") or event.get("event_name") or event.get("summary", ""),
            participant_key,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(event)

    return result


def _apply_transitive_map(name_map: dict[str, str]) -> dict[str, str]:
    resolved: dict[str, str] = {}

    for name in name_map:
        current = name
        visited = set()
        while current in name_map and name_map[current] != current and current not in visited:
            visited.add(current)
            current = name_map[current]
        resolved[name] = current

    return resolved


def _augment_identity_map_with_alias_rules(
    characters: list[dict],
    identity_map: dict[str, str],
) -> dict[str, str]:
    """
    LLM이 놓치기 쉬운 안전한 표기 차이를 보정한다 — 존칭/직함 유무(예: "OO 박사"/"OO"),
    괄호 안 별칭(예: "화자(이름)") 등 순수 문자열/문법 패턴만으로 판단 가능한 경우만
    다룬다. 특정 작품의 인물명을 하드코딩하지 않아 어떤 소설에도 그대로 적용된다.
    """
    names = [c.get("name", "").strip() for c in characters if c.get("name")]
    if len(names) < 2:
        return identity_map

    result = dict(identity_map)
    alias_to_names: dict[str, list[str]] = {}

    for name in names:
        keys = {_alias_key(name)}
        keys.update(_alias_key(alias) for alias in _parenthetical_aliases(name))
        for key in keys:
            if key:
                alias_to_names.setdefault(key, []).append(name)

    for grouped_names in alias_to_names.values():
        unique_names = list(dict.fromkeys(grouped_names))
        if len(unique_names) < 2:
            continue
        canonical = _preferred_canonical([result.get(name, name) for name in unique_names])
        canonical = _normalize_canonical_display(canonical)
        for name in unique_names:
            result[name] = canonical

    for name, canonical in list(result.items()):
        normalized = _normalize_canonical_display(canonical)
        result[name] = normalized
        if normalized != canonical and canonical in result:
            result[canonical] = normalized

    canonical_names = sorted(set(result.values()), key=len, reverse=True)
    short_alias_to_canonical: dict[str, str | None] = {}

    for canonical in canonical_names:
        aliases = _short_alias_candidates(canonical)
        if not aliases:
            continue

        for alias in aliases:
            key = _alias_key(alias)
            existing = short_alias_to_canonical.get(key)
            if existing is None and key in short_alias_to_canonical:
                continue
            if existing and existing != canonical:
                short_alias_to_canonical[key] = None
            else:
                short_alias_to_canonical[key] = canonical

    for name in names:
        if result.get(name, name) != name:
            continue
        key = _alias_key(name)
        canonical = short_alias_to_canonical.get(key)
        if canonical and canonical != name:
            result[name] = canonical

    # "화자(왓슨)"처럼 괄호 안 별칭이 기존 인물명과 맞으면 연결한다.
    alias_key_to_canonical = {
        _alias_key(name): result.get(canonical, canonical)
        for name, canonical in result.items()
    }
    for name in names:
        if result.get(name, name) != name:
            continue
        for alias in _parenthetical_aliases(name):
            canonical = alias_key_to_canonical.get(_alias_key(alias))
            if canonical:
                result[name] = canonical
                break

    return _apply_transitive_map(result)


def _has_common_substring(a: str, b: str, min_len: int = 2) -> bool:
    """이름 두 개가 min_len자 이상 겹치는 부분 문자열을 공유하는지 확인한다.
    최종 병합 여부를 이걸로 결정하지는 않는다(그건 항상 LLM 몫) — 단지 LLM에게
    보여줄 후보를 추리는 용도라서, 오탐 위험 없이 관대하게 잡아도 된다."""
    a = a.replace(" ", "")
    b = b.replace(" ", "")
    if len(a) < min_len or len(b) < min_len:
        return a != "" and (a in b or b in a)
    return any(a[i : i + min_len] in b for i in range(len(a) - min_len + 1))


def _select_candidates(
    new_name: str, canonical_registry: list[dict], recent_n: int = 8, max_candidates: int = 15
) -> list[dict]:
    """canonical_registry 전체 대신, new_name과 이름이 겹치는 인물 + 최근에 등록된
    인물만 후보로 추린다. 책 후반부로 갈수록 canonical_registry가 커지면서 LLM이
    한 번에 봐야 하는 비교 대상이 커져 표기 변형 같은 미묘한 매칭을 놓치는 문제를
    막기 위함이다(문서·책 종류와 무관하게 항상 적용되는 일반 로직)."""
    recent = canonical_registry[-recent_n:]
    similar = [c for c in canonical_registry if _has_common_substring(new_name, c.get("name", ""))]

    combined: list[dict] = []
    seen_names: set[str] = set()
    for c in similar + recent:
        name = c.get("name", "")
        if name and name not in seen_names:
            seen_names.add(name)
            combined.append(c)

    return combined[:max_candidates]


def canonicalize_new_characters(
    new_characters: list[dict],
    canonical_registry: list[dict],
    book_id: str | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """
    new_characters(이번 경계선에서 새로 등장한 인물만)를 canonical_registry(지금까지
    확정된 대표 인물 목록)와 비교해서, 기존 인물과 매칭되면 그 대표 이름으로,
    아니면 새 인물로 canonical_registry에 등록한다(제자리에서 append).

    매 경계선마다 누적된 전체 인물을 통째로 재판단하지 않고 "새로 나온 몇 명만"
    비교하므로, 인물 수가 아무리 늘어나도 한 번에 LLM에 보여주는 "새 인물" 쪽은
    항상 작게 유지된다. "기존 인물" 쪽도 이름 유사도 + 최근 등장 기준으로 후보를
    추려서(`_select_candidates`) 양쪽 다 작게 유지한다.

    book_id가 주어지면 backend/data/character_aliases의 정적 별칭 테이블(있으면)을
    먼저 적용해 LLM 호출 없이 확실한 별칭부터 해결한다 — 파일이 없는 새 책은 그냥
    빈 매핑이라 전부 LLM 판단으로 넘어가므로, 특정 책에 대한 하드코딩 없이 어떤
    소설에도 그대로 동작한다.

    매칭 판정과 같은 LLM 호출에서 "둘 중 어느 표기를 대표 이름으로 쓸지"
    (preferred_display_name)까지 같이 판단한다 — 기존에 먼저 등록된 이름을
    무조건 대표 이름으로 고정하지 않고, LLM이 더 명확한 표기(예: 성+이름,
    직함 포함)를 고를 수 있게 한다. 대표 이름이 바뀌면 canonical_registry의
    해당 항목 이름도 그 자리에서 바꿔쓴다.

    반환값: ({새 인물 원래 이름: 최종 대표 이름}, {이전 대표 이름: 새 대표 이름} —
    이번 호출에서 대표 이름이 바뀐 경우만 포함. 호출자는 이미 만들어둔 과거 결과물에도
    이 rename을 소급 적용해야 한다.)
    """
    if not new_characters:
        return {}, {}

    if not UPSTAGE_API_KEY:
        raise ValueError("UPSTAGE_API_KEY가 설정되지 않았습니다.")

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

    new_characters = still_new
    if not new_characters:
        return result_map, {}

    if not canonical_registry:
        # 최초 등장 — 비교 대상이 없으니 전부 새 인물로 등록
        result_map.update({c.get("name", ""): _register_as_new(c) for c in new_characters if c.get("name")})
        return result_map, {}

    llm_factory = lambda: ChatUpstage(model="solar-pro2", api_key=UPSTAGE_API_KEY, temperature=0, timeout=120)

    candidates: list[dict] = []
    seen_candidate_names: set[str] = set()
    for c in new_characters:
        for cand in _select_candidates(c.get("name", ""), canonical_registry):
            name = cand.get("name", "")
            if name and name not in seen_candidate_names:
                seen_candidate_names.add(name)
                candidates.append(cand)

    payload = {
        "existing_characters": [
            {"name": c["name"], "description": c.get("description", ""), "evidence": c.get("evidence", "")}
            for c in candidates
        ],
        "new_characters": [
            {
                "name": c.get("name", ""),
                "description": c.get("description", ""),
                "evidence": c.get("evidence", ""),
            }
            for c in new_characters
        ],
    }

    response = invoke_with_retry(
        llm_factory,
        [
            SystemMessage(content=CHARACTER_MATCH_SYSTEM_PROMPT),
            HumanMessage(
                content=f"""
new_characters 각각이 existing_characters 중 하나와 같은 인물인지 판단하세요.

{json.dumps(payload, ensure_ascii=False, indent=2)}
"""
            ),
        ],
    )

    result = extract_json_from_text(response.content)
    if not isinstance(result, dict) or result.get("parse_error"):
        # 파싱 실패 시 안전하게(오탐 방지) 전부 새 인물로 등록
        for c in new_characters:
            name = c.get("name", "")
            if name:
                result_map[name] = _register_as_new(c)
        return result_map, {}

    matches = {
        m.get("new_name"): (
            m.get("match_to"),
            (m.get("preferred_display_name") or "").strip() or None,
        )
        for m in result.get("matches", [])
        if isinstance(m, dict)
    }
    existing_names = {c["name"] for c in canonical_registry}
    rename_map: dict[str, str] = {}
    # 같은 배치 안에서 이미 대표 이름이 바뀐 기존 인물을 가리키는 match_to를
    # 새 이름으로 다시 연결하기 위한 체이닝 — LLM은 이 배치를 만들 때의 옛
    # existing_characters 이름 기준으로만 판단했으므로 match_to가 옛 이름일 수 있다.
    applied_renames: dict[str, str] = {}

    for c in new_characters:
        name = c.get("name", "")
        if not name:
            continue
        match_to, preferred = matches.get(name, (None, None))
        if match_to:
            match_to = applied_renames.get(match_to, match_to)
        if match_to and match_to in existing_names:
            final_name = match_to
            if preferred and preferred != match_to:
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
        else:
            result_map[name] = _register_as_new(c)

    return result_map, rename_map


def _names_from_build_result(build_result: dict) -> list[dict]:
    seen = set()
    result: list[dict] = []

    def add(name: str, description: str = "", evidence: str = "") -> None:
        name = (name or "").strip()
        if not name or name in seen:
            return
        seen.add(name)
        result.append({"name": name, "description": description, "evidence": evidence})

    for character in build_result.get("characters", []):
        add(
            character.get("name", ""),
            character.get("description", ""),
            character.get("evidence", ""),
        )

    for relation in build_result.get("relations", []):
        evidence = relation.get("evidence", "")
        add(relation.get("source", ""), evidence=evidence)
        add(relation.get("target", ""), evidence=evidence)

    for event in build_result.get("events", []):
        evidence = event.get("evidence", "")
        for participant in event.get("participants", []):
            if isinstance(participant, dict):
                add(participant.get("character_name", ""), evidence=evidence)
            else:
                add(participant, evidence=evidence)

    return result


def _build_name_lookup(name_map: dict[str, str]) -> dict[str, str]:
    lookup: dict[str, str] = {}

    for name, canonical in name_map.items():
        canonical = _normalize_canonical_display(canonical)
        keys = {_alias_key(name), _alias_key(canonical)}
        keys.update(_alias_key(alias) for alias in _short_alias_candidates(canonical))
        for key in keys:
            if key and key not in lookup:
                lookup[key] = canonical

    return lookup


def _resolve_name(name: str, name_map: dict[str, str], lookup: dict[str, str]) -> str:
    if not name:
        return name
    if name in name_map:
        return _normalize_canonical_display(name_map[name])
    direct = lookup.get(_alias_key(name))
    if direct:
        return direct
    for alias in _parenthetical_aliases(name):
        canonical = lookup.get(_alias_key(alias))
        if canonical:
            return canonical
    return _normalize_canonical_display(name)


def _apply_character_name_map(
    build_result: dict,
    name_map: dict[str, str],
) -> tuple[dict, list[dict], list[dict], list[dict]]:
    characters = build_result.get("characters", [])
    relations = build_result.get("relations", [])
    events = build_result.get("events", [])
    lookup = _build_name_lookup(name_map)

    merged_characters: dict[str, dict] = {}
    for character in characters:
        name = character.get("name", "")
        canonical = _resolve_name(name, name_map, lookup)
        if canonical not in merged_characters:
            merged_characters[canonical] = {**character, "name": canonical}
            continue

        existing = merged_characters[canonical]
        if not existing.get("description") and character.get("description"):
            existing["description"] = character.get("description")
        if not existing.get("evidence") and character.get("evidence"):
            existing["evidence"] = character.get("evidence")

    characters = list(merged_characters.values())
    relations = _deduplicate_relations(
        [
            {
                **relation,
                "source": _resolve_name(relation.get("source", ""), name_map, lookup),
                "target": _resolve_name(relation.get("target", ""), name_map, lookup),
            }
            for relation in relations
        ]
    )
    events = _deduplicate_events(
        [
            {
                **event,
                "participants": [
                    {
                        **participant,
                        "character_name": _resolve_name(
                            participant.get("character_name") or participant.get("name", ""),
                            name_map,
                            lookup,
                        ),
                    }
                    if isinstance(participant, dict)
                    else _resolve_name(participant, name_map, lookup)
                    for participant in event.get("participants", [])
                ],
            }
            for event in events
        ]
    )

    build_result = {
        **build_result,
        "characters": characters,
        "relations": relations,
        "events": events,
    }
    return build_result, characters, relations, events


def verify_build_result(build_result: dict, book_id: str | None = None) -> dict:
    """
    build_result(누적된 characters/relations/events)의 relations/events에 붙은
    evidence가 실제로 내용을 뒷받침하는지 검증해서, 근거가 확인된 것만 남긴다.

    인물 이름 병합은 이 함수의 책임이 아니다 — precompute.py의 경계선 루프에서
    canonicalize_new_characters(증분 비교) + ConsolidationAgent(주기적 전체
    재정리)로 별도 처리되고, 이 함수에 들어오는 build_result는 이미 그 결과가
    적용된 상태다. 다만 `_augment_identity_map_with_alias_rules`가 놓치기 쉬운
    존칭/직함/괄호 별칭 같은 문법 패턴은 저비용으로 한 번 더 보정한다.
    """
    characters = build_result.get("characters", [])
    relations = build_result.get("relations", [])
    events = build_result.get("events", [])

    if not UPSTAGE_API_KEY:
        raise ValueError("UPSTAGE_API_KEY가 설정되지 않았습니다.")

    name_map = _augment_identity_map_with_alias_rules(
        _names_from_build_result(build_result),
        {c.get("name", ""): c.get("name", "") for c in characters if c.get("name")},
    )
    if name_map:
        build_result, characters, relations, events = _apply_character_name_map(
            build_result,
            name_map,
        )

    if not relations and not events:
        return {**build_result, "relations": relations, "events": events, "verifier_raw_response": None}

    llm_factory = lambda: ChatUpstage(
        model="solar-pro2",
        api_key=UPSTAGE_API_KEY,
        temperature=0,
        timeout=120,
    )

    payload = {
        "relations": [
            {
                "key": f"{r.get('source', '')}|{r.get('target', '')}|{r.get('relation', '')}",
                "relation": r.get("relation", ""),
                "evidence": r.get("evidence", ""),
            }
            for r in relations
        ],
        "events": [
            {
                "summary": e.get("event_summary") or e.get("summary", ""),
                "event_name": e.get("event_name", ""),
                "evidence": e.get("evidence", ""),
                "participants": e.get("participants", []),
            }
            for e in events
        ],
    }

    response = invoke_with_retry(
        llm_factory,
        [
            SystemMessage(content=VERIFIER_SYSTEM_PROMPT),
            HumanMessage(
                content=f"""
다음 relations/events 각각의 evidence가 실제로 내용을 뒷받침하는지 검증하세요.

{json.dumps(payload, ensure_ascii=False, indent=2)}
"""
            ),
        ],
    )

    result = extract_json_from_text(response.content)
    if not isinstance(result, dict):
        return {**build_result, "verifier_raw_response": response.content}

    valid_keys = set(result.get("valid_relation_keys", []))
    valid_summaries = set(result.get("valid_event_summaries", []))

    # 파싱 실패(parse_error)면 안전한 쪽으로 아무것도 버리지 않는다 (과도한 억제 방지).
    if result.get("parse_error"):
        return {**build_result, "verifier_raw_response": response.content}

    filtered_relations = [
        r
        for r in relations
        if f"{r.get('source', '')}|{r.get('target', '')}|{r.get('relation', '')}" in valid_keys
    ]
    invalid_roles = {
        (
            item.get("event_summary", ""),
            item.get("character_name", ""),
            item.get("role", ""),
        )
        for item in result.get("invalid_event_roles", [])
        if isinstance(item, dict)
    }
    filtered_events = []
    for event in events:
        summary = event.get("event_summary") or event.get("summary", "")
        if summary not in valid_summaries:
            continue
        participants = []
        for participant in event.get("participants", []):
            if not isinstance(participant, dict):
                participants.append(participant)
                continue
            role = participant.get("role", "")
            name = participant.get("character_name", "")
            if (summary, name, role) in invalid_roles:
                continue
            if role in _STRONG_EVENT_ROLES and not event.get("evidence"):
                participant = {**participant, "confidence": min(float(participant.get("confidence", 0.5)), 0.35)}
            participants.append(participant)
        filtered_events.append({**event, "participants": participants})

    return {
        **build_result,
        "relations": filtered_relations,
        "events": filtered_events,
        "verifier_raw_response": response.content,
    }
