"""분석 잡 큐 + 진행률 공유 저장소.

REDIS_URL 이 설정되면(도커 구성) RQ(Redis Queue)로 분석 잡을 별도 워커(agent
컨테이너)에 넘기고, 진행률도 Redis 에 저장해 backend·worker 두 프로세스가 공유한다.
REDIS_URL 이 없으면(run-local.sh 로컬 실행) 기존처럼 FastAPI BackgroundTask +
인메모리 진행률로 동작한다 — 즉 도커 없이도 그대로 돌아간다.
"""
from __future__ import annotations

import json
import os

QUEUE_NAME = "spokeeper"
_PROGRESS_PREFIX = "spokeeper:progress:"
_JOB_TIMEOUT = 60 * 60  # 분석은 몇 분~수십 분 걸릴 수 있어 넉넉히.
_UNKNOWN = {"status": "unknown", "completed": 0, "total": 0, "error": None}

REDIS_URL = os.getenv("REDIS_URL", "").strip()

_redis = None
_queue = None
_mem_progress: dict[str, dict] = {}

if REDIS_URL:
    import redis as _redis_lib
    from rq import Queue

    _redis = _redis_lib.from_url(REDIS_URL)
    _queue = Queue(QUEUE_NAME, connection=_redis)


def set_progress(book_id: str, progress: dict) -> None:
    if _redis is not None:
        _redis.set(_PROGRESS_PREFIX + book_id, json.dumps(progress))
    else:
        _mem_progress[book_id] = progress


def update_progress(book_id: str, **fields) -> None:
    current = get_progress(book_id)
    current.update(fields)
    set_progress(book_id, current)


def get_progress(book_id: str) -> dict:
    if _redis is not None:
        raw = _redis.get(_PROGRESS_PREFIX + book_id)
        return json.loads(raw) if raw is not None else dict(_UNKNOWN)
    return _mem_progress.get(book_id, dict(_UNKNOWN))


def pop_progress(book_id: str) -> None:
    if _redis is not None:
        _redis.delete(_PROGRESS_PREFIX + book_id)
    else:
        _mem_progress.pop(book_id, None)


def enqueue_analysis(book_id: str, background_tasks=None) -> None:
    """분석 잡을 큐에 넣는다.

    - Redis 있음: RQ 큐에 넣고 agent 워커가 집어간다.
    - Redis 없음: FastAPI BackgroundTask 로 같은 프로세스에서 실행(로컬 폴백).
    """
    set_progress(book_id, {"status": "queued", "completed": 0, "total": 0, "error": None})

    if _queue is not None:
        _queue.enqueue(
            "backend.app.analysis_jobs.run_full_analysis", book_id, job_timeout=_JOB_TIMEOUT
        )
        return

    from .analysis_jobs import run_full_analysis

    if background_tasks is not None:
        background_tasks.add_task(run_full_analysis, book_id)
    else:
        run_full_analysis(book_id)
