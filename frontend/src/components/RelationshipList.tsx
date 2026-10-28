import { useState } from 'react';
import type { GraphJson, Relationship } from '../api/types';
import { useSpoStore } from '../store';

const CATEGORY_LABEL: Record<string, string> = {
  ally: '협력',
  family: '가족',
  conflict: '갈등',
  crime: '범죄',
  investigation: '조사',
  deception: '기만',
  protection: '보호',
  romance: '감정',
  work: '업무',
  mystery: '단서',
  neutral: '관계',
};

function maskName(name: string, mask: boolean) {
  if (!mask) return name;
  return `${name[0] ?? ''}${'*'.repeat(Math.max(name.length - 1, 1))}`;
}

function nameOf(graph: GraphJson, id: string) {
  return graph.entities.find((entity) => entity.id === id)?.name ?? id;
}

function relationLabel(relationship: Relationship) {
  return relationship.role_pair_label || relationship.display_label || relationship.label || '관계';
}

function relationSummary(relationship: Relationship) {
  return relationship.relationship_summary || relationship.event_summary || relationship.display_label || relationship.description;
}

function RelationshipCard({ graph, relationship, maskNames }: { graph: GraphJson; relationship: Relationship; maskNames: boolean }) {
  const [showEvidence, setShowEvidence] = useState(false);
  const evidence = relationship.evidence ?? [];
  const category = relationship.relation_category ?? 'neutral';

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-2 text-sm font-bold text-slate-800">
        <span>{maskName(nameOf(graph, relationship.source), maskNames)}</span>
        <span className="text-slate-300">{relationship.directionality === 'directed' ? '→' : '—'}</span>
        <span>{maskName(nameOf(graph, relationship.target), maskNames)}</span>
        <span className="ml-auto rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-bold text-slate-500">
          {CATEGORY_LABEL[category] ?? category}
        </span>
      </div>
      <div className="mt-2 text-xs font-bold text-accent">{relationLabel(relationship)}</div>
      <p className="mt-2 text-xs font-semibold leading-5 text-slate-600">{relationSummary(relationship)}</p>
      {evidence.length > 0 && (
        <div className="mt-2">
          <button type="button" onClick={() => setShowEvidence((value) => !value)} className="text-xs font-bold text-slate-500 hover:text-slate-800">
            근거 {showEvidence ? '닫기' : '보기'}
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
    </li>
  );
}

export function RelationshipList({ graph }: { graph: GraphJson }) {
  const maskNames = useSpoStore((s) => s.maskNames);
  return (
    <ul className="grid gap-2">
      {graph.relationships.map((relationship) => (
        <RelationshipCard key={relationship.id} graph={graph} relationship={relationship} maskNames={maskNames} />
      ))}
    </ul>
  );
}
