from agents.verifier_agent import (
    _apply_character_name_map,
    _augment_identity_map_with_alias_rules,
)
from agents.character_aliases import load_character_alias_map


def test_load_default_character_alias_map():
    # default.json is scoped to the Hound of the Baskervilles book_id — pass that
    # explicitly, since it must NOT apply to other/unknown books (see the
    # cross-book leak regression test below).
    alias_map = load_character_alias_map("29f8f4f6-1cff-4b13-95e3-5405a19f8b11")

    assert alias_map["셜록 홈스"] == "셜록 홈즈"
    assert alias_map["홈즈"] == "셜록 홈즈"
    assert alias_map["왓슨 박사"] == "존 H. 왓슨"
    assert alias_map["스태퍼드"] == "스탬포드"
    assert alias_map["그렉슨"] == "토비아스 그레그슨"
    assert alias_map["그레그슨"] == "토비아스 그레그슨"
    assert alias_map["요셉 스미스"] == "조셉 스미스"
    assert "스텐거슨 형제" not in alias_map


def test_default_character_alias_map_not_applied_to_unrelated_books():
    """default.json은 원래 셜록 홈즈(배스커빌 가문의 개) 전용으로 만들어졌는데
    book_id 스코프가 없어서 모든 책에 적용됐었다 — 다른 책의 인물이 우연히
    "왓슨"/"그렉슨" 같은 이름이면 셜록 홈즈 정식 이름으로 강제 치환되는 사고가
    났다. book_id가 없거나 다른 책이면 절대 적용되면 안 된다."""
    assert load_character_alias_map(None) == {}
    assert load_character_alias_map("어떤_다른_책_id") == {}


def test_load_book_character_alias_map_merges_default_and_book_specific_aliases():
    alias_map = load_character_alias_map("3fb1a332-ae08-450b-8b20-3567a4da4180")

    assert alias_map["셜록 홈스"] == "셜록 홈즈"
    assert alias_map["나(화자)"] == "존 H. 왓슨"
    assert alias_map["화자(왓슨)"] == "존 H. 왓슨"


def test_load_hound_character_aliases_keep_stapleton_and_miss_stapleton_distinct():
    alias_map = load_character_alias_map("29f8f4f6-1cff-4b13-95e3-5405a19f8b11")

    assert alias_map["스텁블턴"] == "스태플턴"
    assert alias_map["스태플턴 씨"] == "스태플턴"
    assert alias_map["스탭틀턴 씨"] == "스태플턴"
    assert alias_map["스탤프턴"] == "스태플턴"
    assert alias_map["스테플턴"] == "스태플턴"
    assert alias_map["스텁블턴의 여동생"] == "스태플턴 양"
    assert alias_map["스탤튼 양"] == "스태플턴 양"
    assert alias_map["베릴"] == "스태플턴 양"
    assert alias_map["스테플턴 부인"] == "스태플턴 양"
    assert alias_map["선든"] == "셀든"
    assert alias_map["셀던"] == "셀든"
    assert alias_map["실덴"] == "셀든"
    assert alias_map["션든"] == "셀든"
    assert alias_map["모티머 박사"] == "제임스 모티머"
    assert alias_map["프랭클랜드 씨"] == "프랭크랜드 씨"
    assert alias_map["헨리 바스커빌"] == "헨리 배스커빌"
    assert alias_map["헨리 배스커빌 경"] == "헨리 배스커빌"
    assert alias_map["라이언스 부인"] == "로라 라이언스 부인"
    assert alias_map["스태플턴"] == "스태플턴"
    assert alias_map["스태플턴 양"] == "스태플턴 양"


def test_json_alias_map_resolves_names_before_llm_alias_rules():
    alias_map = load_character_alias_map("3fb1a332-ae08-450b-8b20-3567a4da4180")
    build_result = {
        "characters": [
            {"name": "셜록 홈스", "description": "탐정", "evidence": "셜록 홈스가 말했다."},
            {"name": "나(화자)", "description": "사건의 기록자", "evidence": "나는 홈즈와 만났다."},
        ],
        "relations": [
            {"source": "홈즈", "target": "화자(왓슨)", "relation": "동행", "evidence": "함께 움직였다."},
        ],
        "events": [
            {"summary": "조사 시작", "participants": ["셜록", "나(화자)"], "evidence": "조사가 시작되었다."},
        ],
    }

    _, characters, relations, events = _apply_character_name_map(build_result, alias_map)

    assert [character["name"] for character in characters] == ["셜록 홈즈", "존 H. 왓슨"]
    assert relations[0]["source"] == "셜록 홈즈"
    assert relations[0]["target"] == "존 H. 왓슨"
    assert events[0]["participants"] == ["셜록 홈즈", "존 H. 왓슨"]


def test_alias_rules_merge_last_name_and_honorific_variants():
    """작품과 무관한 일반 패턴(성만 남은 표기, 존칭 유무)만으로 병합되는지 확인한다.
    표기 자체가 달라지는 음역 변형(스펠링이 다른 외래어 표기 등)은 이 결정론적
    규칙이 아니라 LLM 판단(canonicalize_new_characters)의 몫이라 여기서 다루지 않는다.
    """
    characters = [
        {"name": "제임스 모티머", "description": "지팡이를 두고 간 방문객, 의사", "evidence": "..."},
        {"name": "모티머", "description": "의사", "evidence": "모티머가 말했다."},
        {"name": "모티머 씨", "description": "의사", "evidence": "모티머 씨가 말했다."},
    ]
    identity_map = {c["name"]: c["name"] for c in characters}

    name_map = _augment_identity_map_with_alias_rules(characters, identity_map)

    assert {name_map[c["name"]] for c in characters} == {"제임스 모티머"}


def test_alias_rules_do_not_merge_family_role_names():
    characters = [
        {"name": "왓슨", "description": "홈즈의 동료 의사", "evidence": "왓슨이 말했다."},
        {"name": "왓슨 부인", "description": "왓슨의 아내", "evidence": "왓슨 부인이 말했다."},
    ]
    identity_map = {c["name"]: c["name"] for c in characters}

    name_map = _augment_identity_map_with_alias_rules(characters, identity_map)

    assert name_map["왓슨"] == "왓슨"
    assert name_map["왓슨 부인"] == "왓슨 부인"


def test_alias_rules_merge_parenthetical_alias_matching_existing_name():
    """"화자(이름)"처럼 괄호 안 표기가 목록에 이미 있는 인물명과 정확히 일치하면
    연결한다. 특정 인물이 서술자라는 것 자체를 추론하지는 않는다 — 그건 이 결정론적
    규칙이 아니라 LLM 판단(canonicalize_new_characters)의 몫이다.
    """
    characters = [
        {"name": "왓슨", "description": "홈즈의 동료 의사", "evidence": "왓슨"},
        {"name": "화자(왓슨)", "description": "사건을 서술하는 홈즈의 동료", "evidence": "화자(왓슨)"},
    ]
    identity_map = {c["name"]: c["name"] for c in characters}

    name_map = _augment_identity_map_with_alias_rules(characters, identity_map)

    assert {name_map[c["name"]] for c in characters} == {"왓슨"}


def test_apply_name_map_deduplicates_relations_after_merge():
    build_result = {
        "characters": [
            {"name": "셜록 홈즈", "description": "탐정", "evidence": "셜록 홈즈"},
            {"name": "홈즈", "description": "탐정", "evidence": "홈즈"},
            {"name": "왓슨", "description": "의사", "evidence": "왓슨"},
        ],
        "relations": [
            {"source": "셜록 홈즈", "target": "왓슨", "relation": "동료", "evidence": "함께 조사"},
            {"source": "홈즈", "target": "왓슨", "relation": "동료", "evidence": "함께 조사"},
        ],
        "events": [
            {"summary": "조사", "participants": ["홈즈", "왓슨"], "evidence": "조사했다"},
            {"summary": "조사", "participants": ["셜록 홈즈", "왓슨"], "evidence": "조사했다"},
        ],
    }

    _, characters, relations, events = _apply_character_name_map(
        build_result,
        {"셜록 홈즈": "셜록 홈즈", "홈즈": "셜록 홈즈", "왓슨": "왓슨"},
    )

    assert [c["name"] for c in characters] == ["셜록 홈즈", "왓슨"]
    assert len(relations) == 1
    assert relations[0]["source"] == "셜록 홈즈"
    assert len(events) == 1
    assert events[0]["participants"] == ["셜록 홈즈", "왓슨"]


def test_apply_name_map_resolves_relation_only_aliases():
    build_result = {
        "characters": [
            {"name": "셜록 홈즈", "description": "탐정", "evidence": "셜록 홈즈"},
            {"name": "존 H. 왓슨", "description": "의사", "evidence": "존 H. 왓슨"},
        ],
        "relations": [
            {"source": "홈즈", "target": "왓슨 박사", "relation": "동료", "evidence": "함께 조사"},
        ],
        "events": [
            {"summary": "조사", "participants": ["홈즈", "화자(왓슨)"], "evidence": "조사했다"},
        ],
    }

    _, _, relations, events = _apply_character_name_map(
        build_result,
        {"셜록 홈즈": "셜록 홈즈", "존 H. 왓슨": "존 H. 왓슨"},
    )

    assert relations[0]["source"] == "셜록 홈즈"
    assert relations[0]["target"] == "존 H. 왓슨"
    assert events[0]["participants"] == ["셜록 홈즈", "존 H. 왓슨"]
