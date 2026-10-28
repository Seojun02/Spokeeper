// ── 푸터 (F1): 진행바 + 읽기 위치 ────────────────
import { useSpoStore } from '../store';

export function Footer() {
  const currentPage = useSpoStore((s) => s.currentPage);
  const totalPages = useSpoStore((s) => s.totalPages);
  const pct = totalPages > 0 ? Math.round((currentPage / totalPages) * 100) : 0;

  return (
    <footer className="border-t border-slate-200 bg-white px-4 py-3 sm:px-6">
      {/* 진행바: 읽은 위치 + 분석 완료 지점 마커 */}
      <div className="relative mb-2 h-2 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-accent transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[11px] text-slate-500">
        <span>
          {currentPage > 0 ? <strong className="text-slate-700">{currentPage} / {totalPages}</strong> : '페이지 계산 중'}
        </span>
        <span>
          읽은 정도 <strong className="text-slate-700">{pct}%</strong>
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-safe" />
          공개 범위 <strong className="text-slate-700">{currentPage > 0 ? `${currentPage}페이지까지` : '페이지 계산 중'}</strong>
        </span>
      </div>
    </footer>
  );
}
