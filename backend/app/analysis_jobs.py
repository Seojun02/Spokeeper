"""분석 파이프라인 잡 정의 — backend·agent 워커가 공유한다.

BuildAgent~IndirectLeakageJudge 4단계 파이프라인을 실행한다. 도커 구성에선 이 함수가
agent 워커 프로세스에서 (Redis 큐를 통해) 실행되고, 로컬(run-local.sh)에선 backend
프로세스의 BackgroundTask 로 실행된다. 어느 쪽이든 진행률은 jobs 모듈이 알아서
공유 저장소(Redis 또는 인메모리)에 기록한다.

완료되면 precompute_from_epub 이 Supabase build_agent_snapshots 에 적재하므로,
다음 요청부터 backend 가 바로 서빙한다.
"""
from __future__ import annotations

from . import jobs


def run_full_analysis(book_id: str) -> None:
    from agents.llm_utils import get_usage_summary, reset_usage
    from agents.parsers.epub_parser import parse_epub
    from agents.tools.chunk_tool import make_chunks

    from .book_repository import resolve_epub_path
    from .precompute import precompute_from_epub

    epub_path = str(resolve_epub_path(book_id))
    parsed = parse_epub(epub_path)
    chunks = make_chunks(parsed["chapters"])
    last = len(chunks) - 1
    boundaries = list(range(4, last, 5)) + [last]

    jobs.set_progress(
        book_id,
        {"status": "running", "completed": 0, "total": len(boundaries), "error": None},
    )

    def _on_progress(completed: int, total: int) -> None:
        jobs.update_progress(book_id, completed=completed, total=total)

    reset_usage()
    try:
        precompute_from_epub(epub_path, book_id, boundaries, on_progress=_on_progress)
        jobs.update_progress(book_id, status="done")
    except Exception as e:  # pragma: no cover - 백그라운드 작업 실패는 로그만
        print(f"[분석 실패] book_id={book_id}: {e}")
        jobs.update_progress(book_id, status="failed", error=str(e))
    finally:
        usage = get_usage_summary()
        print(
            f"[토큰 사용량] book_id={book_id} "
            f"입력={usage['input_tokens']:,} 출력={usage['output_tokens']:,} "
            f"호출횟수={usage['call_count']} 예상비용=${usage['estimated_cost_usd']}"
        )
