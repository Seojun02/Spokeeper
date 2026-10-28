import { useEffect } from 'react';
import { useProgress } from '../api/hooks';
import { useSpoStore } from '../store';

export function ProgressFooter() {
  const selectedBookId = useSpoStore((s) => s.selectedBookId);
  const currentPage = useSpoStore((s) => s.currentPage);
  const totalPages = useSpoStore((s) => s.totalPages);
  const setProgress = useSpoStore((s) => s.setProgress);
  const requestPage = useSpoStore((s) => s.requestPage);
  const { data: progress } = useProgress(selectedBookId);

  useEffect(() => {
    if (progress) {
      setProgress(
        progress.reading_offset,
        progress.spoiler_boundary,
        progress.current_page,
        progress.total_pages,
        progress.spoiler_boundary_page,
        progress.current_cfi,
      );
    }
  }, [progress, setProgress]);

  return (
    <footer className="z-30 grid gap-[7px] border-t border-[#dedbd1] bg-[#faf9f5] px-4 py-[7px] md:px-7">
      <input
        type="range"
        min={1}
        max={Math.max(totalPages, 1)}
        step={1}
        value={Math.max(currentPage, 1)}
        onChange={(event) => requestPage(Number(event.target.value))}
        disabled={totalPages <= 0}
        className="reading-progress h-0.5 w-full cursor-pointer appearance-none bg-[#d8d8ca]"
        aria-label="읽기 위치 이동"
      />
      <div className="flex items-center justify-end gap-2 text-[11px] font-bold tracking-[0.03em] text-[#858d7d]">
        <label className="inline-flex items-center gap-2">
          페이지
          <input
            type="number"
            min={1}
            max={Math.max(totalPages, 1)}
            value={currentPage > 0 ? currentPage : ''}
            onChange={(event) => requestPage(Number(event.target.value))}
            disabled={totalPages <= 0}
            className="h-6 w-11 border-x-0 border-t-0 border-b border-[#d8d8ca] bg-transparent px-1 text-center text-[13px] font-extrabold text-[#283126] outline-none focus:border-[#283126]"
            aria-label="이동할 페이지 번호"
          />
        </label>
        <span>{totalPages > 0 ? `/ ${totalPages}` : '페이지 계산 중'}</span>
      </div>
    </footer>
  );
}
