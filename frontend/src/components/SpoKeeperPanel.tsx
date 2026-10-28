// ── SpoKeeper Panel (구성: main app.py '🧠 SpoKeeper Panel') ────────
// '현재 위치까지 분석' → 추출된 인물 / 관계 / 사건(리마인드) / 로그.
// 데이터는 master의 계약(useGraph·useReminders)을 그대로 사용, 스타일 유지.
import { useMemo, useState } from 'react';
import { useGraph, useReminders, usePutProgress } from '../api/hooks';
import { useSpoStore } from '../store';
import { CharacterImportanceList } from './CharacterImportanceList';
import { RelationshipGraph } from './RelationshipGraph';
import { RelationshipList } from './RelationshipList';

function SectionTitle({ icon, children }: { icon: string; children: React.ReactNode }) {
  return (
    <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
      <span aria-hidden>{icon}</span>
      {children}
    </h3>
  );
}

export function SpoKeeperPanel() {
  const bookId = useSpoStore((s) => s.selectedBookId);
  const currentGlobalIndex = useSpoStore((s) => s.currentGlobalIndex);
  const spoilerSafe = useSpoStore((s) => s.spoilerSafe);
  const analyzed = useSpoStore((s) => s.analyzed);
  const setAnalyzed = useSpoStore((s) => s.setAnalyzed);
  const latestCfi = useSpoStore((s) => s.latestCfi);
  const currentPage = useSpoStore((s) => s.currentPage);
  const totalPages = useSpoStore((s) => s.totalPages);
  const setProgress = useSpoStore((s) => s.setProgress);
  const putProgress = usePutProgress(bookId);
  const [syncing, setSyncing] = useState(false);
  const [showMinorRelations, setShowMinorRelations] = useState(false);

  const { data: graph, isLoading: gLoading } = useGraph(
    bookId,
    currentGlobalIndex,
    currentPage,
    totalPages,
    spoilerSafe,
  );
  const { data: reminders, isLoading: rLoading } = useReminders(
    bookId,
    currentGlobalIndex,
    currentPage,
    totalPages,
  );

  const loading = gLoading || rLoading || syncing;
  const isEmpty = !!graph && graph.entities.length === 0;
  const visibleGraph = useMemo(() => {
    if (!graph) return undefined;
    if (showMinorRelations) return graph;
    return {
      ...graph,
      relationships: graph.relationships.filter(
        (relationship) => relationship.relation_importance_level !== 'minor',
      ),
    };
  }, [graph, showMinorRelations]);
  const minorRelationCount =
    graph?.relationships.filter((relationship) => relationship.relation_importance_level === 'minor').length ?? 0;

  // 페이지 이동 때도 동기화하지만, 분석 버튼 시점의 CFI/page/global_index 묶음을
  // 다시 확정한 뒤 관계와 리마인드 쿼리를 갱신한다.
  const onAnalyze = () => {
    if (!latestCfi) {
      setAnalyzed(true);
      return;
    }
    setSyncing(true);
    putProgress.mutate(
      { currentCfi: latestCfi, currentPage, totalPages },
      {
        onSuccess: (p) => {
          setProgress(
            p.reading_offset,
            p.spoiler_boundary,
            p.current_page,
            p.total_pages,
            p.spoiler_boundary_page,
            p.current_cfi,
          );
          setAnalyzed(true);
          setSyncing(false);
        },
        onError: () => setSyncing(false),
      },
    );
  };

  return (
    <section className="flex min-h-0 flex-col rounded-2xl border border-slate-200 bg-white shadow-sm">
      <header className="flex items-center gap-2 border-b border-slate-100 px-5 py-3">
        <span className="text-lg" aria-hidden>🧠</span>
        <h2 className="text-sm font-bold text-slate-800">SpoKeeper Panel</h2>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-4">
        <p className="mb-3 text-xs leading-5 text-slate-500">
          현재 읽은 위치까지 인물·관계·사건을 분석합니다.
        </p>

        <button
          type="button"
          onClick={onAnalyze}
          disabled={syncing}
          className="w-full rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:brightness-110 disabled:opacity-60"
        >
          {syncing ? '현재 위치 확인 중...' : '현재 위치까지 분석'}
        </button>

        {!analyzed && (
          <div className="mt-6 grid place-items-center rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-10 text-center">
            <div className="mb-2 text-3xl" aria-hidden>✨</div>
            <p className="text-sm font-medium text-slate-600">분석을 실행해 주세요.</p>
            <p className="mt-1 text-xs text-slate-400">읽은 위치까지의 인물·관계·사건을 정리합니다.</p>
          </div>
        )}

        {analyzed && loading && (
          <div className="mt-5 space-y-3">
            <div className="h-32 animate-pulse rounded-xl bg-slate-100" />
            <div className="h-16 animate-pulse rounded-xl bg-slate-100" />
          </div>
        )}

        {analyzed && !loading && isEmpty && (
          <div className="mt-6 grid place-items-center rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-10 text-center">
            <div className="mb-2 text-3xl" aria-hidden>🌫️</div>
            <p className="text-sm font-medium text-slate-600">아직 공개된 정보가 없어요.</p>
            <p className="mt-1 text-xs text-slate-400">조금 더 읽으면 분석 결과가 채워집니다.</p>
          </div>
        )}

        {analyzed && !loading && graph && visibleGraph && !isEmpty && (
          <div className="mt-6 space-y-6">
            {/* 👤 추출된 인물 */}
            <div>
              <SectionTitle icon="👤">추출된 인물 {graph.entities.length}</SectionTitle>
              <CharacterImportanceList entities={graph.entities} />
            </div>

            {/* 🔗 추출된 관계 */}
            <div>
              <SectionTitle icon="🔗">추출된 관계 {visibleGraph.relationships.length}</SectionTitle>
              <div className="mb-3 rounded-xl border border-slate-200 bg-slate-50/60 p-2">
                <RelationshipGraph graph={visibleGraph} />
              </div>
              {minorRelationCount > 0 && (
                <button
                  type="button"
                  onClick={() => setShowMinorRelations((value) => !value)}
                  className="mb-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-800"
                >
                  기타 관계 {showMinorRelations ? '숨기기' : `보기 (${minorRelationCount})`}
                </button>
              )}
              <RelationshipList graph={visibleGraph} />
            </div>

            {/* 📌 추출된 사건 (리마인드) */}
            <div>
              <SectionTitle icon="📌">추출된 사건 {reminders?.lines.length ?? 0}</SectionTitle>
              {reminders && reminders.lines.length > 0 ? (
                <ol className="space-y-2">
                  {reminders.lines.map((line, i) => (
                    <li
                      key={i}
                      className="flex gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm"
                    >
                      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent/10 text-xs font-bold text-accent">
                        {i + 1}
                      </span>
                      <p className="text-sm leading-6 text-slate-700">{line.text}</p>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-xs text-slate-400">정리된 사건이 없습니다.</p>
              )}
            </div>

            {/* 📝 로그 */}
            <div>
              <SectionTitle icon="📝">분석 로그</SectionTitle>
              <pre className="overflow-x-auto rounded-xl bg-slate-900 px-3 py-2.5 text-[11px] leading-5 text-slate-100">
{JSON.stringify(
  {
    분석범위: '현재 읽은 위치까지',
    안심모드: spoilerSafe ? '켜짐' : '꺼짐',
    인물수: graph.entities.length,
    관계수: visibleGraph.relationships.length,
    사건수: reminders?.lines.length ?? 0,
  },
  null,
  2,
)}
              </pre>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
