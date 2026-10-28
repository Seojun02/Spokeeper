"""통합 계약 스키마 (SPEC §0.5). FE/BE/에이전트가 오직 이 형태로만 주고받는다."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

EntityType = Literal["person", "ship", "org", "place"]
NodeColor = Literal["blue", "dark"]
RelationTone = Literal["neutral", "ally", "tense"]


class Entity(BaseModel):
    id: str
    name: str
    type: EntityType
    color: NodeColor
    importance_score: int = 1
    importance_level: Literal["major", "minor"] = "minor"
    # BuildAgent가 본문에서 뽑은 인물 설명(직업/역할 등, 예: "슈퍼 주인"). 근거가
    # 없으면 비워둔다(추측 금지 원칙과 동일).
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    # 기존 스냅샷에는 없을 수 있어 response-time에 AgentResultSource가 현재 boundary
    # 이하의 스냅샷만 오름차순으로 훑어 보완한다.
    first_seen_global_index: int | None = None


class Relationship(BaseModel):
    id: str
    source: str
    target: str
    label: str
    tone: RelationTone
    description: str
    revision_offset: int
    display_label: str | None = None
    relation_category: Literal[
        "ally",
        "family",
        "conflict",
        "crime",
        "investigation",
        "deception",
        "protection",
        "romance",
        "work",
        "mystery",
        "neutral",
    ] = "neutral"
    # BuildAgent가 원본 관계를 뽑을 때 같이 판단한다: "personal"은 가족/연인/친구/원수처럼
    # 사건과 무관하게 계속 성립하는 정체성 기반 관계, "action"은 목격자/조사/공범처럼
    # 특정 사건 때문에 생긴 관계. 프론트가 기본 관계도에는 personal만 보여주고 action은
    # 인물 클릭 시에만 보여주는 데 쓴다. 구조화된 사건(EventParticipant role)에서 자동
    # 생성된 관계는 태생적으로 action이라 story_relations.py가 직접 채워 넣는다.
    relation_kind: Literal["personal", "action"] | None = None
    directionality: Literal["directed", "undirected"] = "undirected"
    relation_importance_score: int = 1
    relation_importance_level: Literal["major", "minor"] = "minor"
    first_seen_global_index: int | None = None
    first_seen_boundary: int | None = None
    is_new_at_current_position: bool = False
    detail: str | None = None
    event_name: str | None = None
    event_summary: str | None = None
    relation_role: str | None = None
    role_label: str | None = None
    role_pair_label: str | None = None
    relationship_summary: str | None = None
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    is_story_relation: bool = False
    # label(=display_label)이 실제 근거 기반 원본 라벨인지, 아니면 카테고리
    # 기본값("조사"/"보호" 등)으로 채워진 제네릭 라벨인지. is_story_relation은
    # "이 관계 그룹 안에 합성 관계가 하나라도 있었는지"라는 다른 의미로 이미
    # 쓰이고 있어(중요도 계산 등), 라벨 표시 판단에는 이 필드를 따로 쓴다.
    label_is_generic: bool = False
    # 원본(BuildAgent) relation이거나, 구조화된 사건(event_id 있음)에서 역할이 명확히
    # 나온 근거 있는 관계면 True. 리마인더 공동 언급만으로 만들어진 약한 합성 관계면
    # False — 이런 관계는 기본 관계도 엣지로는 안 그리고, 해당 인물을 클릭했을 때만
    # 보여준다(그래프가 근거 없는 추측성 연결로 뒤덮이는 걸 막으면서도 정보 자체는
    # 버리지 않기 위함).
    has_direct_evidence: bool = True
    last_seen_global_index: int | None = None
    related_events: list[dict[str, Any]] = Field(default_factory=list)


class EventParticipant(BaseModel):
    character_name: str
    role: Literal[
        "perpetrator",
        "victim",
        "investigator",
        "suspect",
        "accomplice",
        "witness",
        "target",
        "protector",
        "deceiver",
        "deceived",
        "helper",
        "beneficiary",
        "heir",
        "employer",
        "employee",
        "informant",
        "pursuer",
        "pursued",
        "threatened",
        "threatener",
        "concealer",
        "exposed",
    ]
    confidence: float = 0.7


class StoryEvent(BaseModel):
    event_id: str
    event_name: str
    event_summary: str
    participants: list[EventParticipant] = Field(default_factory=list)
    evidence: str = ""
    first_seen_chunk_offset: int | None = None
    last_seen_chunk_offset: int | None = None
    first_seen_global_index: int | None = None
    last_seen_global_index: int | None = None
    confidence: float = 0.7


class GraphJson(BaseModel):
    """계약 graph_json"""
    offset: int
    spoiler_safe: bool
    entities: list[Entity]
    relationships: list[Relationship]
    events: list[StoryEvent] = Field(default_factory=list)
    generated_at: str | None = None  # 이 스냅샷을 마지막으로 만든/갱신한 시각(ISO 8601, UTC)
    current_global_index: int | None = None
    current_page: int | None = None
    total_pages: int | None = None
    spoiler_boundary_page: int | None = None
    # 이 관계도가 실제로 어느 분석 스냅샷(경계선)을 기준으로 만들어졌는지. `offset`은
    # 요청한 현재 위치 그대로 돌려주는 값이라, 실제로 쓰인 스냅샷이 몇 번째인지는
    # 이 필드로만 알 수 있다 — 예: 현재 위치가 문단 100이어도 스냅샷은 16, 52, 88...
    # 중 가장 가까운 이전 것 하나만 쓴다.
    snapshot_boundary: int | None = None


class ReminderLine(BaseModel):
    text: str
    entity_ids: list[str]


class Reminders(BaseModel):
    """계약 reminders"""
    offset: int
    lines: list[ReminderLine]
    current_global_index: int | None = None
    current_page: int | None = None
    total_pages: int | None = None
    spoiler_boundary_page: int | None = None


# ── 서빙 메타 (계약 외 부수 리소스) ──────────────────────────────
class Part(BaseModel):
    id: str
    index: int
    title: str
    start_offset: int
    end_offset: int


class Chapter(BaseModel):
    id: str
    part_id: Optional[str] = None
    index: int
    title: str
    start_offset: int
    end_offset: int
    content: Optional[str] = None


class Book(BaseModel):
    id: str
    title: str
    author: str
    total_offset: int
    parts: list[Part]
    chapters: list[Chapter]


class BookSummary(BaseModel):
    id: str
    title: str
    author: str
    total_offset: int


class Progress(BaseModel):
    user_id: str
    book_id: str
    reading_offset: int
    spoiler_boundary: int
    # reading_offset(global_index)에 해당하는 문단의 원본 CFI. 새로고침 시 프론트(epub.js)가
    # 이 값으로 rendition.display(cfi)를 호출해 마지막으로 읽던 위치로 복원한다.
    cfi: str | None = None
    # 신규 위치 계약. 기존 필드는 삭제하지 않고 같은 값을 additive alias로 제공한다.
    current_cfi: str | None = None
    current_global_index: int
    reading_page: int | None = None
    current_page: int | None = None
    total_pages: int | None = None
    spoiler_boundary_page: int | None = None


class ProgressUpdate(BaseModel):
    # reading_offset은 epub.js 연동 전 구버전 클라이언트 호환용. cfi가 오면 그쪽을 우선한다.
    reading_offset: int = 0
    # epub.js의 rendition.on('relocated') 이벤트가 주는 원본 CFI 문자열.
    # 서버에서 book_cfi_index 기준 global_index로 변환한다 (프론트/백엔드 CFI 파싱 로직
    # 이중 구현으로 어긋나는 걸 피하기 위해, 변환은 항상 서버에서만 한다).
    cfi: str | None = None
    current_cfi: str | None = None
    current_global_index: int | None = None
    reading_page: int | None = None
    current_page: int | None = None
    total_pages: int | None = None
    user_id: str = "local"
    # true면 단조증가 규칙을 무시하고 spoiler_boundary를 reading_offset으로 강제 설정한다.
    # 재독(다시 읽기) 모드: 이미 도달한 지점보다 앞으로 되돌아가 스포일러를 다시 가리고 싶을 때 사용.
    force: bool = False
