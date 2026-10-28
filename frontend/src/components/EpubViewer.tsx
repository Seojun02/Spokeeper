// ── EPUB 뷰어 (구성: main app.py '📖 간이 EPUB 뷰어') ──────────────
// 현재 읽기 위치를 포함하는 챕터 본문을 보여준다. 스타일은 기존 리더 카드 유지.
import { useMemo } from 'react';
import { useBook, useChapter } from '../api/hooks';
import { useSpoStore } from '../store';

export function EpubViewer() {
  const bookId = useSpoStore((s) => s.selectedBookId);
  const readingOffset = useSpoStore((s) => s.readingOffset);
  const { data: book } = useBook(bookId);

  // 현재 읽기 위치를 포함하는 챕터 선택
  const currentChapter = useMemo(() => {
    if (!book) return undefined;
    return (
      book.chapters.find(
        (c) => readingOffset >= c.start_offset && readingOffset <= c.end_offset,
      ) ?? book.chapters[book.chapters.length - 1]
    );
  }, [book, readingOffset]);

  const { data: chapter, isLoading } = useChapter(bookId, currentChapter?.index ?? 0);

  return (
    <section className="flex min-h-0 flex-col rounded-2xl border border-slate-200 bg-white shadow-sm">
      <header className="flex items-center gap-2 border-b border-slate-100 px-5 py-3">
        <span className="text-lg" aria-hidden>📖</span>
        <h2 className="text-sm font-bold text-slate-800">간이 EPUB 뷰어</h2>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-5">
        {book && (
          <>
            <h3 className="text-xl font-bold text-slate-800">{book.title}</h3>
            <p className="mt-1 text-xs text-slate-400">
              {currentChapter
                ? `Chapter ${currentChapter.index} · ${currentChapter.title}`
                : '현재 읽기 위치'}
            </p>
          </>
        )}

        <div className="mt-5">
          {isLoading ? (
            <div className="space-y-3">
              <div className="h-4 w-full animate-pulse rounded bg-slate-100" />
              <div className="h-4 w-5/6 animate-pulse rounded bg-slate-100" />
              <div className="h-4 w-11/12 animate-pulse rounded bg-slate-100" />
            </div>
          ) : chapter?.content ? (
            <article className="whitespace-pre-line text-[16px] leading-8 text-slate-700">
              {chapter.content}
            </article>
          ) : (
            <p className="text-sm text-slate-400">본문을 불러오지 못했어요.</p>
          )}
        </div>
      </div>
    </section>
  );
}
