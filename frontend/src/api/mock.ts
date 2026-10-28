// ── Mock 픽스처 (MOCKS.md 그대로) ──────────────────────────────
// VITE_USE_MOCK=true 일 때 client 레이어가 이 값을 반환한다.
// 아래 숫자들은 실제 책의 chunk/page offset이 아니라 mock 전용 global_index 흉내값이다.
// mock boundary 버킷팅: <215 → 150, 215..379 → 215, >=380 → 380

import type { Book, Chapter, GraphJson, Progress, Reminders } from './types';

export const BOOK_MIST: Book = {
  id: 'b_mist',
  title: '안개 궤도',
  author: '—',
  total_offset: 430,
  parts: [
    { id: 'p1', index: 1, title: '', start_offset: 0, end_offset: 199 },
    { id: 'p2', index: 2, title: '은폐', start_offset: 200, end_offset: 430 },
  ],
  chapters: [
    { id: 'ch1', part_id: 'p1', index: 1, title: '신호', start_offset: 0, end_offset: 99 },
    { id: 'ch2', part_id: 'p1', index: 2, title: '균열', start_offset: 100, end_offset: 199 },
    { id: 'ch3', part_id: 'p2', index: 3, title: '추적자들의 전조', start_offset: 200, end_offset: 430 },
  ],
};

export const CHAPTER_3: Chapter = {
  id: 'ch3',
  index: 3,
  title: '추적자들의 전조',
  start_offset: 200,
  end_offset: 430,
  content:
    '로그 차단이 끝난 지 얼마 지나지 않아 통제소 하부 출입문이 거칠게 열렸다. 방전 마스크를 착용한 무장 요원들이 통로를 가로질러 들어섰다.\n\n' +
    '그들 사이로 걸어 들어온 인물은 강 국장의 직속 집행관인 윤 팀장이였다. 그는 민우의 콘솔 앞으로 다가가 스크린을 내려다봤다.\n\n' +
    '서현은 태연하게 모니터를 가려 서며 백업 디스크를 주머니 깊은 곳으로 밀어 넣었다.',
};

// 챕터 1·2는 데모 본문이 SPEC에 없어 placeholder로 채운다.
export const CHAPTER_1: Chapter = {
  id: 'ch1',
  index: 1,
  title: '신호',
  start_offset: 0,
  end_offset: 99,
  content:
    '민우는 심야의 통제실에서 홀로 수신 로그를 넘기고 있었다. 잡음 사이로 낯선 규칙성이 스쳤다.\n\n' +
    '서현이 커피 두 잔을 들고 들어와 옆자리에 앉았다. 두 사람은 오래된 동료 연구원이었다.\n\n' +
    '화면 끝에서, 오래전 실종된 탐사선 아틀라스 호의 고유 신호가 희미하게 깜빡였다.',
};

export const CHAPTER_2: Chapter = {
  id: 'ch2',
  index: 2,
  title: '균열',
  start_offset: 100,
  end_offset: 199,
  content:
    '신호는 매일 밤 조금씩 또렷해졌다. 민우는 좌표를 역산했고 서현은 로그를 백업했다.\n\n' +
    '어느 새벽, 서현은 신호 헤더 속에서 낯익은 보안 서명 하나를 발견했다. 그것은 상부의 것이었다.\n\n' +
    '두 사람은 자신들이 무엇을 건드렸는지 아직 알지 못했다.',
};

export const CHAPTERS_BY_INDEX: Record<number, Chapter> = {
  1: CHAPTER_1,
  2: CHAPTER_2,
  3: CHAPTER_3,
};

// progress는 mock에서 메모리 상태로 관리한다.
// reading_offset/spoiler_boundary 필드명은 백엔드 계약을 따르지만 값은 mock global_index다.
export const mockProgress: Progress = {
  user_id: 'local',
  book_id: 'b_mist',
  reading_offset: 380,
  current_global_index: 380,
  spoiler_boundary: 380,
};

// ── graph 픽스처 (mock global_index 버킷별) ────────────────────
const MOCK_BOUNDARY_EMPTY = 150;
const MOCK_BOUNDARY_C1 = 215;
const MOCK_BOUNDARY_C3 = 380;

const GRAPH_150: GraphJson = {
  offset: MOCK_BOUNDARY_EMPTY,
  spoiler_safe: true,
  entities: [],
  relationships: [],
};

const GRAPH_215: GraphJson = {
  offset: MOCK_BOUNDARY_C1,
  spoiler_safe: true,
  entities: [
    { id: 'e_minu', name: '민우', type: 'person', color: 'blue' },
    { id: 'e_seohyun', name: '서현', type: 'person', color: 'blue' },
    { id: 'e_atlas', name: '아틀라스 호', type: 'ship', color: 'blue' },
  ],
  relationships: [
    {
      id: 'r1', source: 'e_minu', target: 'e_seohyun', label: '동료 연구원', tone: 'ally',
      description: '통제실에서 함께 아틀라스 호 신호를 확인함.', revision_offset: 40,
    },
    {
      id: 'r2', source: 'e_minu', target: 'e_atlas', label: '신호 추적', tone: 'neutral',
      description: '민우가 실종 탐사선의 고유 신호를 포착함.', revision_offset: 120,
    },
  ],
};

const GRAPH_380: GraphJson = {
  offset: MOCK_BOUNDARY_C3,
  spoiler_safe: true,
  entities: [
    { id: 'e_minu', name: '민우', type: 'person', color: 'blue' },
    { id: 'e_seohyun', name: '서현', type: 'person', color: 'blue' },
    { id: 'e_atlas', name: '아틀라스 호', type: 'ship', color: 'blue' },
    { id: 'e_kang', name: '강 국장', type: 'person', color: 'dark' },
    { id: 'e_yoon', name: '윤 팀장', type: 'person', color: 'dark' },
  ],
  relationships: [
    {
      id: 'r1', source: 'e_minu', target: 'e_seohyun', label: '동료 연구원', tone: 'ally',
      description: '통제실에서 함께 아틀라스 호 신호를 확인함.', revision_offset: 40,
    },
    {
      id: 'r2', source: 'e_minu', target: 'e_atlas', label: '신호 추적', tone: 'neutral',
      description: '민우가 실종 탐사선의 고유 신호를 포착함.', revision_offset: 120,
    },
    {
      id: 'r3', source: 'e_seohyun', target: 'e_kang', label: '은폐 의혹', tone: 'tense',
      description: '서현이 신호 속 강 국장의 보안 서명을 확인함.', revision_offset: 260,
    },
    {
      id: 'r4a', source: 'e_yoon', target: 'e_minu', label: '압박 조사', tone: 'tense',
      description: '윤 팀장이 무장 요원들과 통제실에 진입함.', revision_offset: 370,
    },
    {
      id: 'r4b', source: 'e_yoon', target: 'e_seohyun', label: '압박 조사', tone: 'tense',
      description: '윤 팀장이 무장 요원들과 통제실에 진입함.', revision_offset: 370,
    },
  ],
};

/** mock global_index boundary → 버킷 픽스처 선택 (MOCKS.md 규칙) */
export function pickGraph(mockBoundaryGlobalIndex: number): GraphJson {
  if (mockBoundaryGlobalIndex >= MOCK_BOUNDARY_C3) return GRAPH_380;
  if (mockBoundaryGlobalIndex >= MOCK_BOUNDARY_C1) return GRAPH_215;
  return GRAPH_150;
}

const REMINDERS_380: Reminders = {
  offset: MOCK_BOUNDARY_C3,
  lines: [
    { text: '민우와 서현은 통제실에서 아틀라스 호의 신호를 함께 확인했다.', entity_ids: ['e_minu', 'e_seohyun'] },
    { text: '서현은 신호 속에서 강 국장의 보안 서명을 발견해 은폐 의혹을 품었다.', entity_ids: ['e_seohyun', 'e_kang'] },
    { text: '강 국장의 집행관 윤 팀장이 무장 요원들과 통제실에 진입해 압박을 시작했다.', entity_ids: ['e_yoon', 'e_minu', 'e_seohyun'] },
  ],
};

const REMINDERS_215: Reminders = {
  offset: MOCK_BOUNDARY_C1,
  lines: [
    { text: '민우와 서현은 통제실에서 아틀라스 호의 신호를 함께 확인했다.', entity_ids: ['e_minu', 'e_seohyun'] },
    { text: '민우가 실종 탐사선 아틀라스 호의 고유 신호를 포착했다.', entity_ids: ['e_minu', 'e_atlas'] },
  ],
};

const REMINDERS_150: Reminders = { offset: MOCK_BOUNDARY_EMPTY, lines: [] };

export function pickReminders(mockBoundaryGlobalIndex: number): Reminders {
  if (mockBoundaryGlobalIndex >= MOCK_BOUNDARY_C3) return REMINDERS_380;
  if (mockBoundaryGlobalIndex >= MOCK_BOUNDARY_C1) return REMINDERS_215;
  return REMINDERS_150;
}
