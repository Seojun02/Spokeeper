// ── 슬라이드오버 패널 (F2/F3/F4): 딤 · ✕ · ESC · 포커스 ─────────
import { useEffect, useRef, type ReactNode } from 'react';
import { useSpoStore } from '../store';

interface Props {
  title: string;
  subtitle?: string;
  children: ReactNode;
}

export function SlideOverPanel({ title, subtitle, children }: Props) {
  const panel = useSpoStore((s) => s.panel);
  const setPanel = useSpoStore((s) => s.setPanel);
  const open = panel !== 'closed';
  const panelRef = useRef<HTMLDivElement>(null);

  // ESC 닫기 + 열릴 때 포커스 이동
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPanel('closed');
    };
    document.addEventListener('keydown', onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [open, setPanel]);

  return (
    <>
      {/* 딤 */}
      <div
        aria-hidden
        onClick={() => setPanel('closed')}
        className={`fixed inset-0 z-30 bg-slate-900/30 transition-opacity ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />
      {/* 패널 */}
      <aside
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col bg-white shadow-2xl outline-none transition-transform duration-300 sm:w-[26rem] ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-base font-bold text-slate-800">{title}</h2>
            {subtitle && <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={() => setPanel('closed')}
            aria-label="닫기"
            className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </aside>
    </>
  );
}
