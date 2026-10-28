import json
from langchain_upstage import ChatUpstage
from langchain_core.messages import SystemMessage, HumanMessage

from agents.config import UPSTAGE_API_KEY
from agents.build_agent import extract_json_from_text
from agents.llm_utils import invoke_with_retry


CONSOLIDATION_SYSTEM_PROMPT = """
당신은 SpoKeeper의 ConsolidationAgent입니다. canonicalize_new_characters는 매
경계선마다 "새 인물 vs 최근/유사 후보"만 좁게 비교하기 때문에, 표기가 완전히 달라진
음역(예: "션든" vs "실덴")이나 여러 경계선에 걸쳐 뒤늦게 놓친 중복은 못 잡습니다.
당신은 그 사각지대를 메우는 주기적 전체 정리 담당입니다. 지금까지 누적된 인물
목록 전체(all_characters)를 한 번에 받아서 두 가지를 판단하세요.

1. 병합(merge): 표기만 다를 뿐 실제로 같은 사람을 가리키는 이름들을 찾아서 그룹으로
   묶으세요. 흔한 원인: 번역/음역 표기 차이(예: "배"/"베", "바"/"배" 같은 모음 차이),
   존칭·직함 유무, 띄어쓰기 차이. description/evidence 내용을 반드시 근거로 판단하고,
   확실하지 않으면 병합하지 마세요 (잘못 합치는 것이 안 합치는 것보다 훨씬 나쁩니다).
   각 그룹에서 가장 완전하고 자연스러운 표기를 canonical_name으로 고르세요.

2. 인물 아님 제거(remove): all_characters 중 실존 인물 한 명이 아닌 항목을 찾아
   제거 대상으로 표시하세요. 다음을 포함합니다:
   - 가문/가족/조직/기관/장소 이름 (예: "○○ 가문", "○○ 가족", "○○ 병원", "○○ 경찰청")
   - 1인칭 대명사 등 특정 인물을 가리키지 않는 표현 (예: "나")
   - 소설 본문이 아닌 서지 정보/저작권 안내/출판사 크레딧에서 잘못 추출된 이름
     (예: 소설과 무관해 보이는 실존 편집자/발행인 이름)
   단, 이름이 끝까지 안 나오는 조연을 가리키는 일반명사(예: "목동", "처녀", "술꾼들")는
   실제 개별 인물/집단 등장인물을 가리키는 것이라면 제거하지 마세요 — 애매하면 제거하지
   않는 쪽을 선택하세요.

판단 예시 (참고용이며, 실제 판단은 항상 주어진 description/evidence를 따르세요):

예시 1 — 같은 인물, 이름이 직함으로 완전히 대체된 표기 (병합)
  all_characters에: "이수현" (description: "사건을 조사하는 순경"),
                    "이 순경" (description: "현장에서 진술을 받는 경찰")
  판단: 같은 인물 (직함+성만 남고 이름이 생략된 표기) → merge_groups에
  {"canonical_name": "이수현", "aliases": ["이 순경"]}로 포함

예시 2 — 같은 인물, 완전히 다른 음역 표기 (병합)
  all_characters에: "브랜든", "브렌든" (둘 다 같은 등장인물을 가리키는 evidence)
  판단: 같은 인물 (외래어 음역 표기 차이) → merge_groups에 포함

예시 3 — 성만 같고 실제로 다른 인물 (병합 금지)
  all_characters에: "이수현" (순경), "이재훈" (전혀 다른 역할의 목격자)
  판단: 다른 인물 (성만 우연히 같음, 근거 내용이 전혀 다름) → 병합하지 않음

출력은 반드시 아래 JSON 형식으로만 작성하세요.

{
  "merge_groups": [
    {"canonical_name": "대표 이름", "aliases": ["다른 표기1", "다른 표기2"]}
  ],
  "remove_names": ["인물이 아닌 항목 이름", ...]
}

병합할 것도, 제거할 것도 없으면 두 배열 모두 빈 배열로 반환하세요.
"""


def consolidate_registry(canonical_registry: list[dict]) -> dict:
    """canonical_registry 전체를 한 번에 검토해서 병합 그룹과 비-인물 제거 목록을 낸다.

    canonicalize_new_characters와 달리 "새 인물"만 보는 게 아니라 지금까지 누적된
    전체를 보므로, 이름이 하나도 안 겹치는 음역 변형(예: 션든/실덴)도 잡을 수 있다.
    호출 비용이 크므로 매 경계선이 아니라 주기적으로만 호출하도록 호출부에서 제어한다.

    반환값: {"merge_map": {별칭: 대표이름}, "remove_names": {비인물이름, ...}}
    파싱 실패 시 안전하게(오탐 방지) 아무것도 바꾸지 않는 빈 결과를 반환한다.
    """
    if len(canonical_registry) < 2:
        return {"merge_map": {}, "remove_names": set()}

    if not UPSTAGE_API_KEY:
        raise ValueError("UPSTAGE_API_KEY가 설정되지 않았습니다.")

    llm_factory = lambda: ChatUpstage(model="solar-pro2", api_key=UPSTAGE_API_KEY, temperature=0, timeout=120)

    payload = {
        "all_characters": [
            {"name": c.get("name", ""), "description": c.get("description", ""), "evidence": c.get("evidence", "")}
            for c in canonical_registry
        ],
    }

    response = invoke_with_retry(
        llm_factory,
        [
            SystemMessage(content=CONSOLIDATION_SYSTEM_PROMPT),
            HumanMessage(
                content=f"""
전체 인물 목록에서 병합할 그룹과 인물이 아닌 항목을 찾으세요.

{json.dumps(payload, ensure_ascii=False, indent=2)}
"""
            ),
        ],
    )

    result = extract_json_from_text(response.content)
    if result.get("parse_error"):
        return {"merge_map": {}, "remove_names": set()}

    registry_names = {c.get("name", "") for c in canonical_registry}

    merge_map: dict[str, str] = {}
    for group in result.get("merge_groups", []):
        if not isinstance(group, dict):
            continue
        canonical_name = group.get("canonical_name", "")
        aliases = group.get("aliases", [])
        if not canonical_name or canonical_name not in registry_names:
            continue
        for alias in aliases:
            if isinstance(alias, str) and alias in registry_names and alias != canonical_name:
                merge_map[alias] = canonical_name

    remove_names = {
        name for name in result.get("remove_names", []) if isinstance(name, str) and name in registry_names
    }
    # 병합 대상(alias)이 동시에 제거 대상으로도 잡히는 모순은 병합을 우선한다.
    remove_names -= set(merge_map.keys())

    return {"merge_map": merge_map, "remove_names": remove_names}
