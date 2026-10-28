import { useMemo, useState } from 'react';
import type { Entity, Relationship } from '../api/types';

const CATEGORY_LABEL: Record<string, string> = {
  ally: '친구/동료',
  family: '가족',
  investigation: '조사/의심',
  protection: '보호/도움',
  crime: '범죄/피해',
  conflict: '적대/갈등',
  deception: '기만/협박',
  romance: '사랑/감정',
  work: '업무/동료',
  mystery: '사건/단서',
  neutral: '기타',
};

const CATEGORY_BADGE: Record<string, string> = {
  ally: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  family: 'border-blue-200 bg-blue-50 text-blue-700',
  investigation: 'border-sky-200 bg-sky-50 text-sky-700',
  protection: 'border-teal-200 bg-teal-50 text-teal-700',
  crime: 'border-red-200 bg-red-50 text-red-700',
  conflict: 'border-rose-200 bg-rose-50 text-rose-700',
  deception: 'border-purple-200 bg-purple-50 text-purple-700',
  romance: 'border-pink-200 bg-pink-50 text-pink-700',
  work: 'border-cyan-200 bg-cyan-50 text-cyan-700',
  mystery: 'border-amber-200 bg-amber-50 text-amber-700',
  neutral: 'border-slate-200 bg-slate-50 text-slate-600',
};

function entityName(entities: Entity[], id: string) {
  return entities.find((entity) => entity.id === id)?.name ?? id;
}

function relationLabel(relationship: Relationship) {
  return relationship.display_label || relationship.role_pair_label || relationship.role_label || relationship.label || '관계';
}

function relationSummary(relationship: Relationship) {
  return relationship.relationship_summary || relationship.event_summary || relationship.description || '';
}

function groupName(relationship: Relationship) {
  const category = relationship.relation_category ?? 'neutral';
  if (relationship.role_label) return relationship.role_label;
  if (relationship.relation_role) return relationship.relation_role;
  return CATEGORY_LABEL[category] ?? '기타';
}

function categoryLabel(relationship: Relationship) {
  const category = relationship.relation_category ?? 'neutral';
  return CATEGORY_LABEL[category] ?? '기타';
}

function RelationItem({
  relationship,
  entities,
  selectedCharacterId,
}: {
  relationship: Relationship;
  entities: Entity[];
  selectedCharacterId: string;
}) {
  const [showEvidence, setShowEvidence] = useState(false);
  const otherId = relationship.source === selectedCharacterId ? relationship.target : relationship.source;
  const category = relationship.relation_category ?? 'neutral';
  const evidence = relationship.evidence ?? [];

  return (
    <li className="relative border-l border-slate-200 pl-4">
      <div className="absolute -left-[5px] top-3 h-2.5 w-2.5 rounded-full bg-slate-300" />
      <div className="border border-[#d8d8ca] bg-transparent p-3 transition-colors hover:bg-[#faf9f5]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-extrabold text-accent">{relationLabel(relationship)}</span>
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${CATEGORY_BADGE[category] ?? CATEGORY_BADGE.neutral}`}>
            {categoryLabel(relationship)}
          </span>
        </div>
        <div className="mt-2 text-sm font-extrabold text-[#283126]">{entityName(entities, otherId)}</div>
        {relationSummary(relationship) && (
          <p className="mt-1 text-xs font-semibold leading-5 text-[#4d574b]">{relationSummary(relationship)}</p>
        )}
        {relationship.event_name && (
          <p className="mt-2 text-[11px] font-bold text-slate-400">대표 사건: {relationship.event_name}</p>
        )}
        {evidence.length > 0 && (
          <div className="mt-2">
            <button
              type="button"
              onClick={() => setShowEvidence((value) => !value)}
              className="text-xs font-bold text-slate-500 transition hover:text-slate-800"
            >
              근거 {showEvidence ? '접기' : '보기'}
            </button>
            {showEvidence && (
              <ul className="mt-2 grid gap-1 rounded-lg bg-slate-50 p-2 text-xs font-semibold leading-5 text-slate-500">
                {evidence.map((item, index) => (
                  <li key={`${relationship.id}-evidence-${index}`}>{item}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

export function CharacterRelationshipTree({
  entities,
  relationships,
  selectedCharacterId,
}: {
  entities: Entity[];
  relationships: Relationship[];
  selectedCharacterId: string;
}) {
  const directRelationships = useMemo(
    () =>
      relationships.filter(
        (relationship) =>
          relationship.source === selectedCharacterId || relationship.target === selectedCharacterId,
      ),
    [relationships, selectedCharacterId],
  );

  const groups = useMemo(() => {
    const grouped = new Map<string, Relationship[]>();
    directRelationships.forEach((relationship) => {
      const key = groupName(relationship);
      grouped.set(key, [...(grouped.get(key) ?? []), relationship]);
    });
    return [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [directRelationships]);

  return (
    <section className="space-y-3">
      <h3 className="text-xs font-extrabold uppercase tracking-[0.08em] text-[#858d7d]">관계 트리</h3>
      {directRelationships.length === 0 ? (
        <div className="border border-dashed border-[#d8d8ca] bg-[#faf9f5] p-6 text-center text-sm font-semibold text-[#858d7d]">
          이 인물과 직접 연결된 공개 관계가 없습니다.
        </div>
      ) : (
        <div className="space-y-4">
          {groups.map(([group, items]) => (
            <div key={group}>
              <h4 className="mb-2 text-sm font-extrabold text-slate-700">{group}</h4>
              <ul className="space-y-3">
                {items.map((relationship) => (
                  <RelationItem
                    key={relationship.id}
                    relationship={relationship}
                    entities={entities}
                    selectedCharacterId={selectedCharacterId}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
