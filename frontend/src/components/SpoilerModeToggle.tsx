// ── 안심 모드 토글 (spoilerSafe) ──────────────────────────────
import { useSpoStore } from '../store';

export function SpoilerModeToggle() {
  const spoilerSafe = useSpoStore((s) => s.spoilerSafe);
  const setSpoilerSafe = useSpoStore((s) => s.setSpoilerSafe);

  return (
    <button
      type="button"
      role="switch"
      aria-checked={spoilerSafe}
      onClick={() => setSpoilerSafe(!spoilerSafe)}
      className="group hidden items-center gap-2 border-0 bg-transparent px-0 py-1.5 text-xs font-bold text-[#6d7568] transition hover:text-[#283126] xl:flex"
      title={spoilerSafe ? '안심 모드 ON — 아직 읽지 않은 내용은 숨김' : '안심 모드 OFF — 전체 내용 표시'}
    >
      <span
        className={`inline-flex h-3.5 w-3.5 items-center justify-center rounded-full transition ${
          spoilerSafe ? 'bg-[#52745d]' : 'bg-[#b9b9ad]'
        }`}
        aria-hidden
      >
        <span className="h-1.5 w-1.5 rounded-full bg-white" />
      </span>
      <span className={spoilerSafe ? 'text-[#4d574b]' : 'text-[#9aa38f]'}>
        안심 모드 {spoilerSafe ? 'ON' : 'OFF'}
      </span>
    </button>
  );
}
