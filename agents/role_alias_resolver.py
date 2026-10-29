"""역할 호칭("순찰 경관", "예언자")이 이미 나온 인물의 다른 이름인지 두 단계로 판정한다.

1단계(solar-decide): 호칭의 설명과 인물들의 설명을 '같은 사람인가' 질문으로 비교해 상위 후보 몇 명만 추린다.
          이름이 겹치지 않아도 설명으로 후보가 올라오고, 인물이 많아져도 2단계 호출은 후보 수만큼만 든다.
2단계(LLM): 그 호칭이 나온 본문 발췌를 보여주고, 본문이 같은 사람이라고 서술했을 때만 연결한다.
          고른 이유로 본문 문장을 그대로 인용하게 하고, 코드로 두 가지를 검증한다:
          인용이 발췌에 실제로 있는가, 인용 문장 안에 후보 이름이 들어 있는가(예: "예언자 브리감 영").
          두 번째 조건이 없으면 같은 역할의 다른 사람(하숙집 주인 둘)이나 등장인물의 추리 문장으로 잘못 연결된다.
          등장인물의 추측·추리와 작품에 대한 사전 지식은 근거로 쓰지 않는다.

설명 비교만으로는 틀린 쌍이 맞는 쌍보다 높게 나온 사례가 있어(docs/entity-screening.md) 1단계는 후보 추림에만 쓴다.
본문 발췌를 얻을 수 없으면 연결하지 않는다.

환경변수: ALIAS_RESOLVE(기본 1, 0이면 연결 시도 생략), ALIAS_FLOOR(기본 0.15), ALIAS_TOP(기본 3)
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable

from agents.decide_canonicalizer import _SAME_INSTR, _post, _short

ENABLED = os.getenv("ALIAS_RESOLVE", "1") != "0"
FLOOR = float(os.getenv("ALIAS_FLOOR", "0.15"))
TOP = int(os.getenv("ALIAS_TOP", "3"))
POOL_MAX = int(os.getenv("ALIAS_POOL_MAX", "80"))
BATCH_PAIRS = 70  # 호출당 질문 수

_SYSTEM = """당신은 소설 인물 정리 도구입니다. 역할이나 외형으로만 불린 인물(호칭)이 후보 인물 중 한 명과 같은 사람인지를,
주어진 본문 발췌만 근거로 판단합니다.

규칙:
- 발췌가 그 호칭과 후보가 같은 사람이라고 서술하거나 분명히 보여 줄 때만 match_to 에 후보 이름을 적습니다.
- 등장인물이 추측하거나 추리한 내용(예: 변장했을 것이라는 판단)은 근거가 아닙니다.
- 작품에 대한 사전 지식은 쓰지 마세요. 발췌에 없는 내용은 모르는 것으로 취급합니다.
- quote 에는 호칭과 후보 이름이 함께 나오는 근거 문장을 발췌에서 한 글자도 바꾸지 말고 그대로 옮깁니다.
- 확실하지 않으면 match_to 는 null 입니다. 잘못 연결하는 것이 연결하지 않는 것보다 훨씬 나쁩니다.

출력은 JSON 객체 하나만: {"match_to": "후보 이름 또는 null", "quote": "발췌에서 옮긴 문장"}"""


def rank_candidates(roles: dict[str, str], pool: dict[str, str]) -> dict[str, list[tuple[str, float]]]:
    """1단계. 호칭 × 인물 쌍에 '같은 사람인가'를 물어 호칭마다 상위 후보를 돌려준다. 실패한 호칭은 빠진다."""
    pairs = [(r, p) for r in roles for p in pool if r != p]
    scores: dict[tuple[str, str], float] = {}
    for start in range(0, len(pairs), BATCH_PAIRS):
        chunk = pairs[start:start + BATCH_PAIRS]
        names = list(dict.fromkeys(x for pair in chunk for x in pair))
        desc = {**pool, **roles}
        state = "인물 설명:\n" + "\n".join(f"- {n}: {_short(desc.get(n, ''), 200) or '(설명 없음)'}" for n in names)
        questions = {
            f"q{i}": {
                "type": "choice",
                "instructions": _SAME_INSTR.format(a=a, b=b),
                "criteria": {"yes": "같은 사람이다.", "no": "다른 사람이다."},
            }
            for i, (a, b) in enumerate(chunk)
        }
        try:
            ans = _post(state, questions)
        except Exception as exc:  # noqa: BLE001
            print(f"[role_alias_resolver] solar-decide 호출 실패, 이 묶음은 건너뜀: {exc}")
            continue
        for i, pair in enumerate(chunk):
            if f"q{i}" in ans:
                scores[pair] = ans[f"q{i}"]["probabilities"].get("yes", 0.0)
    ranked: dict[str, list[tuple[str, float]]] = {}
    for role in roles:
        top = sorted(((p, s) for (r, p), s in scores.items() if r == role and s >= FLOOR), key=lambda x: -x[1])[:TOP]
        if top:
            ranked[role] = top
    return ranked


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def ask_identity(role: str, role_desc: str, candidates: list[dict], passages: list[str]) -> dict:
    """2단계 LLM 호출. {"match_to": ..., "quote": ...} 를 돌려준다(파싱 실패 시 빈 dict)."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_upstage import ChatUpstage

    from agents.build_agent import extract_json_from_text
    from agents.config import CHAT_MODEL, UPSTAGE_API_KEY
    from agents.llm_utils import invoke_with_retry

    payload = {
        "role": role,
        "role_description": role_desc,
        "candidates": candidates,
        "passages": passages,
    }
    factory = lambda: ChatUpstage(model=CHAT_MODEL, api_key=UPSTAGE_API_KEY, temperature=0, timeout=120)
    response = invoke_with_retry(
        factory,
        [
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False, indent=2)),
        ],
    )
    out = extract_json_from_text(response.content)
    return out if isinstance(out, dict) and not out.get("parse_error") else {}


def confirm(role: str, role_desc: str, candidates: list[tuple[str, float]], pool: dict[str, str], passages: list[str]) -> str | None:
    """2단계. 본문이 같은 사람이라고 보여 주면 후보 이름을, 아니면 None."""
    if not passages:
        return None
    cand_payload = [{"name": n, "description": _short(pool.get(n, ""), 200)} for n, _ in candidates]
    try:
        ans = ask_identity(role, role_desc, cand_payload, passages)
    except Exception as exc:  # noqa: BLE001 - 실패하면 연결하지 않는다
        print(f"[role_alias_resolver] 본문 확인 호출 실패, 연결하지 않음: {exc}")
        return None
    match = ans.get("match_to")
    quote = _squash(ans.get("quote", ""))
    if not match or match not in {n for n, _ in candidates} or not quote:
        return None
    if quote not in _squash("".join(passages)):  # 인용이 발췌에 없으면 근거가 아니다
        return None
    if _squash(match) not in quote:  # 인용 문장에 후보 이름이 없으면 연결을 증명하지 못한다(같은 역할의 다른 사람·추리 문장 차단)
        return None
    return match


def role_evidence(result: dict, name: str) -> list[str]:
    """결과에서 이 이름이 들어간 관계·사건·인물의 evidence 인용문."""
    out: list[str] = []
    for c in result.get("characters", []):
        if c.get("name") == name and c.get("evidence"):
            out.append(c["evidence"])
    for r in result.get("relations", []):
        if name in (r.get("source"), r.get("target")) and r.get("evidence"):
            out.append(r["evidence"])
    for e in result.get("events", []):
        parts = [p.get("character_name") if isinstance(p, dict) else p for p in e.get("participants", [])]
        if name in parts and e.get("evidence"):
            out.append(e["evidence"])
    return list(dict.fromkeys(out))


def resolve(
    roles: dict[str, str],
    pool: dict[str, str],
    result: dict,
    passages_for: Callable[[str], list[str]] | None,
) -> dict[str, str]:
    """호칭 → 연결할 인물 이름. 연결하지 못한 호칭은 결과에 없다."""
    if not ENABLED or not roles or not pool:
        return {}
    pool = dict(list(pool.items())[-POOL_MAX:])
    resolved: dict[str, str] = {}
    for role, cands in rank_candidates(roles, pool).items():
        passages = list(passages_for(role)) if passages_for else []
        passages += role_evidence(result, role)
        match = confirm(role, roles[role], cands, pool, passages)
        if match:
            resolved[role] = match
    return resolved
