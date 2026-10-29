"""solar-decide 질문으로 '인물이 아닌 항목'을 걸러내는 범용 검사. 단어 목록·접미사 같은 규칙은 쓰지 않는다.

새로 나온 이름마다 같은 4개 질문을 보내 확률을 받고, 기준 미만이면 제거 대상으로 본다.
  person  개인 이름인가?                  (직업·외형·관계로만 부르는 일반 지칭을 거른다)
  single  한 명(한 마리)을 가리키는가?     (둘 이상을 묶은 표현, 가문, 무리, 단체를 거른다)
  inplot  이 이야기의 사건에 관여하는가?   (다른 작품의 인물, 실존 작가처럼 언급·비교만 되는 이름을 거른다)
  human   이야기 세계에 실재하는 존재인가? (벽의 글자, 단어, 이름만 추정된 것, 물건을 거른다)

질문 문구에는 특정 책의 단어를 넣지 않는다. 경계선당 호출은 보통 1회(질문 = 새 이름 수 × 4, 이름이 많으면 20개씩 나눠 호출)이며, 이미 검사한 이름은 다시 묻지 않는다.
Decide 호출이 실패하면 아무것도 제거하지 않고 경고만 남긴다(오탐으로 진짜 인물을 지우는 것보다 낫다).

환경변수: SCREENER(기본 decide, off 이면 검사 생략), SCREEN_{PERSON,SINGLE,INPLOT,HUMAN}_THRESHOLD (미만이면 제거)
기준값은 주홍색의 연구 한 권에서 정했다. 다른 책에서의 적정성은 검증되지 않았다(docs/entity-screening.md).
"""
from __future__ import annotations

import os

from agents.decide_canonicalizer import _DROPPED, _post, _short, drop_entities

ENABLED = os.getenv("SCREENER", "decide") != "off"

QUESTIONS: dict[str, dict] = {
    "person": {
        "instr": (
            "'{a}'은(는) 개인 이름입니까? 직업·관계·신분·외형으로만 부르는 표기(고유한 이름이 없는 표기)이면 no, "
            "이름이나 성이 하나라도 있거나 그 이름에 호칭이 붙은 표기이면 yes. 대부분의 표기는 개인 이름입니다."
        ),
        "yes": "개인 이름이다.",
        "no": "일반 지칭이다.",
        "threshold": float(os.getenv("SCREEN_PERSON_THRESHOLD", "0.3")),
    },
    "single": {
        "instr": "'{a}'은(는) 한 명(또는 한 마리)을 가리킵니까? 둘 이상을 묶은 표현(여럿의 나열, 가문, 무리, 단체)이면 no.",
        "yes": "한 명이다.",
        "no": "여럿을 묶은 표현이다.",
        "threshold": float(os.getenv("SCREEN_SINGLE_THRESHOLD", "0.3")),
    },
    "inplot": {
        "instr": (
            "'{a}'은(는) 이 이야기 속 사건에 직접 등장하거나 관여하는 인물입니까? "
            "다른 작품의 인물이나 실존 인물이어서 단지 언급·비교만 되면 no."
        ),
        "yes": "이야기 속 인물이다.",
        "no": "언급·비교만 된다.",
        "threshold": float(os.getenv("SCREEN_INPLOT_THRESHOLD", "0.3")),
    },
    "human": {
        "instr": (
            "'{a}'은(는) 이야기 세계에 실제로 존재하는 사람(또는 동물)입니까? "
            "글자·단어, 이름만 추정된 것, 물건이면 no."
        ),
        "yes": "실재하는 존재다.",
        "no": "글자·단어·추정된 이름·물건이다.",
        "threshold": float(os.getenv("SCREEN_HUMAN_THRESHOLD", "0.5")),
    },
}


def collect_names(result: dict) -> dict[str, str]:
    """결과에 나온 모든 이름 → 설명. 인물 목록뿐 아니라 관계·사건에만 나오는 이름도 포함한다."""
    names: dict[str, str] = {}
    for c in result.get("characters", []):
        if c.get("name"):
            names[c["name"]] = c.get("description", "") or ""
    for r in result.get("relations", []):
        for key in ("source", "target"):
            if r.get(key):
                names.setdefault(r[key], "")
    for e in result.get("events", []):
        for p in e.get("participants", []):
            n = p.get("character_name") or p.get("name") if isinstance(p, dict) else p
            if n:
                names.setdefault(n, "")
    return names


BATCH_NAMES = int(os.getenv("SCREEN_BATCH_NAMES", "20"))  # 호출당 질문 수(= 이름 수 × 4)를 80 이하로 유지한다


def _screen_batch(names: dict[str, str]) -> dict[str, dict[str, float]]:
    ordered = list(names)
    state = "인물 설명:\n" + "\n".join(f"- {n}: {_short(names[n], 200) or '(설명 없음)'}" for n in ordered)
    questions = {
        f"{key}{i}": {
            "type": "choice",
            "instructions": q["instr"].format(a=name),
            "criteria": {"yes": q["yes"], "no": q["no"]},
        }
        for i, name in enumerate(ordered)
        for key, q in QUESTIONS.items()
    }
    ans = _post(state, questions)
    return {
        name: {
            key: ans[f"{key}{i}"]["probabilities"].get("yes", 1.0)
            for key in QUESTIONS
            if f"{key}{i}" in ans
        }
        for i, name in enumerate(ordered)
    }


def screen_names(names: dict[str, str]) -> dict[str, dict[str, float]]:
    """이름 → {질문: yes 확률}. 호출이 실패한 묶음의 이름은 결과에서 빠진다(제거도, 검사 완료 처리도 하지 않는다)."""
    out: dict[str, dict[str, float]] = {}
    items = list(names.items())
    for start in range(0, len(items), BATCH_NAMES):
        try:
            out.update(_screen_batch(dict(items[start:start + BATCH_NAMES])))
        except Exception as exc:  # noqa: BLE001 - 실패 시 안전하게 아무것도 제거하지 않는다
            print(f"[entity_screener] solar-decide 호출 실패, 이 묶음은 검사하지 않음: {exc}")
    return out


def flagged(scores: dict[str, float]) -> list[str]:
    return [key for key, p in scores.items() if p < QUESTIONS[key]["threshold"]]


_SEEN: dict[int, set[str]] = {}  # 레지스트리 객체별로 이미 검사한 이름
_ALIASES: dict[int, dict[str, str]] = {}  # 호칭 → 연결된 인물 이름
_PENDING: dict[int, dict[str, str]] = {}  # 연결 못한 호칭 → 설명(나중 경계선에서 다시 시도)
_TICK: dict[int, int] = {}
RETRY_EVERY = int(os.getenv("ALIAS_RETRY_EVERY", "6"))  # 연결 못한 호칭을 다시 시도하는 경계선 간격


def _is_alias_candidate(flags: list[str]) -> bool:
    """역할 호칭일 수 있는 경우: 개인 이름이 아니라고 걸렸고, 여럿을 묶은 표현은 아니다."""
    return "person" in flags and "single" not in flags


def screen_result(
    result: dict,
    registry: list[dict],
    book_id: str | None = None,
    passages_for=None,
) -> tuple[dict, dict[str, str]]:
    """새로 나온 이름만 검사하고, 걸러진 이름 전체를 결과에서 제거한다. (결과, {호칭: 연결된 인물})을 돌려준다.

    registry 는 경계선을 넘어 유지되는 객체이며, 검사 상태의 저장소 키로 쓴다. 호출이 실패한 이름은 다음 경계선에서 다시 묻는다.
    역할 호칭으로 보이는 이름은 role_alias_resolver 로 기존 인물에 연결을 시도하고, 못 하면 제거한 채 RETRY_EVERY 경계선마다 다시 시도한다.
    연결은 확인된 경계선부터만 적용된다(이전 경계선 결과는 건드리지 않아 스포일러가 새지 않는다).
    """
    if not ENABLED:
        return result, {}
    from agents import role_alias_resolver as ra
    from agents.character_aliases import load_character_alias_map

    key = id(registry)
    alias_map = load_character_alias_map(book_id)
    names = collect_names(result)
    seen = _SEEN.setdefault(key, set())
    dropped = _DROPPED.setdefault(key, set())
    aliases = _ALIASES.setdefault(key, {})
    pending = _PENDING.setdefault(key, {})
    tick = _TICK[key] = _TICK.get(key, 0) + 1

    fresh = {n: d for n, d in names.items() if n not in seen and n not in alias_map}
    try_now: dict[str, str] = {}
    for name, scores in screen_names(fresh).items():
        seen.add(name)
        flags = flagged(scores)
        if not flags:
            continue
        dropped.add(name)
        if _is_alias_candidate(flags):
            pending[name] = fresh[name]
            try_now[name] = fresh[name]
    if tick % RETRY_EVERY == 0:
        try_now.update({n: d for n, d in pending.items() if n in names})

    if try_now:
        pool = {n: d for n, d in names.items() if n not in dropped and n not in aliases}
        for c in registry:
            if c.get("name"):
                pool.setdefault(c["name"], c.get("description", "") or "")
        for role, target in ra.resolve(try_now, pool, result, passages_for).items():
            aliases[role] = target
            pending.pop(role, None)
            dropped.discard(role)
    return drop_entities(result, set(dropped)), dict(aliases)
