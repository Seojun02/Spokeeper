import type { ReactNode } from 'react';

export function GraphModal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-[#1a1512]/40 p-4" role="dialog" aria-modal="true">
      <div className="grid h-[min(760px,88vh)] w-[min(1180px,96vw)] grid-rows-[60px_minmax(0,1fr)] overflow-hidden border border-[#283126] bg-[#fffdf8] shadow-2xl">
        <header className="flex items-center justify-between border-b border-[#d8d8ca] bg-[#fbfaf5] px-6">
          <h2 className="font-serif text-lg font-bold text-[#283126]">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="grid h-9 w-9 place-items-center border border-transparent bg-transparent text-xl leading-none text-[#4d574b] transition hover:border-[#283126] hover:text-[#283126]"
            aria-label="관계도 닫기"
          >
            ×
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}
