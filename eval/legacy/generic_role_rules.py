"""팀 프로젝트 시절의 일반 지칭 규칙(단어 목록 + 접미사/수식어 패턴). 책 하나에 맞춰진 규칙이라 파이프라인에서는 빼고 기록으로만 남긴다.
대체: agents/entity_screener.py (solar-decide 질문 기반). 근거: docs/entity-screening.md
"""
import re


def _clean_name(value):
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""


_GENERIC_ROLE_NAMES = {
    "의사",
    "마부",
    "여자아이",
    "남자아이",
    "아이",
    "소녀",
    "소년",
    "여자",
    "남자",
    "노인",
    "노파",
    "경찰관",
    "경관",
    "순경",
    "형사",
    "하인",
    "하녀",
    "마부",
    "운전사",
    "사람",
    "손님",
    "주인",
    "군인",
    "병사",
    "목격자",
    "행인",
    "술꾼들",
    "목동",
    "우편국장",
    "처녀",
    "죄수",
    "나",
    "남작부인",
    "재소자",
    "남편",
    "탈주범",
    "미확인 인물",
    "미지의 인물",
    "수사관",
}

_GENERIC_ROLE_SUFFIXES = (
    " 남자",
    " 여자",
    " 아이",
    " 소녀",
    " 소년",
    " 노인",
    " 경찰관",
    " 경관",
    " 의사",
    " 마부",
    " 하인",
    " 하녀",
    " 사람",
    " 손님",
    " 목격자",
    " 행인",
)

_GENERIC_DESCRIPTORS = (
    "술에 취한",
    "취한",
    "늙은",
    "젊은",
    "어린",
    "작은",
    "낯선",
    "수상한",
    "이름 없는",
    "정체불명의",
    "한 ",
    "어떤 ",
    "그 ",
    "이 ",
    "저 ",
)

def looks_like_generic_role_name(name: str) -> bool:
    name = _clean_name(name)
    if not name:
        return True

    if name in _GENERIC_ROLE_NAMES:
        return True

    if any(name.endswith(suffix) for suffix in _GENERIC_ROLE_SUFFIXES):
        return any(name.startswith(prefix) for prefix in _GENERIC_DESCRIPTORS)

    compact = name.replace(" ", "")
    return compact in {role.replace(" ", "") for role in _GENERIC_ROLE_NAMES}


