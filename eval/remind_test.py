"""리마인드 누출 확인용: 경량 파이프라인 결과(light-<model>_s<i>.json)로 ReminderWriter 를 돌리고,
같은 문장을 IndirectLeakageJudge 에도 통과시켜 판정 전/후를 저장한다.
사용: python eval/remind_test.py solar-pro4   -> eval/cache/S/remind-<model>_s<i>.json
"""
import json
import os
import sys
from pathlib import Path

MODEL = sys.argv[1]
os.environ["UPSTAGE_CHAT_MODEL"] = MODEL
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from legacy.indirect_leakage_judge import judge_reminders  # noqa: E402
from agents.reminder_writer_agent import write_reminders  # noqa: E402

CACHE = Path(__file__).resolve().parent / "cache" / "S"
for i in [2, 4, 6, 9, 11]:
    snap = json.loads((CACHE / f"light-{MODEL}_s{i}.json").read_text(encoding="utf-8"))
    written = write_reminders({"characters": snap["characters"], "relations": snap["relations"], "events": []})
    lines = written.get("lines", [])
    judged = judge_reminders(lines)
    out = {"offset": i, "written": lines, "judged": judged}
    (CACHE / f"remind-{MODEL}_s{i}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{MODEL}] 오프셋 {i}: 작성 {len(lines)}줄 → 판정 후 {len(judged)}줄", flush=True)
