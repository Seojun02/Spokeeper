"""LLM 호출 공통 유틸. rate limit(429) 등 일시적 오류에 재시도를 붙이고,
파이프라인 전체의 토큰 사용량/예상 비용을 집계한다."""
import concurrent.futures
import time

# ChatUpstage(timeout=...)가 내부적으로 네트워크 계층까지 제대로 전달되지 않는 경우가
# 있어(연결이 죽었는데도 응답을 무한정 기다리는 현상 실제 관측됨), 라이브러리의 타임아웃을
# 믿지 않고 별도 스레드 + future.result(timeout=)로 파이썬 레벨에서 강제로 끊는다.
#
# 스레드 풀은 호출마다 새로 만든다(공유 풀 X). future.result(timeout=)가 시간초과로
# 포기해도 스레드 자체는 취소가 안 되고 백그라운드에서 계속 살아있는데(파이썬은 실행 중인
# 스레드를 강제 종료할 방법이 없음), 고정 크기 공유 풀(max_workers=4)을 계속 재사용하면
# 이런 "좀비 스레드"가 하나씩 슬롯을 영구히 차지해서 결국 풀 전체가 막혀버리는 현상이
# 실제로 관측됐다(전체 실행이 진행될수록 점점 느려지다가 완전히 멈춤). 매 호출마다
# max_workers=1짜리 풀을 새로 만들고 성공/실패 여부와 무관하게 shutdown(wait=False)로
# 즉시 손을 떼면, 좀비 스레드가 남더라도 그 풀만 버려질 뿐 다음 호출에 영향을 주지 않는다.
_HARD_TIMEOUT_SECONDS = 180.0

# Solar Pro 2 정가 (2026-07 기준, https://www.upstage.ai/pricing/api). 부가세 제외.
_PRICE_PER_1M_INPUT = 0.15
_PRICE_PER_1M_OUTPUT = 0.60
_PRICE_PER_1M_CACHED_INPUT = 0.015

_usage_totals = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "call_count": 0}


def reset_usage() -> None:
    """토큰 집계를 0으로 초기화한다. 파이프라인 실행 시작 시 호출."""
    _usage_totals.update(input_tokens=0, output_tokens=0, cached_tokens=0, call_count=0)


def get_usage_summary() -> dict:
    """지금까지 집계된 토큰 사용량과 정가 기준 예상 비용(달러)을 반환한다."""
    input_tokens = _usage_totals["input_tokens"]
    output_tokens = _usage_totals["output_tokens"]
    cached_tokens = _usage_totals["cached_tokens"]
    billable_input = max(0, input_tokens - cached_tokens)
    cost = (
        billable_input / 1_000_000 * _PRICE_PER_1M_INPUT
        + cached_tokens / 1_000_000 * _PRICE_PER_1M_CACHED_INPUT
        + output_tokens / 1_000_000 * _PRICE_PER_1M_OUTPUT
    )
    return {**_usage_totals, "estimated_cost_usd": round(cost, 4)}


def invoke_with_retry(llm_or_factory, messages, max_retries: int = 5, base_delay: float = 15.0):
    """llm.invoke(messages)를 실행하되, rate limit(429)이나 타임아웃처럼 일시적으로
    보이는 오류면 지수 백오프(base_delay, 2*base_delay, ...)로 재시도한다.
    다른 종류의 오류는 즉시 그대로 올린다. 성공 시 usage_metadata를 전역 집계에 더한다.

    llm_or_factory: ChatUpstage 인스턴스를 그대로 줘도 되지만(하위호환), 재시도 시에도
    같은 인스턴스(=같은 커넥션 풀)를 계속 재사용하면 한 번 죽은 연결을 계속 물고 있는
    문제가 실제로 관측됐다. 따라서 인자 없이 새 인스턴스를 만들어 반환하는 콜러블을
    넘기면, 재시도마다 완전히 새 클라이언트(=새 커넥션)로 다시 시도한다.
    """
    is_factory = callable(llm_or_factory) and not hasattr(llm_or_factory, "invoke")

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            llm = llm_or_factory() if is_factory else llm_or_factory
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm-call")
            try:
                future = executor.submit(llm.invoke, messages)
                try:
                    response = future.result(timeout=_HARD_TIMEOUT_SECONDS)
                except concurrent.futures.TimeoutError:
                    # 실제 스레드는 계속 죽은 소켓을 붙들고 있을 수 있지만(버려짐), 여기서는
                    # 더 기다리지 않고 다음 시도에서 완전히 새 연결로 다시 호출한다.
                    raise TimeoutError(
                        f"llm.invoke가 {_HARD_TIMEOUT_SECONDS:.0f}초 안에 응답하지 않음 (강제 타임아웃)"
                    ) from None
            finally:
                # wait=False: 좀비 스레드가 남아있어도 여기서 막혀서 기다리지 않는다.
                executor.shutdown(wait=False)
            usage = getattr(response, "usage_metadata", None) or {}
            _usage_totals["input_tokens"] += usage.get("input_tokens", 0)
            _usage_totals["output_tokens"] += usage.get("output_tokens", 0)
            cached = (
                usage.get("input_token_details", {}).get("cache_read", 0)
                if isinstance(usage.get("input_token_details"), dict)
                else 0
            )
            _usage_totals["cached_tokens"] += cached
            _usage_totals["call_count"] += 1
            return response
        except Exception as e:  # noqa: BLE001 - 외부 API 예외 타입이 다양해 문자열로 판별
            last_exc = e
            text = str(e).lower()
            # 강제 워치독이 던진 TimeoutError는 메시지가 한국어라 문자열 매칭에 안 걸리므로
            # isinstance로 먼저 확실하게 잡는다 (문자열 매칭은 외부 API의 영어 에러 메시지용 보조 수단).
            is_transient = (
                isinstance(e, TimeoutError)
                or "429" in text
                or "rate limit" in text
                or "too_many_requests" in text
                or "timed out" in text
                or "timeout" in text
            )
            if not is_transient or attempt == max_retries - 1:
                raise
            wait = base_delay * (2**attempt)
            print(f"[llm_utils] 일시적 오류({e}) 감지, {wait:.0f}초 대기 후 재시도 ({attempt + 1}/{max_retries})")
            time.sleep(wait)
    raise last_exc  # pragma: no cover - 위 루프에서 항상 raise/return 됨
