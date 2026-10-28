// ── UI 상태 (Zustand, SPEC §2) ────────────────────────────────
import { create } from 'zustand';
import { BOOK_ID } from './lib/constants';

// 읽기 위치(offset)는 이미 서버(progress API)에 저장돼 새로고침해도 유지되지만,
// "어떤 책을 보고 있었는지" 자체는 순수 클라이언트 상태라 브라우저에 직접 저장해둔다.
const LAST_BOOK_ID_KEY = 'spokeeper:lastBookId';

function loadInitialBookId(): string {
  if (typeof window === 'undefined') return BOOK_ID;
  return window.localStorage.getItem(LAST_BOOK_ID_KEY) || BOOK_ID;
}

function saveLastBookId(bookId: string): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(LAST_BOOK_ID_KEY, bookId);
}

export type PanelKind = 'closed' | 'relationship' | 'reminder' | 'settings';

interface SpoState {
  selectedBookId: string; // 기본값은 constants.BOOK_ID, 책 목록에서 고르면 바뀜
  spoilerSafe: boolean; // 기본 true (안심 모드 ON)
  panel: PanelKind; // 기본 closed
  readingOffset: number;
  spoilerBoundary: number;
  currentGlobalIndex: number;
  // epub.js가 페이지 넘길 때마다 즉시 알려주는 값 — 서버 왕복 없이 화면에만 반영한다.
  currentPage: number;
  totalPages: number;
  spoilerBoundaryPage: number;
  // 매 페이지 넘김마다(10페이지 배치와 무관하게) 갱신되는 최신 CFI.
  // "현재 위치까지 분석" 버튼이 실제 현재 위치를 반영하도록 강제 동기화할 때 사용.
  latestCfi: string | null;
  maskNames: boolean; // 설정: 이름 마스킹
  theme: 'light' | 'dark';
  analyzed: boolean; // 🧠 SpoKeeper Panel: '현재 위치까지 분석' 실행 여부
  requestedPage: number | null;

  setSelectedBookId: (id: string) => void;
  setSpoilerSafe: (v: boolean) => void;
  setPanel: (p: PanelKind) => void;
  togglePanel: (p: Exclude<PanelKind, 'closed'>) => void;
  setProgress: (
    readingOffset: number,
    spoilerBoundary: number,
    currentPage?: number | null,
    totalPages?: number | null,
    spoilerBoundaryPage?: number | null,
    currentCfi?: string | null,
  ) => void;
  setPage: (currentPage: number, totalPages: number) => void;
  setLatestCfi: (cfi: string) => void;
  setMaskNames: (v: boolean) => void;
  setTheme: (t: 'light' | 'dark') => void;
  setAnalyzed: (v: boolean) => void;
  requestPage: (page: number | null) => void;
}

export const useSpoStore = create<SpoState>((set) => ({
  selectedBookId: loadInitialBookId(),
  spoilerSafe: true,
  panel: 'closed',
  readingOffset: 0,
  spoilerBoundary: 0,
  currentGlobalIndex: 0,
  currentPage: 0,
  totalPages: 0,
  spoilerBoundaryPage: 0,
  latestCfi: null,
  maskNames: false,
  theme: 'light',
  analyzed: false,
  requestedPage: null,

  // 책이 바뀌면 이전 책의 읽기 위치/분석 상태를 그대로 들고 있으면 안 되므로 초기화한다.
  setSelectedBookId: (selectedBookId) => {
    saveLastBookId(selectedBookId);
    set({
      selectedBookId,
      readingOffset: 0,
      spoilerBoundary: 0,
      currentGlobalIndex: 0,
      currentPage: 0,
      totalPages: 0,
      spoilerBoundaryPage: 0,
      latestCfi: null,
      analyzed: false,
      requestedPage: null,
    });
  },
  setSpoilerSafe: (v) => set({ spoilerSafe: v }),
  setPanel: (panel) => set({ panel }),
  togglePanel: (p) => set((s) => ({ panel: s.panel === p ? 'closed' : p })),
  setProgress: (
    readingOffset,
    spoilerBoundary,
    currentPage,
    totalPages,
    spoilerBoundaryPage,
    currentCfi,
  ) =>
    set((state) => ({
      readingOffset,
      currentGlobalIndex: readingOffset,
      spoilerBoundary,
      currentPage: currentPage ?? state.currentPage,
      totalPages: totalPages ?? state.totalPages,
      spoilerBoundaryPage: spoilerBoundaryPage ?? state.spoilerBoundaryPage,
      latestCfi: currentCfi ?? state.latestCfi,
    })),
  setPage: (currentPage, totalPages) => set({ currentPage, totalPages }),
  setLatestCfi: (latestCfi) => set({ latestCfi }),
  setMaskNames: (maskNames) => set({ maskNames }),
  setTheme: (theme) => set({ theme }),
  setAnalyzed: (analyzed) => set({ analyzed }),
  requestPage: (requestedPage) => set({ requestedPage }),
}));
