import { useEffect, useRef, useState } from 'react';
import ePub, { type Book, type Rendition } from 'epubjs';
import { bookFileUrl } from '../api/client';
import { useProgress, usePutProgress } from '../api/hooks';
import { useSpoStore } from '../store';

type LocationsWithTotal = {
  locationFromCfi: (cfi: string) => number;
  cfiFromLocation: (location: number) => string;
  total: number;
  epubcfi: { compare: (a: string, b: string) => number };
};

function charsForViewport(width: number, height: number): number {
  // epub.js locations는 문자 단위이므로 현재 viewport가 담을 수 있는 문자 수를 기준으로
  // 다시 생성한다. 화면/폰트 reflow 시 같은 CFI의 표시 page가 새로 계산된다.

  const columns = Math.max(24, Math.floor(width / 13));
  const rows = Math.max(10, Math.floor(height / 34));
  return Math.max(300, Math.min(1800, columns * rows));
}

// 페이지 번호/슬라이더 위치는 서버 응답을 기다릴 필요 없이 클라이언트에서 바로 계산되므로
// (epub.js locations가 이미 로컬에 있음) 즉시 반영한다. 서버 확정 상태(reading_offset,
// spoiler_boundary 등)만 이 지연 이후 한 번 저장한다 — 슬라이더를 빠르게 끌 때마다
// 매번 요청을 쏘지 않기 위한 최소한의 디바운스.
const PROGRESS_FLUSH_DELAY_MS = 150;

export function EpubJsReader() {
  const bookId = useSpoStore((s) => s.selectedBookId);
  const setProgress = useSpoStore((s) => s.setProgress);
  const setPage = useSpoStore((s) => s.setPage);
  const setLatestCfi = useSpoStore((s) => s.setLatestCfi);
  const totalPages = useSpoStore((s) => s.totalPages);
  const latestCfi = useSpoStore((s) => s.latestCfi);
  const requestedPage = useSpoStore((s) => s.requestedPage);
  const requestPage = useSpoStore((s) => s.requestPage);
  const putProgress = usePutProgress(bookId);
  const { data: progress, isLoading: progressLoading } = useProgress(bookId);

  const containerRef = useRef<HTMLDivElement>(null);
  const bookRef = useRef<Book | null>(null);
  const renditionRef = useRef<Rendition | null>(null);
  const viewportRef = useRef({ width: 0, height: 0 });
  const syncSequenceRef = useRef(0);
  const flushTimerRef = useRef<number | null>(null);
  // 페이지 번호를 book.locations(글자 수 기준 근사 구간)로 매번 다시 계산하는 한,
  // 한 번의 "다음" 클릭이 실제로는 location 2~3칸을 건너뛰거나(점프) 반대로 전혀
  // 안 움직이는(반복) 문제를 근본적으로 피할 수 없었다 — click 한 번이 relocated
  // 이벤트를 여러 번 일으킬 수도 있어서, 방향만 기억해뒀다가 한 번 써먹는 방식도
  // 두 번째 이벤트에서 다시 location 계산으로 새버렸다. 그래서 아예 "화면 페이지는
  // 클릭 한 번에 정확히 한 장씩 움직인다"는 사실 자체를 유일한 진실로 삼는다 —
  // 페이지 번호를 클릭 핸들러에서 동기적으로 직접 증감시키고, relocated 이벤트는
  // (1) 서버에 보낼 CFI 동기화, (2) atStart/atEnd 경계 보정에만 쓴다. location
  // 기반 계산은 이 카운터가 아직 없는 최초 로드/슬라이더 점프 때만 쓴다.
  const pageCounterRef = useRef(0);
  const totalPagesRef = useRef(0);

  const [loadError, setLoadError] = useState<string | null>(null);
  const [locationsReady, setLocationsReady] = useState(false);
  // 페이지 수는 글자 수 기반 근사치라 실제 EPUB의 시작/끝과 다를 수 있다.
  // 이동 버튼은 rendition의 relocated 이벤트가 주는 실제 경계 상태로 제어한다.
  const [atStart, setAtStart] = useState(false);
  const [atEnd, setAtEnd] = useState(false);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      // 여기서는 실제 컨테이너 크기를 계속 기록만 해둔다(다음 책을 열 때
      // charsForViewport 계산에 씀) — 리사이즈가 일어났다고 locations를 다시
      // 만들거나 book/rendition을 재생성하지는 않는다. 예전엔 사이드 패널을
      // 열고 닫을 때마다 locations를 다시 계산해서, 실제로 읽는 위치는 그대로인데
      // 페이지 번호만 엉뚱하게 튀는 문제가 있었다(예: 1페이지 -> 8페이지, 내용은
      // 안 바뀜) — 시각적 레이아웃은 CSS width:100%로 이미 잘 따라가므로, 페이지
      // 번호 계산까지 매번 다시 할 필요가 없다.
      const width = Math.round(entry.contentRect.width);
      const height = Math.round(entry.contentRect.height);
      viewportRef.current = { width, height };
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!containerRef.current || progressLoading) return;
    syncSequenceRef.current += 1;
    setLoadError(null);
    setLocationsReady(false);
    setPage(0, 0);

    const book = ePub(bookFileUrl(bookId), { openAs: 'epub' });
    bookRef.current = book;
    const rendition = book.renderTo(containerRef.current, {
      width: '100%',
      height: '100%',
      flow: 'paginated',
    });
    renditionRef.current = rendition;

    let cancelled = false;
    pageCounterRef.current = 0;
    totalPagesRef.current = 0;

    // book.locations(글자 수 기준 근사 구간)로 페이지 번호를 계산하는 건, 최초
    // 로드나 슬라이더 점프처럼 "지금이 몇 페이지인지 전혀 모르는" 상황에서
    // 대략적인 시작값을 잡을 때만 쓴다. 그 이후로는 pageCounterRef(클릭 핸들러가
    // 직접 증감시키는 값)를 유일한 진실로 삼는다 — relocated 이벤트가 한 번의
    // 클릭에 여러 번 발생해도(설정에 따라 그럴 수 있음) location을 다시 계산하지
    // 않으므로 값이 흔들리지 않는다.
    const estimateFromLocation = (cfi: string): number => {
      const locations = book.locations as unknown as LocationsWithTotal;
      const locationIndex = locations.locationFromCfi(cfi);
      if (typeof locationIndex !== 'number') return 1;
      return locationIndex + 1;
    };

    const reportPage = (cfi: string, hints?: { atStart?: boolean; atEnd?: boolean }) => {
      const locations = book.locations as unknown as LocationsWithTotal;
      const totalLocationCount = locations.total;
      if (totalLocationCount <= 0) return null;

      if (totalPagesRef.current <= 0) {
        totalPagesRef.current = totalLocationCount + 1;
      }

      if (hints?.atStart) {
        // epub.js가 "책의 진짜 첫 페이지"라고 직접 알려주는 신호 — 무조건 1페이지.
        pageCounterRef.current = 1;
      } else if (hints?.atEnd) {
        // 진짜 끝에 닿았다 — 지금까지 카운터가 없었다면(예: 마지막 페이지에서
        // 새로고침) location 추정치로, 있었다면 그 값 그대로 총 페이지 수로 확정.
        pageCounterRef.current = pageCounterRef.current > 0 ? pageCounterRef.current : estimateFromLocation(cfi);
        totalPagesRef.current = pageCounterRef.current;
      } else if (pageCounterRef.current <= 0) {
        // 아직 기준이 없다(최초 로드, 슬라이더 점프 직후) — 근사치로 시작.
        pageCounterRef.current = Math.min(estimateFromLocation(cfi), totalPagesRef.current);
      } else if (pageCounterRef.current >= totalPagesRef.current) {
        // 아직 끝이 아닌데(atEnd 아님) 추정 총 페이지에 닿았다면 추정치가
        // 작았던 것 — 늘려서 "N/N인데 다음 버튼이 살아있는" 모순을 없앤다.
        totalPagesRef.current = pageCounterRef.current + 1;
      }
      // 그 외(카운터가 이미 있고, 아직 총 페이지 수 미만인 일반적인 클릭 이동)는
      // pageCounterRef.current를 그대로 둔다 — 클릭 핸들러가 이미 동기적으로
      // 증감시켜 놓았으므로 여기서 다시 계산할 필요가 없다.

      return { page: pageCounterRef.current, totalPages: totalPagesRef.current };
    };

    const flushProgress = (cfi: string, pagination: { page: number; totalPages: number }) => {
      const sequence = ++syncSequenceRef.current;
      putProgress.mutate(
        {
          currentCfi: cfi,
          currentPage: pagination.page,
          totalPages: pagination.totalPages,
        },
        {
          onSuccess: (next) => {
            if (sequence !== syncSequenceRef.current) return;
            setProgress(
              next.reading_offset,
              next.spoiler_boundary,
              next.current_page,
              next.total_pages,
              next.spoiler_boundary_page,
              next.current_cfi,
            );
            setLocationsReady(true);
          },
        },
      );
    };

    const syncLocation = (cfi: string, hints?: { atStart?: boolean; atEnd?: boolean }) => {
      const pagination = reportPage(cfi, hints);
      setLatestCfi(cfi);
      setAtStart(Boolean(hints?.atStart));
      setAtEnd(Boolean(hints?.atEnd));
      if (!pagination) return;

      // 페이지 번호/슬라이더는 서버 응답을 기다리지 않고 여기서 바로 갱신한다 —
      // epub.js locations가 이미 로컬에 있어서 즉시 계산 가능하다. 서버 확정 상태
      // (reading_offset/spoiler_boundary 등)만 디바운스 후 저장한다.
      setPage(pagination.page, pagination.totalPages);

      if (flushTimerRef.current !== null) window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = window.setTimeout(() => {
        flushTimerRef.current = null;
        flushProgress(cfi, pagination);
      }, PROGRESS_FLUSH_DELAY_MS);
    };

    book.ready
      .then(() => {
        const { width, height } = viewportRef.current;
        return book.locations.generate(charsForViewport(width || 760, height || 560));
      })
      .then(() => {
        if (cancelled) return undefined;
        const savedCfi = latestCfi ?? progress?.current_cfi ?? progress?.cfi ?? undefined;
        return rendition.display(savedCfi).then(() => {
          const current = rendition.currentLocation() as
            | { start?: { cfi: string }; atStart?: boolean; atEnd?: boolean }
            | undefined;
          if (current?.start?.cfi) {
            syncLocation(current.start.cfi, { atStart: current.atStart, atEnd: current.atEnd });
          }
        });
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : 'EPUB을 불러오지 못했습니다.');
      });

    rendition.on(
      'relocated',
      (location: { start: { cfi: string }; atStart?: boolean; atEnd?: boolean }) => {
        syncLocation(location.start.cfi, { atStart: location.atStart, atEnd: location.atEnd });
      },
    );

    return () => {
      cancelled = true;
      // 디바운스 타이머가 아직 안 끝난 상태로 책을 나가거나 바꾸면 마지막 위치
      // 저장이 유실될 수 있어 여기서 한 번 더 확실히 저장한다.
      if (flushTimerRef.current !== null) {
        window.clearTimeout(flushTimerRef.current);
        flushTimerRef.current = null;
        const current = rendition.currentLocation() as { start?: { cfi: string } } | undefined;
        if (current?.start?.cfi) {
          const pagination = reportPage(current.start.cfi);
          if (pagination) flushProgress(current.start.cfi, pagination);
        }
      }
      rendition.destroy();
      book.destroy();
      renditionRef.current = null;
      bookRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookId, progressLoading]);

  useEffect(() => {
    if (!locationsReady || requestedPage === null || !renditionRef.current || !bookRef.current) return;
    const locations = bookRef.current.locations as unknown as LocationsWithTotal;
    // 표시 중인 총 페이지 수(끝 도달 시 실측 보정될 수 있음)와 location 개수가
    // 다를 수 있으므로, 요청 페이지를 비율로 환산해서 location index로 매핑한다.
    const ratio = totalPages > 1 ? (requestedPage - 1) / (totalPages - 1) : 0;
    const target = Math.max(0, Math.min(Math.round(ratio * locations.total), locations.total));
    const cfi = locations.cfiFromLocation(target);
    // 슬라이더로 점프한 목표 페이지를 그대로 카운터의 새 기준점으로 삼는다 —
    // 그래야 이후 "다음/이전" 클릭이 여기서부터 정확히 ±1로 이어진다.
    pageCounterRef.current = requestedPage;
    requestPage(null);
    if (cfi) void renditionRef.current.display(cfi);
  }, [locationsReady, requestPage, requestedPage, totalPages]);

  return (
    <div className="relative mx-auto flex h-full w-full max-w-[1080px] items-start justify-center px-12">
      <section className="reader-page relative h-full w-full max-w-[780px] min-w-0 overflow-hidden border border-[#dedbd1] bg-[#fffdfa] px-5 py-6 sm:px-10 lg:px-[52px] lg:py-11">
        {loadError ? (
          <div className="grid h-full place-items-center text-center">
            <p className="max-w-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-600">
              {loadError}
            </p>
          </div>
        ) : (
          <div ref={containerRef} className="h-full w-full overflow-hidden" />
        )}
      </section>
      <button
        type="button"
        onClick={() => {
          if (pageCounterRef.current <= 1) return;
          // 클릭한 순간 바로 페이지 번호를 확정한다 — relocated 이벤트(비동기,
          // 한 클릭에 여러 번 올 수 있음)를 기다리지 않는다. 화면 페이지는
          // 정의상 클릭 한 번에 정확히 한 장씩만 움직이므로 이게 항상 정확하다.
          pageCounterRef.current -= 1;
          setPage(pageCounterRef.current, totalPagesRef.current);
          renditionRef.current?.prev();
        }}
        disabled={!locationsReady || atStart}
        className="absolute left-0 top-1/2 z-20 grid h-10 w-10 -translate-y-1/2 place-items-center rounded-full border border-[#d8d8ca] bg-[#faf9f5] text-2xl font-medium text-[#283126] shadow-sm transition hover:border-[#283126] hover:bg-[#fffdfa] disabled:cursor-default disabled:opacity-45"
        aria-label="이전 페이지"
      >
        ‹
      </button>
      <button
        type="button"
        onClick={() => {
          if (totalPagesRef.current > 0 && pageCounterRef.current >= totalPagesRef.current) return;
          pageCounterRef.current += 1;
          setPage(pageCounterRef.current, totalPagesRef.current);
          renditionRef.current?.next();
        }}
        disabled={!locationsReady || atEnd}
        className="absolute right-0 top-1/2 z-20 grid h-10 w-10 -translate-y-1/2 place-items-center rounded-full border border-[#d8d8ca] bg-[#faf9f5] text-2xl font-medium text-[#283126] shadow-sm transition hover:border-[#283126] hover:bg-[#fffdfa] disabled:cursor-default disabled:opacity-45"
        aria-label="다음 페이지"
      >
        ›
      </button>
    </div>
  );
}
