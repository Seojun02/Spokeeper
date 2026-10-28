import { useReminders } from '../api/hooks';
import { useSpoStore } from '../store';

export function ReminderPanel() {
  const bookId = useSpoStore((s) => s.selectedBookId);
  const currentGlobalIndex = useSpoStore((s) => s.currentGlobalIndex);
  const currentPage = useSpoStore((s) => s.currentPage);
  const totalPages = useSpoStore((s) => s.totalPages);
  const { data, isLoading, isError } = useReminders(
    bookId,
    currentGlobalIndex,
    currentPage,
    totalPages,
  );

  return (
    <div className="space-y-4">
      <div className="border border-[#cfd8c5] bg-[#f2f6ed] px-3 py-2 text-xs font-semibold leading-5 text-[#4d574b]">
        {currentPage > 0
          ? `현재 ${currentPage}페이지 기준으로 공개된 사건만 요약합니다.`
          : '페이지 계산 중 · 현재 위치까지 공개된 사건만 요약합니다.'}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((index) => (
            <div key={index} className="h-16 animate-pulse rounded-xl bg-slate-100" />
          ))}
        </div>
      ) : null}

      {isError ? (
        <div className="border border-rose-200 bg-rose-50 p-4 text-sm font-semibold text-rose-600">
          요약을 불러오지 못했습니다.
        </div>
      ) : null}

      {data && data.lines.length === 0 ? (
        <div className="grid min-h-[280px] place-items-center border border-dashed border-[#d8d8ca] bg-[#faf9f5] px-4 text-center text-sm font-semibold text-[#858d7d]">
          아직 정리할 사건이 없습니다.
        </div>
      ) : null}

      {data && data.lines.length > 0 ? (
        <ol className="grid gap-3">
          {data.lines.map((line, index) => (
            <li key={`${line.text}-${index}`} className="border-b border-[#dedbd1] bg-transparent px-0 py-4 last:border-b-0">
              <div className="mb-2 text-xs font-bold text-[#31533e]">Reminder {index + 1}</div>
              <p className="text-sm leading-6 text-[#4d574b]">{line.text}</p>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
