from __future__ import annotations

from collections import Counter, defaultdict

from .schemas import GraphJson


def apply_entity_importance(book_id: str, graph: GraphJson, reminder_entity_ids: list[str]) -> GraphJson:
    relation_mentions: Counter[str] = Counter()
    connected_neighbors: dict[str, set[str]] = defaultdict(set)

    for relationship in graph.relationships:
        relation_mentions[relationship.source] += 1
        relation_mentions[relationship.target] += 1
        connected_neighbors[relationship.source].add(relationship.target)
        connected_neighbors[relationship.target].add(relationship.source)

    reminder_mentions = Counter(reminder_entity_ids)

    entities = []
    for entity in graph.entities:
        relation_count = relation_mentions[entity.id]
        degree = len(connected_neighbors[entity.id])
        reminder_count = reminder_mentions[entity.id]

        raw_score = 1
        if relation_count >= 1:
            raw_score += 1
        if relation_count >= 3 or degree >= 3:
            raw_score += 1
        if reminder_count >= 1:
            raw_score += 1
        if reminder_count >= 3:
            raw_score += 1

        importance_score = max(1, min(5, raw_score))
        entities.append(
            entity.model_copy(
                update={
                    "importance_score": importance_score,
                    "importance_level": "major" if importance_score >= 4 else "minor",
                }
            )
        )

    return graph.model_copy(update={"entities": entities})
