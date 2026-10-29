from __future__ import annotations

import re
from typing import Any

from agents.character_aliases import load_character_alias_map


_IMPORTANT_UNKNOWN_KINDS = {"important_unknown", "unnamed_character", "recurring_unknown"}
_NAMED_KINDS = {"named_character", "character", "person"}


def _clean_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "important", "keep"}
    return False


def _entity_kind(character: dict) -> str:
    for key in ("entity_kind", "character_kind", "kind"):
        value = character.get(key)
        if isinstance(value, str):
            return value.strip().lower()
    return ""


def is_explicitly_kept_character(character: dict) -> bool:
    kind = _entity_kind(character)
    if kind in _NAMED_KINDS or kind in _IMPORTANT_UNKNOWN_KINDS:
        return True
    return any(
        _truthy(character.get(key))
        for key in ("keep_as_character", "important_unknown", "is_important_character")
    )


def should_keep_character_entity(character: dict, book_id: str | None = None) -> bool:
    name = _clean_name(character.get("name"))
    if not name:
        return False

    alias_map = load_character_alias_map(book_id)
    if name in alias_map or name in set(alias_map.values()):
        return True

    kind = _entity_kind(character)
    if kind == "generic_role" and not is_explicitly_kept_character(character):
        return False

    return True


def filter_generic_role_entities(build_result: dict, book_id: str | None = None) -> dict:
    characters = build_result.get("characters", [])
    kept_characters: list[dict] = []
    kept_names: set[str] = set()
    dropped_names: set[str] = set()

    for character in characters:
        if should_keep_character_entity(character, book_id=book_id):
            kept_characters.append(character)
            name = _clean_name(character.get("name"))
            if name:
                kept_names.add(name)
        else:
            name = _clean_name(character.get("name"))
            if name:
                dropped_names.add(name)

    def is_dropped_role(name: str) -> bool:
        name = _clean_name(name)
        if not name or name in kept_names:
            return False
        return name in dropped_names

    relations = [
        relation
        for relation in build_result.get("relations", [])
        if not is_dropped_role(relation.get("source", ""))
        and not is_dropped_role(relation.get("target", ""))
    ]

    events = []
    for event in build_result.get("events", []):
        participants = []
        for participant in event.get("participants", []):
            if isinstance(participant, dict):
                name = participant.get("character_name") or participant.get("name") or ""
                if not is_dropped_role(name):
                    participants.append(participant)
            elif not is_dropped_role(participant):
                participants.append(participant)
        events.append({**event, "participants": participants})

    return {
        **build_result,
        "characters": kept_characters,
        "relations": relations,
        "events": events,
    }
