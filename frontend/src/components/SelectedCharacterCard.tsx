import type { Entity } from '../api/types';
import { TYPE_LABEL } from '../lib/constants';

function score(entity: Entity) {
  return Math.max(1, Math.min(5, entity.importance_score ?? (entity.importance_level === 'major' ? 4 : 2)));
}

function stars(value: number) {
  return `${'★'.repeat(value)}${'☆'.repeat(5 - value)}`;
}

export function SelectedCharacterCard({ entity }: { entity: Entity }) {
  const value = score(entity);
  return (
    <section className="border border-[#d8d8ca] bg-[#faf9f5] p-4">
      <div className="mb-2 text-sm font-black tracking-wide text-amber-500">{stars(value)}</div>
      <h3 className="font-serif text-xl font-bold text-[#283126]">{entity.name}</h3>
      <p className="mt-1 text-sm font-semibold text-[#6d7568]">
        {TYPE_LABEL[entity.type] ?? entity.type}
        {entity.importance_level === 'major' ? ' · 핵심 인물' : ' · 등장인물'}
      </p>
      {entity.description && (
        <p className="mt-1 text-xs font-medium leading-relaxed text-[#858d7d]">{entity.description}</p>
      )}
    </section>
  );
}
