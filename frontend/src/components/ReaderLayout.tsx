import { EpubJsReader } from './EpubJsReader';
import { SidePanel } from './SidePanel';
import { useSpoStore } from '../store';

export function ReaderLayout() {
  const panel = useSpoStore((s) => s.panel);
  // SidePanel은 panel==='closed'일 때 아예 렌더링을 안 하지만(null 반환), 이 grid의
  // 두 번째 칸(420~560px)이 lg 화면에서 고정으로 계속 예약돼 있으면 빈 여백만
  // 남는다 — panel이 닫혔을 때는 칸 자체를 접어서 리더가 전체 폭을 쓰게 한다.
  const gridCols = panel === 'closed' ? 'lg:grid-cols-1' : 'lg:grid-cols-[minmax(0,1fr)_minmax(470px,560px)]';

  return (
    <main className={`grid min-h-0 grid-cols-1 gap-5 overflow-hidden bg-[#f2f1ec] px-3 py-3 sm:px-5 lg:px-7 lg:py-5 ${gridCols}`}>
      <section className="relative min-h-0 overflow-hidden bg-transparent">
        <EpubJsReader />
      </section>
      <SidePanel />
    </main>
  );
}
