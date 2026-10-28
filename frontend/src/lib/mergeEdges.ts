// ── (source,label) 병합 규칙 (SPEC §0.5) ──────────────────────
// 동일 (source,label) 엣지는 하나로 병합해 대상 노드를 합쳐 표시.
// 예: r4a(윤 팀장→민우) + r4b(윤 팀장→서현) → "윤 팀장 — 압박 조사 — 민우/서현"

import type { Entity, GraphJson, Relationship, RelationTone } from '../api/types';

export interface MergedEdge {
  key: string; // `${source}::${label}`
  source: string;
  label: string;
  tone: RelationTone;
  description: string;
  targets: string[]; // entity ids
  revision_offset: number; // 병합된 것 중 최대(가장 최근 갱신)
  memberIds: string[]; // 원본 relationship id들
}

export function mergeEdges(rels: Relationship[]): MergedEdge[] {
  const map = new Map<string, MergedEdge>();
  for (const r of rels) {
    const key = `${r.source}::${r.label}`;
    const existing = map.get(key);
    if (existing) {
      if (!existing.targets.includes(r.target)) existing.targets.push(r.target);
      existing.revision_offset = Math.max(existing.revision_offset, r.revision_offset);
      existing.memberIds.push(r.id);
    } else {
      map.set(key, {
        key,
        source: r.source,
        label: r.label,
        tone: r.tone,
        description: r.description,
        targets: [r.target],
        revision_offset: r.revision_offset,
        memberIds: [r.id],
      });
    }
  }
  // revision_offset 오름차순 정렬 (읽은 순서대로)
  return [...map.values()].sort((a, b) => a.revision_offset - b.revision_offset);
}

/** 이름 조회 헬퍼 (마스킹 옵션 반영은 컴포넌트에서) */
export function nameOf(entities: Entity[], id: string): string {
  return entities.find((e) => e.id === id)?.name ?? id;
}

export function entityOf(graph: GraphJson, id: string): Entity | undefined {
  return graph.entities.find((e) => e.id === id);
}
