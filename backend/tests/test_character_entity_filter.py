from agents.character_entity_filter import (
    filter_generic_role_entities,
    looks_like_generic_role_name,
    should_keep_character_entity,
)
from backend.app import agent_adapter as ad


def test_generic_role_name_rules():
    assert looks_like_generic_role_name("의사")
    assert looks_like_generic_role_name("마부")
    assert looks_like_generic_role_name("여자아이")
    assert looks_like_generic_role_name("술에 취한 남자")
    assert looks_like_generic_role_name("노인")
    assert looks_like_generic_role_name("경찰관")

    assert not looks_like_generic_role_name("셜록 홈즈")
    assert not looks_like_generic_role_name("제퍼슨 호프")


def test_alias_dictionary_names_are_not_filtered_as_generic_roles():
    assert should_keep_character_entity(
        {"name": "홈즈", "entity_kind": "generic_role"},
        book_id="3fb1a332-ae08-450b-8b20-3567a4da4180",
    )


def test_important_unknown_role_can_be_kept():
    assert should_keep_character_entity(
        {
            "name": "정체불명의 남자",
            "entity_kind": "important_unknown",
            "description": "반복적으로 등장하지만 아직 이름이 밝혀지지 않은 핵심 인물",
        }
    )
    assert should_keep_character_entity(
        {
            "name": "술에 취한 남자",
            "entity_kind": "generic_role",
            "keep_as_character": True,
        }
    )


def test_filter_removes_generic_roles_from_characters_relations_and_events():
    build_result = {
        "characters": [
            {"name": "셜록 홈즈", "entity_kind": "named_character"},
            {"name": "의사", "entity_kind": "generic_role"},
            {"name": "술에 취한 남자", "entity_kind": "generic_role"},
            {"name": "정체불명의 남자", "entity_kind": "important_unknown"},
        ],
        "relations": [
            {"source": "셜록 홈즈", "target": "의사", "relation": "대화"},
            {"source": "셜록 홈즈", "target": "정체불명의 남자", "relation": "추적"},
        ],
        "events": [
            {
                "summary": "홈즈가 사람들을 관찰했다.",
                "participants": ["셜록 홈즈", "의사", "술에 취한 남자", "정체불명의 남자"],
            }
        ],
    }

    filtered = filter_generic_role_entities(build_result)

    assert [character["name"] for character in filtered["characters"]] == ["셜록 홈즈", "정체불명의 남자"]
    assert filtered["relations"] == [{"source": "셜록 홈즈", "target": "정체불명의 남자", "relation": "추적"}]
    assert filtered["events"][0]["participants"] == ["셜록 홈즈", "정체불명의 남자"]


def test_adapter_does_not_create_entities_for_relation_only_generic_roles():
    graph = ad.to_graph_json(
        {
            "characters": [{"name": "셜록 홈즈", "entity_kind": "named_character"}],
            "relations": [
                {"source": "셜록 홈즈", "target": "마부", "relation": "질문"},
                {"source": "셜록 홈즈", "target": "제퍼슨 호프", "relation": "추적"},
            ],
            "events": [],
        },
        boundary=10,
    )

    assert [entity.name for entity in graph.entities] == ["셜록 홈즈", "제퍼슨 호프"]
    assert len(graph.relationships) == 1
    assert graph.relationships[0].target == ad.entity_id("제퍼슨 호프")
