"""데모 precompute store 생성기 (API 키 불필요).

'다음 에이전트' 담당자에게 주는 살아있는 예제: 아래 DEMO_BUILD_RESULTS 는 BuildAgent 가
경계선별로 내놓아야 하는 '누적' 출력의 모양이다. 이 스크립트는 그것을 어댑터/precompute 로
계약 JSON(`backend/data/precomputed/b_mist.json`)으로 변환한다. 담당자는 이 dict 를 실제
`incremental_build_agent` 결과로 바꾸기만 하면 된다 (혹은 precompute_from_epub 사용).

실행:  python -m backend.scripts.make_demo_store
확인:  SPO_SOURCE=agent uvicorn backend.app.main:app --port 8000
"""
from __future__ import annotations

from backend.app.precompute import build_entries, write_store

BOOK_ID = "b_mist"

# 경계선별 '누적' build 결과 (BuildAgent 출력 형태). type/color 는 optional —
# 없으면 어댑터가 person/blue 로 채운다. 여기선 시맨틱을 살리려 명시.
DEMO_BUILD_RESULTS: list[tuple[int, dict]] = [
    (
        215,
        {
            "characters": [
                {"name": "민우", "description": "통제실 연구원"},
                {"name": "서현", "description": "민우의 동료 연구원"},
                {"name": "아틀라스 호", "description": "실종된 탐사선", "type": "ship"},
            ],
            "relations": [
                {"source": "민우", "target": "서현", "relation": "동료 연구원",
                 "evidence": "통제실에서 함께 아틀라스 호 신호를 확인함."},
                {"source": "민우", "target": "아틀라스 호", "relation": "신호 추적",
                 "evidence": "민우가 실종 탐사선의 고유 신호를 포착함."},
            ],
            "events": [
                {"summary": "민우와 서현은 통제실에서 아틀라스 호의 신호를 함께 확인했다.",
                 "participants": ["민우", "서현"]},
                {"summary": "민우가 실종 탐사선 아틀라스 호의 고유 신호를 포착했다.",
                 "participants": ["민우", "아틀라스 호"]},
            ],
        },
    ),
    (
        320,
        {
            "characters": [
                {"name": "민우"}, {"name": "서현"},
                {"name": "아틀라스 호", "type": "ship"},
                {"name": "강 국장", "description": "상부 인물", "color": "dark"},
            ],
            "relations": [
                {"source": "민우", "target": "서현", "relation": "동료 연구원",
                 "evidence": "통제실에서 함께 아틀라스 호 신호를 확인함."},
                {"source": "민우", "target": "아틀라스 호", "relation": "신호 추적",
                 "evidence": "민우가 실종 탐사선의 고유 신호를 포착함."},
                {"source": "서현", "target": "강 국장", "relation": "은폐 의혹",
                 "evidence": "서현이 신호 속 강 국장의 보안 서명을 확인함."},
            ],
            "events": [
                {"summary": "민우와 서현은 통제실에서 아틀라스 호의 신호를 함께 확인했다.",
                 "participants": ["민우", "서현"]},
                {"summary": "서현은 신호 속에서 강 국장의 보안 서명을 발견해 은폐 의혹을 품었다.",
                 "participants": ["서현", "강 국장"]},
            ],
        },
    ),
    (
        380,
        {
            "characters": [
                {"name": "민우"}, {"name": "서현"},
                {"name": "아틀라스 호", "type": "ship"},
                {"name": "강 국장", "color": "dark"},
                {"name": "윤 팀장", "description": "강 국장의 집행관", "color": "dark"},
            ],
            "relations": [
                {"source": "민우", "target": "서현", "relation": "동료 연구원",
                 "evidence": "통제실에서 함께 아틀라스 호 신호를 확인함."},
                {"source": "민우", "target": "아틀라스 호", "relation": "신호 추적",
                 "evidence": "민우가 실종 탐사선의 고유 신호를 포착함."},
                {"source": "서현", "target": "강 국장", "relation": "은폐 의혹",
                 "evidence": "서현이 신호 속 강 국장의 보안 서명을 확인함."},
                {"source": "윤 팀장", "target": "민우", "relation": "압박 조사",
                 "evidence": "윤 팀장이 무장 요원들과 통제실에 진입함."},
                {"source": "윤 팀장", "target": "서현", "relation": "압박 조사",
                 "evidence": "윤 팀장이 무장 요원들과 통제실에 진입함."},
            ],
            "events": [
                {"summary": "민우와 서현은 통제실에서 아틀라스 호의 신호를 함께 확인했다.",
                 "participants": ["민우", "서현"]},
                {"summary": "서현은 신호 속에서 강 국장의 보안 서명을 발견해 은폐 의혹을 품었다.",
                 "participants": ["서현", "강 국장"]},
                {"summary": "강 국장의 집행관 윤 팀장이 무장 요원들과 통제실에 진입해 압박을 시작했다.",
                 "participants": ["윤 팀장", "민우", "서현"]},
            ],
        },
    ),
]


def main() -> None:
    entries = build_entries(DEMO_BUILD_RESULTS)
    path = write_store(BOOK_ID, entries)
    print(f"wrote {path} ({len(entries)} entries)")


if __name__ == "__main__":
    main()
