import { useState } from 'react';
import type { Entity } from '../api/types';
import { TYPE_LABEL } from '../lib/constants';

function scoreText(score?: number) {
  return `${Math.max(1, Math.min(5, score ?? 1))}/5`;
}

function CharacterPill({ entity }: { entity: Entity }) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-sm">
      <span className="min-w-0 truncate">
        <span className="font-bold text-slate-700">{entity.name}</span>
        <span className="ml-2 text-[10px] font-semibold text-slate-400">{TYPE_LABEL[entity.type] ?? entity.type}</span>
      </span>
      <span className="shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-bold text-amber-600">
        {scoreText(entity.importance_score)}
      </span>
    </li>
  );
}

export function CharacterImportanceList({ entities }: { entities: Entity[] }) {
  const [showMinor, setShowMinor] = useState(false);
  const sorted = [...entities].sort(
    (a, b) => (b.importance_score ?? 1) - (a.importance_score ?? 1) || a.name.localeCompare(b.name),
  );
  const major = sorted.filter((entity) => entity.importance_level === 'major');
  const minor = sorted.filter((entity) => entity.importance_level !== 'major');
  const primary = major.length ? major : sorted.slice(0, 3);

  return (
    <div className="space-y-3">
      <ul className="grid gap-2">
        {primary.map((entity) => (
          <CharacterPill key={entity.id} entity={entity} />
        ))}
      </ul>
      {minor.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setShowMinor((value) => !value)}
            className="mb-2 text-xs font-bold text-slate-500 transition hover:text-slate-800"
          >
            기타 인물 ({minor.length}) {showMinor ? '닫기' : '보기'}
          </button>
          {showMinor && (
            <ul className="grid gap-2">
              {minor.map((entity) => (
                <CharacterPill key={entity.id} entity={entity} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
