"""ContentSource 추상화 (SPEC §3).

계약(graph_json·reminders)의 소스를 인터페이스 뒤에 두어, 초기 FixtureSource →
이후 AgentResultSource 로 '주입만 바꿔' 교체한다. 스포일러 게이팅(strict_chunk_end)은
서버에서 수행한다 (CLAUDE.md 불변 규칙 2·6: 경계선 뒤 데이터는 클라이언트로 보내지 않는다).
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path

from agents.character_aliases import load_character_alias_map
from agents.character_entity_filter import should_keep_character_entity

from .entity_importance import apply_entity_importance
from .relation_summary import summarize_relationships
from .relation_presenter import apply_relationship_presentation
from .schemas import Entity, GraphJson, Relationship, ReminderLine, Reminders, StoryEvent
from .story_relations import expand_story_relationships


def _empty_graph() -> GraphJson:
    return GraphJson(offset=0, spoiler_safe=True, entities=[], relationships=[])


class ContentSource(ABC):
    """graph_json / reminders 공급자."""

    @abstractmethod
    def get_graph(
        self,
        book_id: str,
        boundary_global_index: int,
        reveal_all: bool,
    ) -> GraphJson: ...

    @abstractmethod
    def get_reminders(
        self,
        book_id: str,
        boundary_global_index: int,
        entity_id: str | None,
    ) -> Reminders: ...


class FixtureSource(ContentSource):
    """정적 시드 픽스처 소스 (초기). 경계선 기준 strict_chunk_end 게이팅."""

    def _fixture_graphs(self) -> list[GraphJson]:
        from . import fixtures as fx

        return [fx.GRAPH_C1, fx.GRAPH_C2, fx.GRAPH_C3]

    def _fixture_reminders(self) -> list[tuple[int, list[ReminderLine]]]:
        from . import fixtures as fx

        return [
            (fx.GRAPH_C1.offset, fx.REMINDERS_C1),
            (fx.GRAPH_C2.offset, fx.REMINDERS_C2),
            (fx.GRAPH_C3.offset, fx.REMINDERS_C3),
        ]

    def _with_entity_first_seen(self, graph: GraphJson, boundary_global_index: int) -> GraphJson:
        first_seen_by_id: dict[str, int] = {}
        for snapshot in sorted(self._fixture_graphs(), key=lambda item: item.offset):
            if snapshot.offset > boundary_global_index:
                break
            for entity in snapshot.entities:
                first_seen_by_id.setdefault(entity.id, snapshot.offset)
        return graph.model_copy(
            update={
                "entities": [
                    entity.model_copy(
                        update={
                            "first_seen_global_index": entity.first_seen_global_index
                            if entity.first_seen_global_index is not None
                            else first_seen_by_id.get(entity.id, boundary_global_index)
                        }
                    )
                    for entity in graph.entities
                ]
            }
        )

    def get_graph(
        self,
        book_id: str,
        boundary_global_index: int,
        reveal_all: bool,
    ) -> GraphJson:
        if reveal_all:
            graph = max(self._fixture_graphs(), key=lambda g: g.offset)

            return graph.model_copy(update={"offset": boundary_global_index, "snapshot_boundary": graph.offset})

            graph = self._with_entity_first_seen(graph, graph.offset)
            return graph.model_copy(update={"offset": boundary_global_index})

        visible_graphs = [
            graph
            for graph in self._fixture_graphs()
            if graph.offset <= boundary_global_index
        ]
        graph = max(visible_graphs, key=lambda g: g.offset) if visible_graphs else _empty_graph()
        graph = self._with_entity_first_seen(graph, boundary_global_index)
        # 계약 offset 은 요청 경계선을 반영
        return graph.model_copy(update={"offset": boundary_global_index, "snapshot_boundary": graph.offset})

    def get_reminders(
        self,
        book_id: str,
        boundary_global_index: int,
        entity_id: str | None,
    ) -> Reminders:
        visible_reminders = [
            (boundary, lines)
            for boundary, lines in self._fixture_reminders()
            if boundary <= boundary_global_index
        ]
        lines = max(visible_reminders, key=lambda item: item[0])[1] if visible_reminders else []
        if entity_id:
            lines = [ln for ln in lines if entity_id in ln.entity_ids]
        return Reminders(offset=boundary_global_index, lines=list(lines))


class AgentResultSource(ContentSource):
    """에이전트 precompute 결과 조회 소스 (B2에서 연동).

    외부 에이전트 담당자가 (book, boundary)별로 미리 계산해 둔 계약 JSON을 저장소에서
    읽어 반환한다. 계약이 동일하므로 라우트/스키마 변경 없이 주입만 교체하면 된다.
    """

    def __init__(self, store: dict | None = None):
        # store[(book_id, boundary)] = {"graph": GraphJson, "reminders": list[ReminderLine]}
        self._store = store or {}

    def _canonical_name(self, name: str, alias_map: dict[str, str]) -> str:
        return alias_map.get(name, name)

    def _should_return_entity(self, book_id: str, entity: Entity, alias_map: dict[str, str]) -> bool:
        return should_keep_character_entity({"name": entity.name, "type": entity.type}, book_id=book_id)

    def _replace_alias_names_in_text(self, text: str, alias_map: dict[str, str]) -> str:
        aliases = [
            alias
            for alias, canonical_name in alias_map.items()
            if alias and alias != canonical_name
        ]
        if not aliases:
            return text

        pattern = re.compile("|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True)))
        return pattern.sub(lambda match: alias_map.get(match.group(0), match.group(0)), text)

    def _partial_name_resolution_map(
        self,
        names: list[str],
        alias_map: dict[str, str],
    ) -> tuple[dict[str, str], set[str]]:
        canonical_names = [self._canonical_name(name, alias_map) for name in names]
        full_names = {name for name in canonical_names if " " in name.strip()}
        resolution_map: dict[str, str] = {}
        ambiguous_names: set[str] = set()

        for name in canonical_names:
            stripped = name.strip()
            if not stripped or " " in stripped:
                continue
            if stripped in alias_map or stripped in set(alias_map.values()):
                continue

            candidates = sorted(
                candidate
                for candidate in full_names
                if candidate.startswith(f"{stripped} ") or candidate.endswith(f" {stripped}")
            )
            if len(candidates) == 1:
                resolution_map[stripped] = candidates[0]
            elif len(candidates) > 1:
                ambiguous_names.add(stripped)

        return resolution_map, ambiguous_names

    def _apply_alias_dictionary_to_graph(
        self,
        book_id: str,
        graph: GraphJson,
    ) -> tuple[GraphJson, dict[str, str], dict[str, str]]:
        alias_map = load_character_alias_map(book_id)

        merged_entities: dict[str, Entity] = {}
        entity_id_map: dict[str, str] = {}
        response_name_map = dict(alias_map)
        partial_resolution_map, ambiguous_partial_names = self._partial_name_resolution_map(
            [entity.name for entity in graph.entities],
            alias_map,
        )

        for entity in graph.entities:
            canonical_name = self._canonical_name(entity.name, alias_map)
            if canonical_name in ambiguous_partial_names:
                continue
            canonical_name = partial_resolution_map.get(canonical_name, canonical_name)
            if entity.name != canonical_name:
                response_name_map[entity.name] = canonical_name
            aliases = {
                alias
                for alias, target in alias_map.items()
                if target == canonical_name and alias != canonical_name
            }
            aliases.update(entity.aliases)
            if entity.name != canonical_name:
                aliases.add(entity.name)
            canonical_entity = entity.model_copy(
                update={"name": canonical_name, "aliases": sorted(aliases)}
            )
            if not self._should_return_entity(book_id, canonical_entity, alias_map):
                continue
            existing = merged_entities.get(canonical_name)
            if existing:
                entity_id_map[entity.id] = existing.id
                first_seen_values = [
                    value
                    for value in (existing.first_seen_global_index, canonical_entity.first_seen_global_index)
                    if value is not None
                ]
                merged_aliases = sorted(set(existing.aliases) | set(canonical_entity.aliases))
                updates = {"aliases": merged_aliases}
                if first_seen_values:
                    updates["first_seen_global_index"] = min(first_seen_values)
                merged_entities[canonical_name] = existing.model_copy(update=updates)
                continue

            merged_entities[canonical_name] = canonical_entity
            entity_id_map[entity.id] = canonical_entity.id

        relationships: list[Relationship] = []
        seen_relationships = set()
        for relationship in graph.relationships:
            if relationship.source not in entity_id_map or relationship.target not in entity_id_map:
                continue
            source = entity_id_map.get(relationship.source, relationship.source)
            target = entity_id_map.get(relationship.target, relationship.target)

            # Defensive support for legacy snapshots that stored names directly.
            source = self._canonical_name(source, alias_map)
            target = self._canonical_name(target, alias_map)
            if source == target:
                continue

            key = (
                source,
                target,
                relationship.label,
                relationship.description,
                relationship.revision_offset,
            )
            if key in seen_relationships:
                continue
            seen_relationships.add(key)
            relationships.append(
                relationship.model_copy(
                    update={
                        "source": source,
                        "target": target,
                    }
                )
            )

        events: list[StoryEvent] = []
        for event in graph.events:
            participants = []
            for participant in event.participants:
                canonical_name = self._canonical_name(participant.character_name, alias_map)
                canonical_name = partial_resolution_map.get(canonical_name, canonical_name)
                if canonical_name in ambiguous_partial_names:
                    continue
                canonical_entity = merged_entities.get(canonical_name)
                if not canonical_entity:
                    continue
                if not self._should_return_entity(book_id, canonical_entity, alias_map):
                    continue
                participants.append(participant.model_copy(update={"character_name": canonical_name}))
                if participant.character_name != canonical_name:
                    response_name_map[participant.character_name] = canonical_name
            if len(participants) < 2:
                continue
            events.append(event.model_copy(update={"participants": participants}))

        return (
            graph.model_copy(
                update={
                    "entities": list(merged_entities.values()),
                    "relationships": relationships,
                    "events": events,
                }
            ),
            entity_id_map,
            response_name_map,
        )

    def _apply_alias_dictionary_to_reminders(
        self,
        book_id: str,
        lines: list[ReminderLine],
        entity_id_map: dict[str, str],
        response_name_map: dict[str, str] | None = None,
        drop_if_any_entity_removed: bool = True,
    ) -> list[ReminderLine]:
        alias_map = {**load_character_alias_map(book_id), **(response_name_map or {})}
        if not alias_map and not entity_id_map:
            return list(lines)

        result: list[ReminderLine] = []
        for line in lines:
            if drop_if_any_entity_removed and any(entity_id not in entity_id_map for entity_id in line.entity_ids):
                continue
            entity_ids = list(
                dict.fromkeys(
                    entity_id_map[entity_id]
                    for entity_id in line.entity_ids
                    if entity_id in entity_id_map
                )
            )
            if line.entity_ids and not entity_ids:
                continue
            result.append(
                line.model_copy(
                    update={
                        "text": self._replace_alias_names_in_text(line.text, alias_map),
                        "entity_ids": entity_ids,
                    }
                )
            )
        return result

    @classmethod
    def from_supabase(cls) -> "AgentResultSource":
        """Supabase build_agent_snapshots 테이블에서 전체 책의 스냅샷을 로드한다.

        로컬 JSON 파일과 달리 여러 책이 한 테이블에 같이 있으므로, book_id 필터 없이
        전부 읽어서 (book_id, boundary) 복합키 store 하나로 합친다.
        """
        import psycopg2
        import psycopg2.extras

        from .config import SUPABASE_DB_URL

        store: dict = {}
        if not SUPABASE_DB_URL:
            return cls(store)

        conn = psycopg2.connect(SUPABASE_DB_URL, connect_timeout=10)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT book_id, boundary, graph, reminders FROM build_agent_snapshots")
                rows = cur.fetchall()
        finally:
            conn.close()

        for row in rows:
            store[(str(row["book_id"]), int(row["boundary"]))] = {
                "graph": GraphJson.model_validate(row["graph"]),
                "reminders": [ReminderLine.model_validate(l) for l in row["reminders"]],
            }
        return cls(store)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "AgentResultSource":
        """precompute 가 만든 계약 JSON 파일에서 store 를 로드한다.

        파일 형식: {"book_id": str, "entries": [{"boundary": int, "graph": {...},
        "reminders": [{...}]}]}. schemas 로 검증하며 읽으므로 계약 위반 시 즉시 실패.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        book_id = data["book_id"]
        store: dict = {}
        for entry in data.get("entries", []):
            boundary = int(entry["boundary"])
            store[(book_id, boundary)] = {
                "graph": GraphJson.model_validate(entry["graph"]),
                "reminders": [ReminderLine.model_validate(l) for l in entry.get("reminders", [])],
            }
        return cls(store)

    def _lookup(self, book_id: str, boundary_global_index: int):
        # 경계선 이하 중 가장 큰 precompute 지점을 사용 (없으면 빈 결과)
        keys = sorted(
            boundary
            for (bk, boundary) in self._store
            if bk == book_id and boundary <= boundary_global_index
        )
        return self._store.get((book_id, keys[-1])) if keys else None

    def _with_entity_first_seen(
        self,
        book_id: str,
        boundary_global_index: int,
        graph: GraphJson,
    ) -> GraphJson:
        """현재 boundary 이하 스냅샷만 사용해 entity 최초 등장 위치를 복원한다."""
        first_seen_by_id: dict[str, int] = {}
        boundaries = sorted(
            boundary
            for (stored_book_id, boundary) in self._store
            if stored_book_id == book_id and boundary <= boundary_global_index
        )
        for boundary in boundaries:
            entry = self._store[(book_id, boundary)]
            stored_graph: GraphJson = entry["graph"]
            for entity in stored_graph.entities:
                first_seen_by_id.setdefault(entity.id, boundary)

        return graph.model_copy(
            update={
                "entities": [
                    entity.model_copy(
                        update={
                            "first_seen_global_index": entity.first_seen_global_index
                            if entity.first_seen_global_index is not None
                            else first_seen_by_id.get(entity.id, boundary_global_index)
                        }
                    )
                    for entity in graph.entities
                ]
            }
        )

    def _max_snapshot_boundary_global_index(self, book_id: str) -> int | None:
        boundaries = [boundary for (bk, boundary) in self._store if bk == book_id]
        return max(boundaries) if boundaries else None

    def _book_last_global_index(self, book_id: str) -> int:
        from . import cfi_db

        try:
            total = cfi_db.total_paragraphs(book_id)
        except Exception:
            return 0
        return max(0, total - 1)

    def _reveal_all_boundary_global_index(self, book_id: str) -> int:
        snapshot_boundary_global_index = self._max_snapshot_boundary_global_index(book_id)
        if snapshot_boundary_global_index is not None:
            return snapshot_boundary_global_index
        return self._book_last_global_index(book_id)

    def get_graph(
        self,
        book_id: str,
        boundary_global_index: int,
        reveal_all: bool,
    ) -> GraphJson:
        spoiler_boundary_global_index = (
            self._reveal_all_boundary_global_index(book_id)
            if reveal_all
            else boundary_global_index
        )
        entry = self._lookup(book_id, spoiler_boundary_global_index)
        if not entry:
            return _empty_graph().model_copy(update={"offset": boundary_global_index})
        graph: GraphJson = entry["graph"]

        # 실제로 쓰인 스냅샷 자기 자신의 boundary(=offset) — 아래에서 graph.offset이
        # "요청한 현재 위치"로 덮어써지기 전에 먼저 떼어둔다.
        snapshot_boundary = graph.offset

        graph = self._with_entity_first_seen(book_id, spoiler_boundary_global_index, graph)

        graph, entity_id_map, response_name_map = self._apply_alias_dictionary_to_graph(book_id, graph)
        reminder_lines = self._apply_alias_dictionary_to_reminders(
            book_id,
            entry.get("reminders", []),
            entity_id_map,
            response_name_map,
            drop_if_any_entity_removed=False,
        )
        reminder_entity_ids = [
            entity_id
            for line in reminder_lines
            for entity_id in line.entity_ids
        ]
        graph = apply_entity_importance(book_id, graph, reminder_entity_ids)
        graph = expand_story_relationships(
            graph,
            reminder_lines,
            current_boundary_global_index=spoiler_boundary_global_index,
        )
        graph = summarize_relationships(
            graph,
            current_boundary_global_index=spoiler_boundary_global_index,
            reminder_entity_ids=reminder_entity_ids,
        )
        graph = apply_relationship_presentation(graph)
        return graph.model_copy(update={"offset": boundary_global_index, "snapshot_boundary": snapshot_boundary})

    def get_reminders(
        self,
        book_id: str,
        boundary_global_index: int,
        entity_id: str | None,
    ) -> Reminders:
        entry = self._lookup(book_id, boundary_global_index)
        lines: list[ReminderLine] = entry["reminders"] if entry else []
        graph: GraphJson | None = entry["graph"] if entry else None
        entity_id_map: dict[str, str] = {}
        response_name_map: dict[str, str] = {}
        if graph:
            _, entity_id_map, response_name_map = self._apply_alias_dictionary_to_graph(book_id, graph)
        lines = self._apply_alias_dictionary_to_reminders(book_id, lines, entity_id_map, response_name_map)
        if entity_id:
            canonical_entity_id = entity_id_map.get(entity_id, entity_id)
            lines = [ln for ln in lines if canonical_entity_id in ln.entity_ids]
        return Reminders(offset=boundary_global_index, lines=list(lines))
