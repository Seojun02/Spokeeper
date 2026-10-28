import { useRef, useState, type ChangeEvent } from 'react';
import { createPortal } from 'react-dom';
import { useAnalysisStatus, useBook, useBooks, useDeleteBook, useUploadBook } from '../api/hooks';
import { useSpoStore, type PanelKind } from '../store';
import { SpoilerModeToggle } from './SpoilerModeToggle';

const DELETE_CONFIRM_WORD = '삭제';

function DeleteBookDialog({
  title,
  isDeleting,
  onCancel,
  onConfirm,
}: {
  title: string;
  isDeleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [input, setInput] = useState('');
  const canDelete = input.trim() === DELETE_CONFIRM_WORD;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-5 shadow-xl">
        <h3 className="text-sm font-extrabold text-slate-800">책 삭제</h3>
        <p className="mt-2 text-xs leading-relaxed text-slate-500">
          <span className="font-bold text-slate-700">{title}</span> 을(를) 삭제하면 분석 결과(관계도, 스냅샷,
          읽기 위치)까지 전부 사라지고 되돌릴 수 없습니다. 다시 만들려면 처음부터 재분석해야 합니다.
        </p>
        <p className="mt-3 text-xs font-semibold text-slate-600">
          계속하려면 아래 칸에 <span className="font-black text-rose-600">삭제</span> 라고 입력하세요.
        </p>
        <input
          autoFocus
          value={input}
          onChange={(event) => setInput(event.target.value)}
          className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-rose-400"
          placeholder="삭제"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={isDeleting}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-60"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!canDelete || isDeleting}
            className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-bold text-white transition disabled:cursor-not-allowed disabled:bg-rose-300"
          >
            {isDeleting ? '삭제 중…' : '영구 삭제'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

const TABS: Array<{ kind: Exclude<PanelKind, 'closed'>; label: string }> = [
  { kind: 'relationship', label: '관계도' },
  { kind: 'reminder', label: '요약' },
  { kind: 'settings', label: '설정' },
];

export function TopBar() {
  const selectedBookId = useSpoStore((s) => s.selectedBookId);
  const setSelectedBookId = useSpoStore((s) => s.setSelectedBookId);
  const panel = useSpoStore((s) => s.panel);
  const togglePanel = useSpoStore((s) => s.togglePanel);
  const currentPage = useSpoStore((s) => s.currentPage);
  const totalPages = useSpoStore((s) => s.totalPages);
  const { data: books } = useBooks();
  const { data: book } = useBook(selectedBookId);
  const uploadBook = useUploadBook();
  const deleteBook = useDeleteBook();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [analyzingBookId, setAnalyzingBookId] = useState<string | null>(null);
  const { data: analysisStatus } = useAnalysisStatus(analyzingBookId, analyzingBookId !== null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null);

  const confirmDelete = () => {
    if (!deleteTarget) return;
    deleteBook.mutate(deleteTarget.id, {
      onSuccess: () => {
        if (selectedBookId === deleteTarget.id) {
          const remaining = books?.filter((item) => item.id !== deleteTarget.id) ?? [];
          if (remaining[0]) setSelectedBookId(remaining[0].id);
        }
        setDeleteTarget(null);
      },
    });
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    uploadBook.mutate(file, {
      onSuccess: (result) => {
        setSelectedBookId(result.book_id);
        setAnalyzingBookId(result.book_id);
      },
      onError: (error) => setUploadError(error instanceof Error ? error.message : '업로드에 실패했습니다.'),
    });
  };

  const isAnalyzing = analysisStatus?.status === 'running';
  const analysisPercent =
    analysisStatus && analysisStatus.total > 0
      ? Math.round((analysisStatus.completed / analysisStatus.total) * 100)
      : 0;

  return (
    <header className="relative z-30 flex min-w-0 items-center justify-between gap-5 border-b border-[#dedbd1] bg-[#faf9f5] px-4 md:px-7">
      <div className="flex min-w-0 items-center gap-3.5">
        <div className="flex shrink-0 items-center gap-3.5">
          <div className="font-serif text-[17px] font-bold tracking-[0.01em] text-[#20231f]">SpoKeeper</div>
          <div className="hidden h-5 w-px bg-[#d8d8ca] sm:block" />
        </div>
        <div className="flex min-w-0 items-center gap-1">
          <select
            value={selectedBookId}
            onChange={(event) => setSelectedBookId(event.target.value)}
            className="w-[132px] max-w-[230px] truncate border-0 bg-transparent py-2 pr-2 text-[13px] font-semibold text-[#6d7568] outline-none transition focus:text-[#283126] sm:w-[180px] md:w-auto"
            aria-label="도서 선택"
          >
            {books?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
          {selectedBookId && (
            <button
              type="button"
              onClick={() =>
                setDeleteTarget({
                  id: selectedBookId,
                  title:
                    books?.find((item) => item.id === selectedBookId)?.title ??
                    book?.title ??
                    selectedBookId,
                })
              }
              title="이 책 삭제"
              aria-label="이 책 삭제"
              className="hidden h-8 w-8 shrink-0 items-center justify-center border border-transparent bg-transparent text-[#9aa38f] transition hover:border-rose-300 hover:text-rose-600 sm:flex"
            >
              🗑
            </button>
          )}
        </div>
      </div>

      <div className="pointer-events-none absolute left-1/2 hidden -translate-x-1/2 text-[11px] font-bold tracking-[0.06em] text-[#858d7d] lg:block">
        {currentPage > 0 && totalPages > 0 ? `${currentPage} / ${totalPages} 페이지` : '페이지 계산 중'}
      </div>

      <div className="flex shrink-0 items-center gap-3 lg:gap-5">
        <SpoilerModeToggle />
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={uploadBook.isPending || isAnalyzing}
          className="hidden h-9 items-center border border-[#d8d8ca] bg-transparent px-3 text-xs font-bold text-[#6d7568] transition hover:border-[#283126] hover:text-[#283126] disabled:opacity-60 sm:inline-flex"
        >
          {uploadBook.isPending
            ? '업로드 중'
            : isAnalyzing
              ? `분석 중 ${analysisPercent}%`
              : 'EPUB 업로드'}
        </button>
        <input ref={fileRef} type="file" accept=".epub" className="hidden" onChange={onFileChange} />
        <nav className="flex items-center gap-4 lg:gap-5">
          {TABS.map((tab) => (
            <button
              key={tab.kind}
              type="button"
              onClick={() => togglePanel(tab.kind)}
              className={`h-9 border-x-0 border-t-0 bg-transparent px-0 text-[13px] font-bold tracking-[0.03em] transition ${
                panel === tab.kind
                  ? 'border-b-[3px] border-[#283126] text-[#283126]'
                  : 'border-b-2 border-transparent text-[#6d7568] hover:border-[#283126] hover:text-[#283126]'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>
      {uploadError && (
        <div className="absolute right-7 top-14 border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-600 shadow-sm">
          {uploadError}
        </div>
      )}
      {analysisStatus && analysisStatus.status !== 'done' && (
        <div className="absolute right-7 top-14 w-64 border border-[#d8d8ca] bg-[#fffdfa] px-3 py-2.5 shadow-md">
          {analysisStatus.status === 'failed' ? (
            <p className="text-xs font-semibold text-rose-600">
              분석 실패: {analysisStatus.error ?? '알 수 없는 오류'}
            </p>
          ) : (
            <>
              <div className="flex items-center justify-between text-xs font-semibold text-slate-600">
                <span>인물/관계 분석 중</span>
                <span>
                  {analysisStatus.completed} / {analysisStatus.total || '?'}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-accent transition-all"
                  style={{ width: `${analysisPercent}%` }}
                />
              </div>
            </>
          )}
        </div>
      )}
      {deleteTarget && (
        <DeleteBookDialog
          title={deleteTarget.title}
          isDeleting={deleteBook.isPending}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={confirmDelete}
        />
      )}
    </header>
  );
}
