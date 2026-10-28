import { IS_MOCK } from '../api/client';
import { useSpoStore } from '../store';

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex items-start justify-between gap-4 border border-[#d8d8ca] bg-transparent p-5">
      <span>
        <span className="block text-sm font-bold text-[#283126]">{label}</span>
        <span className="mt-1 block text-xs font-semibold leading-5 text-[#858d7d]">{description}</span>
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition ${
          checked ? 'bg-[#52745d]' : 'bg-[#d8d8ca]'
        }`}
      >
        <span
          className={`h-5 w-5 rounded-full bg-white shadow transition ${
            checked ? 'translate-x-5' : 'translate-x-0.5'
          }`}
        />
      </button>
    </label>
  );
}

export function SettingsPanel() {
  const spoilerSafe = useSpoStore((s) => s.spoilerSafe);
  const setSpoilerSafe = useSpoStore((s) => s.setSpoilerSafe);
  const maskNames = useSpoStore((s) => s.maskNames);
  const setMaskNames = useSpoStore((s) => s.setMaskNames);

  return (
    <div className="grid gap-4">
      <ToggleRow
        label="Spoiler 방지"
        description="켜면 현재 읽은 위치 이후의 관계와 요약을 요청하거나 표시하지 않습니다."
        checked={spoilerSafe}
        onChange={setSpoilerSafe}
      />
      <ToggleRow
        label="이름 마스킹"
        description="관계도와 리스트의 인물 이름을 첫 글자 중심으로 숨깁니다."
        checked={maskNames}
        onChange={setMaskNames}
      />
      <div className="border border-[#d8d8ca] bg-[#faf9f5] p-4 text-xs font-semibold text-[#6d7568]">
        <div className="flex items-center justify-between gap-3">
          <span>데이터 소스</span>
          <span
            className={`rounded-full px-2.5 py-1 font-bold ${
              IS_MOCK ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'
            }`}
          >
            {IS_MOCK ? 'MOCK' : 'FastAPI'}
          </span>
        </div>
      </div>
    </div>
  );
}
