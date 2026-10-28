import { useEffect, useMemo, useState } from 'react';
import { useGraph, usePutProgress } from '../api/hooks';
import type { Entity } from '../api/types';
import { useSpoStore } from '../store';
import { CharacterRelationshipTree } from './CharacterRelationshipTree';
import { CharacterSelector } from './CharacterSelector';
import { RelationshipGraph } from './RelationshipGraph';
import { SelectedCharacterCard } from './SelectedCharacterCard';

function score(entity: Entity) {
  return Math.max(1, Math.min(5, entity.importance_score ?? (entity.importance_level === 'major' ? 4 : 2)));
}

function sortByImportance(entities: Entity[]) {
  return [...entities].sort(
    (a, b) =>
      Number(b.importance_level === 'major') - Number(a.importance_level === 'major') ||
      score(b) - score(a) ||
      a.name.localeCompare(b.name),
  );
}

function formatGeneratedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString('ko-KR', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function RelationPanel() {
  const bookId = useSpoStore((s) => s.selectedBookId);
  const currentGlobalIndex = useSpoStore((s) => s.currentGlobalIndex);
  const spoilerSafe = useSpoStore((s) => s.spoilerSafe);
  const latestCfi = useSpoStore((s) => s.latestCfi);
  const currentPage = useSpoStore((s) => s.currentPage);
  const totalPages = useSpoStore((s) => s.totalPages);
  const setProgress = useSpoStore((s) => s.setProgress);
  const setAnalyzed = useSpoStore((s) => s.setAnalyzed);
  const analyzed = useSpoStore((s) => s.analyzed);
  const putProgress = usePutProgress(bookId);
  const { data: graph, isLoading, isError } = useGraph(
    bookId,
    currentGlobalIndex,
    currentPage,
    totalPages,
    spoilerSafe,
  );
  const [syncing, setSyncing] = useState(false);
  const [selectedCharacterId, setSelectedCharacterId] = useState<string | null>(null);

  const selectedCharacter = useMemo(
    () => graph?.entities.find((entity) => entity.id === selectedCharacterId) ?? null,
    [graph?.entities, selectedCharacterId],
  );

  useEffect(() => {
    if (!graph || graph.entities.length === 0) {
      setSelectedCharacterId(null);
      return;
    }
    if (selectedCharacterId && graph.entities.some((entity) => entity.id === selectedCharacterId)) return;
    setSelectedCharacterId(sortByImportance(graph.entities)[0]?.id ?? null);
  }, [graph, selectedCharacterId]);

  const onAnalyze = () => {
    if (!latestCfi) {
      setAnalyzed(true);
      return;
    }
    setSyncing(true);
    putProgress.mutate(
      { currentCfi: latestCfi, currentPage, totalPages },
      {
        onSuccess: (progress) => {
          setProgress(
            progress.reading_offset,
            progress.spoiler_boundary,
            progress.current_page,
            progress.total_pages,
            progress.spoiler_boundary_page,
            progress.current_cfi,
          );
          setAnalyzed(true);
          setSyncing(false);
        },
        onError: () => setSyncing(false),
      },
    );
  };

  if (!analyzed) {
    return (
      <div className="grid min-h-[360px] place-items-center border border-dashed border-[#d8d8ca] bg-[#faf9f5] px-5 text-center">
        <div>
          <p className="text-sm font-bold text-[#283126]">현재 위치 기준 분석을 시작하세요.</p>
          <p className="mt-2 text-xs font-semibold leading-5 text-[#858d7d]">
            EPUB reader의 최신 CFI를 서버 progress API로 동기화한 뒤 관계와 요약을 갱신합니다.
          </p>
          <button
            type="button"
            onClick={onAnalyze}
            disabled={syncing}
            className="mt-5 h-10 border border-[#283126] bg-[#283126] px-4 text-sm font-bold text-white transition hover:bg-[#3d493a] disabled:opacity-60"
          >
            {syncing ? '분석 중' : '현재 위치까지 분석'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3 border border-[#cfd8c5] bg-[#f2f6ed] px-3 py-2 text-xs font-semibold leading-5 text-[#4d574b]">
        <span>
          {spoilerSafe
            ? currentPage > 0
              ? `Spoiler 방지 ON: 현재 ${currentPage}페이지까지 공개된 정보만 표시합니다.`
              : 'Spoiler 방지 ON: 페이지 계산 중 · 현재 위치까지 공개된 정보만 표시합니다.'
            : 'Spoiler 방지 OFF: 서버가 허용한 전체 데이터를 표시합니다.'}
        </span>
        {graph && graph.entities.length > 0 && <RelationshipGraph graph={graph} />}
      </div>

      {graph?.generated_at || graph?.snapshot_boundary != null ? (
        <p className="text-right text-[11px] font-semibold text-[#9aa38f]">
          {graph?.generated_at ? `스냅샷 마지막 갱신: ${formatGeneratedAt(graph.generated_at)}` : null}
          {graph?.generated_at && graph?.snapshot_boundary != null ? ' · ' : null}
          {graph?.snapshot_boundary != null ? `기준 스냅샷: 문단 ${graph.snapshot_boundary}` : null}
        </p>
      ) : null}

      {isLoading || syncing ? (
        <div className="space-y-3">
          <div className="h-16 animate-pulse rounded-xl bg-slate-100" />
          <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
        </div>
      ) : null}

      {isError ? (
        <div className="border border-rose-200 bg-rose-50 p-4 text-sm font-semibold text-rose-600">
          관계 데이터를 불러오지 못했습니다.
        </div>
      ) : null}

      {graph && graph.entities.length === 0 ? (
        <div className="grid min-h-[280px] place-items-center border border-dashed border-[#d8d8ca] bg-[#faf9f5] px-4 text-center text-sm font-semibold text-[#858d7d]">
          아직 공개된 인물 관계가 없습니다.
        </div>
      ) : null}

      {graph && selectedCharacter ? (
        <>
          <CharacterSelector
            entities={graph.entities}
            selectedCharacterId={selectedCharacterId}
            onSelect={setSelectedCharacterId}
          />
          <SelectedCharacterCard entity={selectedCharacter} />
          <CharacterRelationshipTree
            entities={graph.entities}
            relationships={graph.relationships}
            selectedCharacterId={selectedCharacter.id}
          />
        </>
      ) : null}
    </div>
  );
}
