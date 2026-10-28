// ── TanStack Query 훅 (SPEC §2 서버상태) ──────────────────────
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

export function useBooks() {
  return useQuery({
    queryKey: ['books'],
    queryFn: () => api.getBooks(),
  });
}

export function useUploadBook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.uploadBook(file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['books'] });
    },
  });
}

/** 업로드 직후 분석 진행률을 폴링한다. status가 running일 때만 2초마다 다시 불러오고,
 *  done/failed가 되면 폴링을 멈춘다. enabled=false면 아예 요청하지 않는다. */
export function useAnalysisStatus(bookId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['analysisStatus', bookId],
    queryFn: () => api.getAnalysisStatus(bookId as string),
    enabled: enabled && !!bookId,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 2000 : false),
  });
}

export function useDeleteBook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (bookId: string) => api.deleteBook(bookId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['books'] });
    },
  });
}

export function useBook(bookId: string) {
  return useQuery({
    queryKey: ['book', bookId],
    queryFn: () => api.getBook(bookId),
  });
}

export function useChapter(bookId: string, index: number) {
  return useQuery({
    queryKey: ['chapter', bookId, index],
    queryFn: () => api.getChapter(bookId, index),
    enabled: index > 0,
  });
}

/** currentGlobalIndex가 실제 필터 기준이고 currentPage/totalPages는 응답 표시 메타다. */
export function useGraph(
  bookId: string,
  currentGlobalIndex: number,
  currentPage: number,
  totalPages: number,
  spoilerSafe: boolean,
) {
  return useQuery({
    // currentPage는 표시용 파생값이다. global index가 아직 이전 값인 상태에서 page만
    // 먼저 바뀌었다고 같은 graph를 재요청하지 않는다. progress 응답으로 실제
    // currentGlobalIndex가 확정되는 즉시 최신 page 메타와 함께 한 번만 조회한다.
    queryKey: ['graph', bookId, currentGlobalIndex, spoilerSafe],
    queryFn: () => api.getGraph(bookId, currentGlobalIndex, currentPage, totalPages, !spoilerSafe),
  });
}

export function useReminders(
  bookId: string,
  currentGlobalIndex: number,
  currentPage: number,
  totalPages: number,
  entityId?: string,
) {
  return useQuery({
    queryKey: ['reminders', bookId, currentGlobalIndex, entityId ?? null],
    queryFn: () => api.getReminders(bookId, currentGlobalIndex, currentPage, totalPages, entityId),
  });
}

export function useProgress(bookId: string) {
  return useQuery({
    queryKey: ['progress', bookId],
    queryFn: () => api.getProgress(bookId),
  });
}

export function usePutProgress(bookId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: number | Parameters<typeof api.putProgress>[1]) =>
      typeof args === 'number'
        ? api.putProgress(bookId, { offset: args })
        : api.putProgress(bookId, args),
    onSuccess: (data) => {
      qc.setQueryData(['progress', bookId], data);
    },
  });
}
