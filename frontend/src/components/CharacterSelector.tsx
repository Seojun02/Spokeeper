import { useState } from 'react';
import type { Entity } from '../api/types';

function score(entity: Entity) {
  return Math.max(1, Math.min(5, entity.importance_score ?? (entity.importance_level === 'major' ? 4 : 2)));
}

function stars(value: number) {
  return `${'★'.repeat(value)}${'☆'.repeat(5 - value)}`;
}

function sortByImportance(entities: Entity[]) {
  return [...entities].sort(
    (a, b) =>
      Number(b.importance_level === 'major') - Number(a.importance_level === 'major') ||
      score(b) - score(a) ||
      a.name.localeCompare(b.name),
  );
}

function tierLabel(value: number) {
  if (value >= 5) return '주요 등장인물';
  if (value >= 4) return '핵심 등장인물';
  if (value >= 3) return '등장인물';
  return '기타 등장인물';
}

export function CharacterSelector({
  entities,
  selectedCharacterId,
  onSelect,
}: {
  entities: Entity[];
  selectedCharacterId: string | null;
  onSelect: (id: string) => void;
}) {
  const [showMinor, setShowMinor] = useState(false);
  const sorted = sortByImportance(entities);
  const primary = sorted.filter((entity) => entity.importance_level === 'major' || score(entity) >= 3);
  const minor = sorted.filter((entity) => !primary.includes(entity));
  const visiblePrimary = primary.length > 0 ? primary : sorted.slice(0, 4);

  const renderButton = (entity: Entity) => {
    const value = score(entity);
    const selected = entity.id === selectedCharacterId;
    return (
      <button
        key={entity.id}
        type="button"
        onClick={() => onSelect(entity.id)}
        className={`shrink-0 border px-3 py-2 text-left transition ${
          selected
            ? 'border-[#283126] bg-[#ebece2] text-[#283126]'
            : 'border-[#d8d8ca] bg-transparent text-[#6d7568] hover:border-[#283126] hover:bg-[#faf9f5]'
        }`}
      >
        <span className="block text-[10px] font-black leading-none tracking-wide text-amber-500">{stars(value)}</span>
        <span className="mt-1 block text-xs font-extrabold">{entity.name}</span>
        <span
          className="mt-0.5 block max-w-[110px] truncate text-[10px] font-bold text-slate-400"
          title={entity.description ?? undefined}
        >
          {entity.description || tierLabel(value)}
        </span>
      </button>
    );
  };

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-xs font-extrabold uppercase tracking-[0.08em] text-[#858d7d]">인물 목록</h3>
        {minor.length > 0 && (
          <button
            type="button"
            onClick={() => setShowMinor((value) => !value)}
            className="text-xs font-bold text-slate-500 transition hover:text-slate-800"
          >
            기타 등장인물 {showMinor ? '접기' : '보기'} ({minor.length})
          </button>
        )}
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1 md:flex-wrap md:overflow-visible">
        {visiblePrimary.map(renderButton)}
      </div>
      {showMinor && (
        <div className="flex gap-2 overflow-x-auto pb-1 md:flex-wrap md:overflow-visible">
          {minor.map(renderButton)}
        </div>
      )}
    </section>
  );
}
