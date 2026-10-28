// ── 통합 계약 타입 (SPEC §0.5) ────────────────────────────────
// FE / BE / 에이전트가 오직 이 스키마로만 주고받는다. 절대 변경 금지.

export type EntityType = 'person' | 'ship' | 'org' | 'place';
export type NodeColor = 'blue' | 'dark';
export type RelationTone = 'neutral' | 'ally' | 'tense';

export interface Entity {
  id: string;
  name: string;
  type: EntityType;
  color: NodeColor;
  importance_score?: number;
  importance_level?: 'major' | 'minor';
  /** 본문에서 확인된 인물 설명(직업/역할 등). 근거 없으면 비어있을 수 있음. */
  description?: string | null;
  aliases?: string[];
}

export interface Relationship {
  id: string;
  source: string; // entity id
  target: string; // entity id
  label: string;
  tone: RelationTone;
  description: string;
  revision_offset: number;
  display_label?: string | null;
  relation_category?:
    | 'ally'
    | 'family'
    | 'conflict'
    | 'crime'
    | 'investigation'
    | 'deception'
    | 'protection'
    | 'romance'
    | 'work'
    | 'mystery'
    | 'neutral';
  directionality?: 'directed' | 'undirected';
  relation_importance_score?: number;
  relation_importance_level?: 'major' | 'minor';
  first_seen_global_index?: number | null;
  first_seen_boundary?: number | null;
  is_new_at_current_position?: boolean;
  detail?: string | null;
  event_name?: string | null;
  event_summary?: string | null;
  relation_role?: string | null;
  role_label?: string | null;
  role_pair_label?: string | null;
  relationship_summary?: string | null;
  evidence?: string[];
  confidence?: number;
  is_story_relation?: boolean;
  /** 원본 라벨이나 구조화된 사건 근거가 있으면 true. false면 리마인더 공동 언급만으로
   *  만든 약한 추측성 관계 — 기본 관계도 엣지로는 안 그리고, 연결된 인물을 클릭했을
   *  때만 보여준다. */
  has_direct_evidence?: boolean;
  /** "personal": 가족/연인/친구/원수처럼 사건과 무관하게 계속 성립하는 정체성 기반 관계.
   *  "action": 목격자/조사/공범처럼 특정 사건 때문에 생긴 관계. BuildAgent가 원본 관계를
   *  뽑을 때 직접 판단해서 채운다(구버전 데이터는 null일 수 있음). */
  relation_kind?: 'personal' | 'action' | null;
  last_seen_global_index?: number | null;
  related_events?: Array<Record<string, unknown>>;
}

/** 계약 graph_json */
export interface GraphJson {
  offset: number;
  spoiler_safe: boolean;
  entities: Entity[];
  relationships: Relationship[];
  events?: Array<Record<string, unknown>>;
  /** 이 스냅샷을 마지막으로 만든/갱신한 시각(ISO 8601, UTC). 없으면 예전 데이터. */
  generated_at?: string | null;
  current_global_index?: number | null;
  current_page?: number | null;
  total_pages?: number | null;
  spoiler_boundary_page?: number | null;
  /** 이 관계도가 실제로 어느 분석 스냅샷(경계선, global_index)을 기준으로
   *  만들어졌는지. 현재 읽는 위치(offset)와는 다를 수 있다 — 그 위치 이전의
   *  가장 가까운 스냅샷 하나만 쓰기 때문이다. */
  snapshot_boundary?: number | null;
}

export interface ReminderLine {
  text: string;
  entity_ids: string[];
}

/** 계약 reminders */
export interface Reminders {
  offset: number;
  lines: ReminderLine[];
  current_global_index?: number | null;
  current_page?: number | null;
  total_pages?: number | null;
  spoiler_boundary_page?: number | null;
}

// ── 서빙 메타 (계약 외 부수 리소스) ────────────────────────────
export interface Part {
  id: string;
  index: number;
  title: string;
  start_offset: number;
  end_offset: number;
}

export interface Chapter {
  id: string;
  part_id?: string;
  index: number;
  title: string;
  start_offset: number;
  end_offset: number;
  content?: string;
}

export interface Book {
  id: string;
  title: string;
  author: string;
  total_offset: number;
  parts: Part[];
  chapters: Chapter[];
}

export interface Progress {
  user_id: string;
  book_id: string;
  reading_offset: number;
  spoiler_boundary: number;
  cfi?: string | null;
  current_cfi?: string | null;
  current_global_index: number;
  reading_page?: number | null;
  current_page?: number | null;
  total_pages?: number | null;
  spoiler_boundary_page?: number | null;
}

export interface BookSummary {
  id: string;
  title: string;
  author: string;
  total_offset: number;
}

export interface UploadResult {
  book_id: string;
  reused: boolean;
  paragraph_count: number;
}

export interface AnalysisStatus {
  status: 'unknown' | 'running' | 'done' | 'failed';
  completed: number;
  total: number;
  error: string | null;
}
