"""책 하나를 4단계 파이프라인(BuildAgent→Verifier→ReminderWriter→IndirectLeakageJudge)으로
재분석해서 Supabase build_agent_snapshots에 덮어쓴다.

사용법:
  cd backend
  python3 scripts/run_full_analysis.py <book_id>
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
REPO_ROOT = BACKEND_DIR.parent  # UPSTAGE_Bootcamp/ (agents 패키지가 여기 있음)
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(REPO_ROOT))

from app.analysis_jobs import run_full_analysis  # noqa: E402


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("사용법: python3 scripts/run_full_analysis.py <book_id>")

    book_id = sys.argv[1]
    print(f"[{book_id}] 분석 시작...")
    run_full_analysis(book_id)
    print(f"[{book_id}] 완료")
