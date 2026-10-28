"""책 하나의 저장된 스냅샷(로컬 precomputed 파일 또는 Supabase build_agent_snapshots)을
훑어서, 리마인더(요약 문장)가 "조용히 소실"된 경계선이 있는지 점검한다.

write_reminders()는 LLM 응답 JSON 파싱에 실패하면 예외를 던지는 대신 그냥 빈
배열(lines: [])을 반환한다(agents/reminder_writer_agent.py). 그 결과 특정
경계선에서만 파싱이 실패해도 겉으로는 "이 구간엔 정리할 사건이 없다"처럼 보여서,
직접 책을 읽어보기 전까지는 알아채기 어렵다. 이 스크립트는 그 증상 —
직전 경계선까지 리마인더가 쌓이고 있었는데 관계/사건 수는 그대로거나 늘었는데
리마인더만 갑자기 0으로 떨어지는 패턴 — 을 찾아낸다.

사용법:
  cd backend
  python3 scripts/check_reminder_integrity.py <book_id>
  python3 scripts/check_reminder_integrity.py --all   # 등록된 책 전체 점검
"""
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
REPO_ROOT = BACKEND_DIR.parent  # UPSTAGE_Bootcamp/ (agents 패키지가 여기 있음)
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(REPO_ROOT))

from app.precompute import store_path  # noqa: E402


def _load_local_entries(book_id: str) -> list[dict] | None:
    path = store_path(book_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["entries"]


def _load_supabase_entries(book_id: str) -> list[dict]:
    from app.cfi_db import _connect  # noqa: E402

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT boundary, graph, reminders FROM build_agent_snapshots"
                " WHERE book_id=%s ORDER BY boundary",
                (book_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    entries = []
    for boundary, graph, reminders in rows:
        graph = graph if isinstance(graph, dict) else json.loads(graph)
        reminders = reminders if isinstance(reminders, (list, dict)) else json.loads(reminders)
        lines = reminders.get("lines", []) if isinstance(reminders, dict) else reminders
        entries.append({"boundary": boundary, "graph": graph, "reminders": lines})
    return entries


def load_entries(book_id: str) -> list[dict]:
    """로컬 precomputed 파일이 있으면 그걸, 없으면 Supabase 스냅샷을 쓴다
    (source_factory.make_content_source가 실제로 우선순위를 매기는 방식과 동일)."""
    local = _load_local_entries(book_id)
    return local if local is not None else _load_supabase_entries(book_id)


# 초반 몇 경계선은 정말로 아직 정리할 사건이 없을 수 있다(예: 인물 소개만
# 하는 도입부) — 그래서 "계속 0"은 이 정도 지나서도 그러면 의심한다.
_STUCK_AT_ZERO_MIN_RELATIONS = 5
_STUCK_AT_ZERO_MIN_BOUNDARIES = 3


def check(book_id: str) -> list[dict]:
    entries = sorted(load_entries(book_id), key=lambda e: e["boundary"])
    issues: list[dict] = []
    prev_reminder_count: int | None = None
    prev_relation_count = 0
    zero_streak = 0

    for entry in entries:
        boundary = entry["boundary"]
        reminder_count = len(entry.get("reminders", []))
        relation_count = len(entry.get("graph", {}).get("relationships", []))

        # 패턴 1: 관계 수는 그대로거나 늘었다(=새 사건이 계속 쌓이고 있다)는 건 이
        # 구간에 정리할 내용이 실제로 있었다는 뜻이다. 그런데도 리마인더가 이전엔
        # 있다가 갑자기 0이 됐다면, "정리할 사건이 없어서"가 아니라 파싱 실패로
        # 조용히 빈 배열이 저장됐을 가능성이 높다.
        if (
            reminder_count == 0
            and prev_reminder_count is not None
            and prev_reminder_count > 0
            and relation_count >= prev_relation_count
        ):
            issues.append(
                {
                    "type": "dropped_to_zero",
                    "boundary": boundary,
                    "prev_reminder_count": prev_reminder_count,
                    "relation_count": relation_count,
                }
            )

        # 패턴 2: 애초에 한 번도 리마인더가 안 생기고 계속 0인 경우 — 패턴 1은
        # "0이 아니었다가 0이 됨"만 잡아서 놓친다. 관계는 이미 몇 개 쌓였는데
        # 리마인더는 몇 경계선째 계속 0이면 별도로 표시한다.
        zero_streak = zero_streak + 1 if reminder_count == 0 else 0
        if (
            zero_streak == _STUCK_AT_ZERO_MIN_BOUNDARIES
            and relation_count >= _STUCK_AT_ZERO_MIN_RELATIONS
        ):
            issues.append(
                {
                    "type": "stuck_at_zero",
                    "boundary": boundary,
                    "zero_streak": zero_streak,
                    "relation_count": relation_count,
                }
            )

        prev_reminder_count = reminder_count
        prev_relation_count = relation_count

    return issues


def _all_book_ids() -> list[str]:
    from app.cfi_db import list_books  # noqa: E402

    return [row["book_id"] for row in list_books()]


def _report(book_id: str) -> bool:
    try:
        issues = check(book_id)
    except Exception as e:  # pragma: no cover - 진단 스크립트, 조회 실패는 그냥 보고만
        print(f"[{book_id}] 점검 실패: {e}")
        return False

    if not issues:
        print(f"[{book_id}] 이상 없음")
        return True

    print(f"[{book_id}] 리마인더 이상 {len(issues)}건:")
    for issue in issues:
        if issue["type"] == "dropped_to_zero":
            print(
                f"  boundary={issue['boundary']} [소실]"
                f" 직전 리마인더 {issue['prev_reminder_count']}줄 -> 0,"
                f" 관계는 {issue['relation_count']}개로 유지/증가"
            )
        else:
            print(
                f"  boundary={issue['boundary']} [계속 0]"
                f" {issue['zero_streak']}개 경계선째 리마인더 0,"
                f" 관계는 {issue['relation_count']}개나 쌓임"
            )
    return False


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("사용법: python3 scripts/check_reminder_integrity.py <book_id | --all>")

    if sys.argv[1] == "--all":
        ok = True
        for bid in _all_book_ids():
            ok = _report(bid) and ok
        sys.exit(0 if ok else 1)

    ok = _report(sys.argv[1])
    sys.exit(0 if ok else 1)
