// ── 헤더: 브랜드 · 안심모드 토글 · 패널 탭 ─────────────────────
import { useSpoStore, type PanelKind } from '../store';
import { SpoilerModeToggle } from './SpoilerModeToggle';

const TABS: { kind: Exclude<PanelKind, 'closed'>; label: string; icon: string }[] = [
  { kind: 'relationship', label: '관계도', icon: '🕸️' },
  { kind: 'reminder', label: '리마인드', icon: '📌' },
  { kind: 'settings', label: '설정', icon: '⚙️' },
];

export function Header() {
  const panel = useSpoStore((s) => s.panel);
  const togglePanel = useSpoStore((s) => s.togglePanel);

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur sm:px-6">
      <div className="flex items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white shadow-sm">
          S
        </span>
        <div className="leading-tight">
          <div className="text-sm font-bold tracking-tight text-slate-800">SpoKeeper</div>
          <div className="hidden text-[11px] text-slate-400 sm:block">스포일러 없이 읽는 리딩 컴패니언</div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <SpoilerModeToggle />
        <nav className="flex items-center gap-1 rounded-full bg-slate-100 p-1">
          {TABS.map((t) => {
            const active = panel === t.kind;
            return (
              <button
                key={t.kind}
                type="button"
                aria-pressed={active}
                onClick={() => togglePanel(t.kind)}
                className={`flex items-center gap-1 rounded-full px-3 py-1.5 text-sm font-medium transition ${
                  active
                    ? 'bg-white text-accent shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                <span aria-hidden>{t.icon}</span>
                <span className="hidden sm:inline">{t.label}</span>
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
