import type { Entity, Relationship } from '../../../api/types';

export type CharacterGroupId = 'investigation' | 'family' | 'antagonist' | 'protected' | 'official' | 'other';

export type CharacterGroup = {
  id: CharacterGroupId;
  label: string;
  color: string;
  borderColor: string;
  softColor: string;
};

export const CHARACTER_GROUPS: Record<CharacterGroupId, CharacterGroup> = {
  investigation: {
    id: 'investigation',
    label: '조사/주요 인물',
    color: '#2563eb',
    borderColor: '#1d4ed8',
    softColor: '#dbeafe',
  },
  family: {
    id: 'family',
    label: '가족/가문',
    color: '#16a34a',
    borderColor: '#15803d',
    softColor: '#dcfce7',
  },
  antagonist: {
    id: 'antagonist',
    label: '적대/기만',
    color: '#7c3aed',
    borderColor: '#6d28d9',
    softColor: '#ede9fe',
  },
  protected: {
    id: 'protected',
    label: '피해/보호 대상',
    color: '#ef4444',
    borderColor: '#dc2626',
    softColor: '#fee2e2',
  },
  official: {
    id: 'official',
    label: '공식 인물',
    color: '#f97316',
    borderColor: '#ea580c',
    softColor: '#ffedd5',
  },
  other: {
    id: 'other',
    label: '기타',
    color: '#64748b',
    borderColor: '#475569',
    softColor: '#f1f5f9',
  },
};

function unknownText(value: unknown) {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.join(' ');
  return '';
}

function entityText(entity: Entity) {
  const raw = entity as Entity & Record<string, unknown>;
  return [
    raw.group,
    raw.category,
    raw.role,
    raw.role_label,
    raw.description,
    raw.summary,
    raw.type,
    raw.color,
  ]
    .map(unknownText)
    .join(' ')
    .toLowerCase();
}

function relationshipText(relationship: Relationship) {
  return [
    relationship.relation_category,
    relationship.display_label,
    relationship.relation_role,
    relationship.role_label,
    relationship.role_pair_label,
    relationship.relationship_summary,
    relationship.event_summary,
    relationship.description,
    relationship.label,
  ]
    .map(unknownText)
    .join(' ')
    .toLowerCase();
}

function hasAny(text: string, words: string[]) {
  return words.some((word) => text.includes(word));
}

function scoreGroup(text: string, category?: Relationship['relation_category']) {
  const scores: Record<CharacterGroupId, number> = {
    investigation: 0,
    family: 0,
    antagonist: 0,
    protected: 0,
    official: 0,
    other: 0,
  };

  if (category === 'investigation') scores.investigation += 4;
  if (category === 'family') scores.family += 4;
  if (category === 'deception' || category === 'conflict' || category === 'crime') scores.antagonist += 3;
  if (category === 'protection') scores.protected += 3;
  if (category === 'work') scores.official += 1;

  if (hasAny(text, ['investigator', 'detective', 'inquiry', 'investigation', 'probe', '조사', '탐정', '수사'])) {
    scores.investigation += 3;
  }
  if (hasAny(text, ['police', 'inspector', 'constable', 'official', 'doctor', 'lawyer', '경찰', '형사', '공식', '의사'])) {
    scores.official += 3;
  }
  if (hasAny(text, ['family', 'heir', 'relative', 'father', 'mother', 'wife', 'husband', 'sibling', '가족', '가문', '상속', '친척'])) {
    scores.family += 3;
  }
  if (hasAny(text, ['perpetrator', 'murderer', 'deceiver', 'deception', 'threat', 'suspect', 'criminal', '범인', '기만', '협박', '용의자'])) {
    scores.antagonist += 3;
  }
  if (hasAny(text, ['victim', 'target', 'protected', 'threatened', 'danger', '피해', '보호', '위협', '희생'])) {
    scores.protected += 3;
  }

  return scores;
}

export function deriveCharacterGroups(entities: Entity[], relationships: Relationship[]) {
  const groupByEntityId = new Map<string, CharacterGroup>();
  const evidenceByEntityId = new Map<string, string[]>();

  entities.forEach((entity) => {
    const id = String(entity.id ?? '').trim();
    if (!id) return;
    const scores = scoreGroup(entityText(entity));
    relationships.forEach((relationship) => {
      const source = String(relationship.source ?? '').trim();
      const target = String(relationship.target ?? '').trim();
      if (source !== id && target !== id) return;
      const relationScores = scoreGroup(relationshipText(relationship), relationship.relation_category);
      Object.entries(relationScores).forEach(([groupId, score]) => {
        scores[groupId as CharacterGroupId] += score;
      });
    });

    const ranked = (Object.entries(scores) as Array<[CharacterGroupId, number]>)
      .filter(([groupId]) => groupId !== 'other')
      .sort((a, b) => b[1] - a[1]);
    const selected = ranked[0] && ranked[0][1] > 0 ? ranked[0][0] : 'other';
    groupByEntityId.set(id, CHARACTER_GROUPS[selected]);
    evidenceByEntityId.set(
      id,
      ranked
        .filter(([, score]) => score > 0)
        .slice(0, 2)
        .map(([groupId]) => CHARACTER_GROUPS[groupId].label),
    );
  });

  return { groupByEntityId, evidenceByEntityId };
}

export function usedGroups(groupByEntityId: Map<string, CharacterGroup>) {
  const ids = new Set<CharacterGroupId>();
  groupByEntityId.forEach((group) => ids.add(group.id));
  return Object.values(CHARACTER_GROUPS).filter((group) => ids.has(group.id));
}
