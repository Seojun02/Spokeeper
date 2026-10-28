// ── 사이드바 (구성: main app.py) : 브랜드 · EPUB 업로드 · 읽기 위치 슬라이더 ──
// 스타일은 기존 React 디자인 토큰(accent·slate·rounded)을 그대로 따른다.
import { useEffect, useRef, useState } from 'react';
import { useBooks, useProgress, usePutProgress, useUploadBook } from '../api/hooks';
import { useSpoStore } from '../store';
import { SpoilerModeToggle } from './SpoilerModeToggle';

export function Sidebar() {
  const selectedBookId = useSpoStore((s) => s.selectedBookId);
  const setSelectedBookId = useSpoStore((s) => s.setSelectedBookId);
  const { data: books } = useBooks();
  const { data: progress } = useProgress(selectedBookId);
  const putProgress = usePutProgress(selectedBookId);
  const uploadBook = useUploadBook();
  const setProgress = useSpoStore((s) => s.setProgress);
  const readingOffset = useSpoStore((s) => s.readingOffset);
  const spoilerBoundary = useSpoStore((s) => s.spoilerBoundary);
  const currentPage = useSpoStore((s) => s.currentPage);
  const totalPages = useSpoStore((s) => s.totalPages);
  const latestCfi = useSpoStore((s) => s.latestCfi);
  const requestPage = useSpoStore((s) => s.requestPage);

  const [fileName, setFileName] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setUploadError(null);
    uploadBook.mutate(file, {
      onSuccess: (result) => setSelectedBookId(result.book_id),
      onError: (err) => setUploadError(err instanceof Error ? err.message : '업로드 실패'),
    });
  };

  // 최초 progress → store 동기화
  useEffect(() => {
    if (progress) setProgress(
      progress.reading_offset,
      progress.spoiler_boundary,
      progress.current_page,
      progress.total_pages,
      progress.spoiler_boundary_page,
      progress.current_cfi,
    );
  }, [progress, setProgress]);

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col gap-6 overflow-y-auto border-r border-slate-200 bg-white/80 px-4 py-5 backdrop-blur">
      {/* 브랜드 */}
      <div className="flex items-center gap-2">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-lg text-white shadow-sm">
          🍀
        </span>
        <div className="leading-tight">
          <div className="text-base font-bold tracking-tight text-slate-800">SpoKeeper</div>
          <div className="text-[11px] text-slate-400">스포일러-세이프 리딩 컴패니언</div>
        </div>
      </div>

      {/* 1. EPUB 업로드 */}
      <section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          1. EPUB 업로드
        </h2>

        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={uploadBook.isPending}
          className="w-full rounded-xl border border-dashed border-slate-300 bg-slate-50 px-3 py-6 text-center text-xs text-slate-500 transition hover:border-accent hover:text-accent disabled:opacity-50"
        >
          <div className="mb-1 text-2xl" aria-hidden>📚</div>
          {uploadBook.isPending
            ? '업로드 중... (CFI 인덱스 생성)'
            : (fileName ?? '소설 EPUB 파일을 업로드하세요')}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".epub"
          className="hidden"
          onChange={onFileChange}
        />
        {uploadError && <p className="text-xs text-red-500">{uploadError}</p>}

        {/* 책 목록 (Supabase에서 조회) */}
        {books && books.length > 0 && (
          <div className="space-y-1.5">
            {books.map((b) => (
              <button
                key={b.id}
                type="button"
                onClick={() => setSelectedBookId(b.id)}
                className={`w-full rounded-xl border p-3 text-left shadow-sm transition ${
                  b.id === selectedBookId
                    ? 'border-accent bg-accent/5'
                    : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <div className="text-[11px] font-medium text-slate-400">
                  {b.id === selectedBookId ? '현재 분석 중인 책' : '책'}
                </div>
                <div className="mt-0.5 text-sm font-bold text-slate-800">{b.title}</div>
                <div className="text-xs text-slate-500">{b.author}</div>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* 2. 현재 읽기 위치 선택 */}
      <section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          2. 현재 읽기 위치 선택
        </h2>

        <input
          type="range"
          min={1}
          max={Math.max(totalPages, 1)}
          step={1}
          value={Math.max(currentPage, 1)}
          onChange={(e) => requestPage(Number(e.target.value))}
          disabled={totalPages <= 0}
          className="w-full accent-accent"
        />

        <div className="rounded-lg bg-slate-50 px-2 py-1.5 text-xs">
          <div className="text-slate-400">현재 페이지</div>
          <div className="font-mono font-semibold text-slate-700">
            {totalPages > 0 ? `${currentPage} / ${totalPages}` : '—'}
          </div>
        </div>

        {/* 이미 도달한 위치(spoilerBoundary)보다 앞으로 돌아왔을 때만 노출 */}
        {readingOffset < spoilerBoundary && (
          <button
            type="button"
            onClick={() => {
              putProgress.mutate(
                {
                  currentGlobalIndex: readingOffset,
                  currentCfi: latestCfi ?? undefined,
                  currentPage,
                  totalPages,
                  force: true,
                },
                {
                  onSuccess: (p) => setProgress(
                    p.reading_offset,
                    p.spoiler_boundary,
                    p.current_page,
                    p.total_pages,
                    p.spoiler_boundary_page,
                    p.current_cfi,
                  ),
                },
              );
            }}
            className="w-full rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700 transition hover:bg-amber-100"
          >
            📖 현재 읽기 위치로 이동하기
          </button>
        )}
      </section>

      {/* 안심 모드 (master 고유 기능 유지) */}
      <section className="mt-auto space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">안심 모드</h2>
        <SpoilerModeToggle />
        <p className="text-[11px] leading-4 text-slate-400">
          켜면 읽은 위치 뒤 내용은 숨겨집니다.
        </p>
      </section>
    </aside>
  );
}
