import { useSpoStore } from '../store';
import { RelationPanel } from './RelationPanel';
import { ReminderPanel } from './ReminderPanel';
import { SettingsPanel } from './SettingsPanel';

export function SidePanel() {
  const panel = useSpoStore((s) => s.panel);
  const setPanel = useSpoStore((s) => s.setPanel);
  const currentPage = useSpoStore((s) => s.currentPage);

  // 예전엔 'hidden lg:flex'였는데, lg 브레이크포인트에서 lg:flex가 hidden을 덮어써서
  // 데스크탑 화면에선 panel이 'closed'여도 사이드바가 절대 안 사라지는 버그가 있었다.
  // 아예 렌더링 자체를 안 하는 쪽이 화면 크기와 무관하게 확실하다 — 그리고
  // ReaderLayout이 grid-cols를 panel 상태에 맞춰 접어야 빈 칸도 안 남는다.
  if (panel === 'closed') return null;

  return (
    <aside className="flex min-h-0 flex-col border border-[#dedbd1] bg-[#fffdfa]">
      <header className="flex shrink-0 items-center justify-between border-b border-[#dedbd1] bg-transparent px-7 py-4">
        <div>
          <h2 className="font-serif text-xl font-bold text-[#20231f]">
            {panel === 'relationship' && '관계도'}
            {panel === 'reminder' && '요약'}
            {panel === 'settings' && '설정'}
          </h2>
          <p className="mt-1 text-[10px] font-bold uppercase tracking-[0.1em] text-[#9aa38f]">
            {currentPage > 0 ? `현재 ${currentPage}페이지까지 공개된 정보` : '페이지 계산 중'}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setPanel('closed')}
          className="grid h-[30px] w-[30px] place-items-center border border-transparent bg-transparent text-lg leading-none text-[#6d7568] transition hover:border-[#283126] hover:text-[#283126]"
          aria-label="패널 닫기"
        >
          ×
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-[18px] pb-5 pt-4 [scrollbar-color:#d2d6c8_transparent] [scrollbar-width:thin]">
        {panel === 'relationship' && <RelationPanel />}
        {panel === 'reminder' && <ReminderPanel />}
        {panel === 'settings' && <SettingsPanel />}
      </div>
    </aside>
  );
}
