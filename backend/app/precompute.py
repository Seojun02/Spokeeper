"""에이전트 결과 → 계약 JSON precompute 파이프라인.

'다음 에이전트' 담당자의 진입점:
- (A) 이미 계산된 build 결과 시퀀스가 있으면 `build_entries()` 로 계약 JSON 생성.
- (B) EPUB 원본에서 바로 돌리려면 `precompute_from_epub()` (UPSTAGE_API_KEY 필요).

산출물은 `AgentResultSource.from_json_file()` 이 읽는 형식이며, 이를 로드해
`main.py` 의 `content_source` 로 주입하면 라우트/스키마 변경 없이 실데이터 서빙이 된다.

핵심: 각 관계의 `revision_offset` 은 그 관계가 '처음 등장한 경계선' 으로 고정된다
(누적 그래프에서 이후 경계선에도 계속 보이지만 최초 등장 시점을 유지).
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from . import agent_adapter as ad

# precompute 결과 저장 위치
STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "precomputed"
_GRAPH_POSITION_FIELDS = {
    "offset",
    "boundary",
    "revision_offset",
    "first_seen_global_index",
    "last_seen_global_index",
}


def build_analysis_boundaries(chunks: list[dict], chunks_per_snapshot: int = 1) -> list[int]:
    """Return cumulative chunk boundaries without dropping intermediate data.

    A relationship first becomes spoiler-safe at the end of the chunk that
    introduced it.  The old upload schedule grouped five chunks per snapshot,
    so several pages of entities and relationships appeared at once.  One
    chunk per snapshot keeps the stored boundary aligned with the finest
    position that the analysis pipeline currently knows.
    """

    if chunks_per_snapshot <= 0:
        raise ValueError("chunks_per_snapshot must be greater than zero")
    offsets = [int(chunk["offset"]) for chunk in chunks]
    if not offsets:
        return []
    boundaries = offsets[chunks_per_snapshot - 1 :: chunks_per_snapshot]
    if not boundaries or boundaries[-1] != offsets[-1]:
        boundaries.append(offsets[-1])
    return boundaries


def _build_single_entry(
    chunk_boundary: int,
    result: dict,
    first_seen: dict[str, int],
    book_id: str | None,
    canonical_registry: list[dict],
    global_name_map: dict[str, str],
    prev_raw_names: set[str],
) -> tuple[dict, dict[str, str]]:
    """경계선 하나에 대해 인물 병합 → VerifierAgent → ReminderWriterAgent →
    IndirectLeakageJudge를 체이닝해서 계약 entry 하나를 만든다.

    인물 병합은 "새로 등장한 인물만" canonical_registry와 비교하는 증분 방식
    (canonicalize_new_characters)이라, 인물 수가 아무리 늘어나도 매 경계선마다
    LLM에 보여주는 비교 대상은 작게 유지된다. canonical_registry/global_name_map/
    prev_raw_names는 호출자가 경계선을 넘어 계속 누적/재사용하는 상태다.

    주의: 이 함수가 반환하는 entry의 boundary/offset은 아직 내부 분석용 chunk
    offset이다. 저장 직전 `remap_entries_to_global_index()`에서 global_index로 통일한다.

    반환값은 (entry, rename_map) — canonicalize_new_characters가 이번 호출에서
    기존 인물의 대표 이름을 더 명확한 표기로 바꾼 경우(preferred_display_name),
    rename_map({이전 대표 이름: 새 대표 이름})이 채워진다. 호출자는 이미 만들어둔
    과거 entries에도 이 rename을 소급 적용해야 한다(그러지 않으면 같은 인물이
    경계선 전후로 다른 이름을 갖게 된다).
    """
    from agents.character_entity_filter import filter_generic_role_entities
    from agents.indirect_leakage_judge import judge_reminders
    from agents.reminder_writer_agent import write_reminders
    from agents.verifier_agent import _apply_character_name_map, canonicalize_new_characters, verify_build_result

    result = filter_generic_role_entities(result, book_id=book_id)

    raw_characters = result.get("characters", [])
    new_characters = [c for c in raw_characters if c.get("name", "") not in prev_raw_names]
    prev_raw_names.update(c.get("name", "") for c in raw_characters)

    new_map, rename_map = canonicalize_new_characters(new_characters, canonical_registry, book_id=book_id)
    global_name_map.update(new_map)

    if rename_map:
        # ConsolidationAgent의 merge_map 소급 적용과 같은 패턴 — 이미 누적된
        # global_name_map 값이 옛 대표 이름을 가리키고 있으면 새 이름으로 체이닝.
        for raw_name, mapped_name in list(global_name_map.items()):
            if mapped_name in rename_map:
                global_name_map[raw_name] = rename_map[mapped_name]
        global_name_map.update(rename_map)

    if global_name_map:
        result, _, _, _ = _apply_character_name_map(result, global_name_map)

    # 1차 가드: 근거 없는 relations/events 제거
    verified = verify_build_result(result, book_id=book_id)

    # 이 chunk 경계선에서 처음 보이는 관계의 revision_offset 을 chunk_boundary 로 고정
    for rid in ad.build_relation_ids(verified):
        first_seen.setdefault(rid, chunk_boundary)

    graph = ad.to_graph_json(verified, chunk_boundary, revision_offsets=first_seen)

    # 2차 가드: 서술형으로 재작성 → 3차 가드: 암시/복선 판정 후 최종 확정
    written = write_reminders(verified)
    entity_name_to_id = {e.name: e.id for e in graph.entities}
    judged_lines = judge_reminders(written.get("lines", []))
    reminders = [
        {
            "text": line.get("text", ""),
            "entity_ids": [
                entity_name_to_id[n]
                for n in line.get("entity_names", [])
                if n in entity_name_to_id
            ],
        }
        for line in judged_lines
        if line.get("text")
    ]

    return {
        "boundary": chunk_boundary,
        "graph": graph.model_dump(),
        "reminders": reminders,
    }, rename_map


def build_entries(boundary_results: list[tuple[int, dict]], book_id: str | None = None) -> list[dict]:
    """(chunk_boundary, accumulated_build_result) 시퀀스 → 계약 entries.

    boundary_results 는 chunk 경계선 오름차순. build_result 는 해당 chunk 경계선까지
    '누적된' characters/relations/events (incremental_build_agent 반환 형태).
    중간 체크포인팅이 필요하면(예: 대량 EPUB) 이 함수 대신 `precompute_from_epub`처럼
    `_build_single_entry`를 직접 루프에서 호출하는 쪽을 쓴다.
    """
    ordered = sorted(boundary_results, key=lambda x: x[0])
    first_seen: dict[str, int] = {}
    canonical_registry: list[dict] = []
    global_name_map: dict[str, str] = {}
    prev_raw_names: set[str] = set()

    entries: list[dict] = []
    for chunk_boundary, result in ordered:
        entry, rename_map = _build_single_entry(
            chunk_boundary,
            result,
            first_seen,
            book_id,
            canonical_registry,
            global_name_map,
            prev_raw_names,
        )
        entries.append(entry)
        if rename_map:
            entries[:] = _apply_consolidation_to_entries(entries, rename_map, set())
    return entries


def build_chunk_boundary_to_global_index_map(book_id: str, epub_path: str | Path) -> dict[int, int]:
    """내부 분석용 chunk boundary를 CFI global_index로 바꾸는 매핑을 만든다.

    BuildAgent의 chunk_tool은 epub_parser 기준 문자 단위로 청크를 만드는데, 실제
    스포일러 게이팅은 book_cfi_index 기준 global_index로 이뤄지므로 두 단위를 반드시
    맞춰줘야 한다 (안 맞으면 책의 일부만 읽었는데 전체 스포일러가 노출되는 버그가 남).
    """
    from . import cfi_db
    from .config import PARSER_CHAPTER_OFFSET
    from agents.parsers.epub_parser import parse_epub
    from agents.tools.chunk_tool import make_chunks

    parsed = parse_epub(epub_path)
    chapters = parsed["chapters"]
    chunks = make_chunks(chapters)
    chapter_charcount = {c["chapter_index"]: c["char_count"] for c in chapters}

    cfi_db.clear_cache()
    paragraphs = cfi_db.get_paragraphs(book_id)
    if not paragraphs:
        return {int(chunk["offset"]): int(chunk["offset"]) for chunk in chunks}

    by_cfi_chapter: dict[int, list] = {}
    for p in paragraphs:
        by_cfi_chapter.setdefault(p.chapter_index, []).append(p)
    cfi_chapter_range = {
        idx: (ps[0].global_index, ps[-1].global_index) for idx, ps in by_cfi_chapter.items()
    }

    # 첫 챕터 제목으로 이 책의 실제 파서 오프셋을 자동 계산한다(책마다 표지·목차 문서
    # 개수가 다름). book_cfi_index의 chapter_index가 항상 1부터 시작한다는 보장이
    # 없다(예: 0부터 시작하는 책도 있음) — "idx == 1"로 고정하면 그런 책은 첫 챕터를
    # 영영 못 찾아서 이 계산 전체가 조용히 실패한다. 실제로 존재하는 가장 작은
    # chapter_index를 첫 챕터로 삼는다.
    first_cfi_chapter_index = min(by_cfi_chapter.keys()) if by_cfi_chapter else None
    ch1_title = (
        by_cfi_chapter[first_cfi_chapter_index][0].chapter_title
        if first_cfi_chapter_index is not None
        else None
    )

    def normalize(t: str) -> str:
        # 예전엔 [^a-z0-9]+로 영문/숫자만 남겼는데, 그러면 한글(또는 다른 비ASCII
        # 문자) 제목은 전부 빈 문자열이 돼서 아래 "target and ..." 조건이 항상
        # False가 되어 이 자동 보정이 조용히 실패하고, 책마다 다른 챕터 오프셋을
        # 무조건 PARSER_CHAPTER_OFFSET(다른 책 기준값)으로 잘못 고정해버렸다.
        # \\w는 파이썬 re 기본 설정에서 유니코드 문자(한글 포함)도 단어 문자로
        # 인식하므로, 어떤 언어의 제목이든 정규화가 실제로 동작한다.
        return re.sub(r"[^\w]+", "", t.lower())

    computed_offset = PARSER_CHAPTER_OFFSET
    if ch1_title and first_cfi_chapter_index is not None:
        target = normalize(ch1_title)
        for c in chapters:
            if target and target in normalize(c["title"]):
                computed_offset = c["chapter_index"] - first_cfi_chapter_index
                break

    def chunk_to_global_index(chunk: dict) -> int:
        cfi_chapter_index = max(0, chunk["chapter_index"] - computed_offset)
        if cfi_chapter_index not in cfi_chapter_range:
            cfi_chapter_index = max(cfi_chapter_range.keys())
        start, end = cfi_chapter_range[cfi_chapter_index]
        total_chars = chapter_charcount.get(chunk["chapter_index"], 1) or 1
        frac = min(1.0, chunk["end_char"] / total_chars)
        return round(start + frac * (end - start))

    return {int(chunk["offset"]): chunk_to_global_index(chunk) for chunk in chunks}


def _remap_position_value_to_global_index(
    value: object,
    chunk_boundary_to_global_index: dict[int, int],
) -> object:
    if isinstance(value, bool) or not isinstance(value, int):
        return value
    return chunk_boundary_to_global_index.get(value, value)


def _remap_graph_positions_to_global_index(
    value: object,
    chunk_boundary_to_global_index: dict[int, int],
) -> object:
    """graph 내부의 offset/boundary/revision_offset 값을 global_index로 변환한다."""
    if isinstance(value, list):
        return [
            _remap_graph_positions_to_global_index(item, chunk_boundary_to_global_index)
            for item in value
        ]
    if isinstance(value, dict):
        remapped: dict = {}
        for key, item in value.items():
            if key in _GRAPH_POSITION_FIELDS:
                remapped[key] = _remap_position_value_to_global_index(
                    item,
                    chunk_boundary_to_global_index,
                )
            else:
                remapped[key] = _remap_graph_positions_to_global_index(
                    item,
                    chunk_boundary_to_global_index,
                )
        return remapped
    return value


def remap_entries_to_global_index(
    book_id: str, epub_path: str | Path, entries: list[dict]
) -> list[dict]:
    """entry boundary와 graph 내부 위치 필드를 모두 CFI global_index로 재매핑한다."""
    chunk_boundary_to_global_index = build_chunk_boundary_to_global_index_map(book_id, epub_path)

    remapped = []
    for entry in entries:
        chunk_boundary = int(entry["boundary"])
        boundary_global_index = chunk_boundary_to_global_index.get(chunk_boundary, chunk_boundary)
        graph = _remap_graph_positions_to_global_index(
            entry.get("graph", {}),
            chunk_boundary_to_global_index,
        )
        for event in graph.get("events", []):
            if "first_seen_chunk_offset" in event:
                event["first_seen_global_index"] = _remap_position_value_to_global_index(
                    event.get("first_seen_chunk_offset"),
                    chunk_boundary_to_global_index,
                )
            if "last_seen_chunk_offset" in event:
                event["last_seen_global_index"] = _remap_position_value_to_global_index(
                    event.get("last_seen_chunk_offset"),
                    chunk_boundary_to_global_index,
                )
        graph = {**graph, "offset": boundary_global_index}
        if "boundary" in graph:
            graph["boundary"] = boundary_global_index
        remapped.append({**entry, "boundary": boundary_global_index, "graph": graph})

    # 서로 다른 chunk 경계선이 같은 global_index로 매핑될 수 있다 — 예를 들어 두 chunk
    # 경계 사이에 새 문단이 없으면(짧은 챕터, 챕터 경계 근처 등) 둘 다 가장 가까운 같은
    # 문단으로 반올림된다. 이 상태로 그대로 Supabase에 upsert하면 "같은 배치 안에서
    # 같은 행을 두 번 갱신하려 한다"는 CardinalityViolation 에러가 난다(book_id+boundary
    # 유니크 제약). 같은 global_index면 더 나중에(더 누적된 정보를 담은) 항목만 남긴다.
    deduped: dict[int, dict] = {}
    for item in remapped:
        deduped[item["boundary"]] = item
    remapped = list(deduped.values())

    remapped.sort(key=lambda e: e["boundary"])
    return remapped


def remap_boundaries_to_global_index(
    book_id: str, epub_path: str | Path, entries: list[dict]
) -> list[dict]:
    """하위 호환용 wrapper. 새 코드에서는 `remap_entries_to_global_index`를 사용한다."""
    return remap_entries_to_global_index(book_id, epub_path, entries)


def delete_snapshots_from_supabase(book_id: str) -> int:
    """book_id의 기존 스냅샷 행을 전부 삭제. 재분석 시작 전에 한 번 호출한다.

    upload_snapshots_to_supabase는 (book_id, boundary) upsert라, boundary 스케줄이
    바뀌면(예: 청크 오프셋 재보정 후 재분석) 예전 스케줄의 boundary들은 새 entries에
    안 나타나서 절대 지워지지 않고 계속 쌓인다 — floor 선택 로직이 이 스테일 스냅샷을
    골라버리면 재분석 이전의 잘못된 그래프가 다시 노출된다. 실제로 이 문제로 재분석
    직후에도 옛 boundary(16/52/88/124/160/217)가 새 boundary와 섞여서 표시된 사고가 있었다.
    """
    import psycopg2

    from .config import SUPABASE_DB_URL

    if not SUPABASE_DB_URL:
        return 0

    conn = psycopg2.connect(SUPABASE_DB_URL, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM build_agent_snapshots WHERE book_id = %s", (book_id,))
            deleted = cur.rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()


def upload_snapshots_to_supabase(book_id: str, entries: list[dict]) -> int:
    """entries를 Supabase build_agent_snapshots 테이블에 적재. 적재 행 수 반환."""
    import json as _json

    import psycopg2
    import psycopg2.extras

    from .config import SUPABASE_DB_URL

    if not SUPABASE_DB_URL or not entries:
        return 0

    conn = psycopg2.connect(SUPABASE_DB_URL, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            rows = [
                (
                    book_id,
                    e["boundary"],
                    _json.dumps(e["graph"], ensure_ascii=False),
                    _json.dumps(e["reminders"], ensure_ascii=False),
                )
                for e in entries
            ]
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO build_agent_snapshots (book_id, boundary, graph, reminders)
                VALUES %s
                ON CONFLICT (book_id, boundary)
                DO UPDATE SET graph = EXCLUDED.graph, reminders = EXCLUDED.reminders
                """,
                rows,
                template="(%s, %s, %s::jsonb, %s::jsonb)",
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def write_store(book_id: str, entries: list[dict], store_dir: Path = STORE_DIR) -> Path:
    """계약 JSON 을 `<store_dir>/<book_id>.json` 으로 저장하고 경로를 반환."""
    store_dir.mkdir(parents=True, exist_ok=True)
    path = store_dir / f"{book_id}.json"
    payload = {"book_id": book_id, "entries": entries}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def store_path(book_id: str, store_dir: Path = STORE_DIR) -> Path:
    return store_dir / f"{book_id}.json"


def _apply_consolidation_to_entries(
    entries: list[dict], merge_map: dict[str, str], remove_names: set[str]
) -> list[dict]:
    """ConsolidationAgent가 뒤늦게 찾아낸 병합/제거를 이미 체크포인팅된 과거 entries에도
    소급 적용한다. LLM을 다시 부르지 않고 이미 만들어진 graph(entities/relationships)와
    reminders를 id 기준으로 직접 고쳐 쓰는 순수 데이터 변환이라 비용이 들지 않는다.
    """
    if not merge_map and not remove_names:
        return entries

    id_to_canonical_id: dict[str, str] = {
        ad.entity_id(alias): ad.entity_id(canon) for alias, canon in merge_map.items()
    }
    removed_ids = {ad.entity_id(name) for name in remove_names}

    patched: list[dict] = []
    for entry in entries:
        graph = entry["graph"]

        kept_entities: dict[str, dict] = {}
        for e in graph.get("entities", []):
            eid = e["id"]
            if eid in removed_ids:
                continue
            new_id = id_to_canonical_id.get(eid, eid)
            new_name = merge_map.get(e["name"], e["name"])
            if new_id not in kept_entities:
                kept_entities[new_id] = {**e, "id": new_id, "name": new_name}

        kept_relationships: dict[str, dict] = {}
        for r in graph.get("relationships", []):
            src = id_to_canonical_id.get(r["source"], r["source"])
            tgt = id_to_canonical_id.get(r["target"], r["target"])
            if src in removed_ids or tgt in removed_ids:
                continue
            if src not in kept_entities or tgt not in kept_entities:
                continue
            rid = ad._relation_id(src, tgt, r.get("label", ""))
            if rid not in kept_relationships:
                kept_relationships[rid] = {**r, "id": rid, "source": src, "target": tgt}

        new_graph = {
            **graph,
            "entities": list(kept_entities.values()),
            "relationships": list(kept_relationships.values()),
        }

        new_reminders = []
        for line in entry.get("reminders", []):
            remapped_ids = []
            for eid in line.get("entity_ids", []):
                new_id = id_to_canonical_id.get(eid, eid)
                if new_id in removed_ids or new_id not in kept_entities:
                    continue
                if new_id not in remapped_ids:
                    remapped_ids.append(new_id)
            new_reminders.append({**line, "entity_ids": remapped_ids})

        patched.append({**entry, "graph": new_graph, "reminders": new_reminders})

    return patched


# 몇 스냅샷마다 ConsolidationAgent로 canonical_registry 전체를 재점검할지.
# canonicalize_new_characters는 "새 인물 vs 최근/유사 후보"만 좁게 비교해서 저렴하지만
# 그만큼 사각지대(전혀 다른 음역 변형, 뒤늦게 놓친 비인물 항목)가 생긴다 — 그 사각지대를
# 메우려고 몇 스냅샷마다 한 번씩만 전체를 훑는 무거운 패스를 추가로 돌린다.
CONSOLIDATION_INTERVAL = 5


def precompute_from_epub(
    epub_path: str | Path,
    book_id: str,
    boundaries: list[int],
    store_dir: Path = STORE_DIR,
    upload_to_supabase: bool = True,
    on_progress: Callable[[int, int], None] | None = None,
) -> Path:
    """EPUB → chunk → 경계선별 incremental build → 계약 JSON 저장 + Supabase 적재.

    UPSTAGE_API_KEY 가 필요하다 (실제 LLM 호출). boundaries 는 청크 offset(정수) 리스트.
    agents 패키지는 지연 import — 어댑터/서빙 경로가 langchain 에 의존하지 않게 하기 위함.

    경계선 하나가 끝날 때마다 즉시 로컬 파일/Supabase에 체크포인팅한다. 책 한 권
    분석은 LLM 호출이 수백 번에 달해 중간에 rate limit/타임아웃으로 실패할 수 있는데,
    체크포인팅해두면 여기까지 처리한 경계선은 이미 반영되어 있어 재시도 비용이 줄어든다.

    on_progress(완료된 경계선 수, 전체 경계선 수)는 경계선 하나가 끝날 때마다 호출된다
    (선택). 업로드 API가 진행률을 보여줄 때 쓴다 — 없어도 동작에는 영향 없다.
    """
    from agents.build_agent import incremental_build_agent  # 지연 import
    from agents.consolidation_agent import consolidate_registry
    from agents.parsers.epub_parser import parse_epub
    from agents.tools.chunk_tool import make_chunks

    parsed = parse_epub(epub_path)
    chunks = make_chunks(parsed["chapters"])

    if upload_to_supabase:
        # 새 스케줄로 재분석을 시작하기 전에 이 책의 예전 스냅샷을 전부 지운다 —
        # 그러지 않으면 예전 boundary 스케줄의 스테일 데이터가 새 데이터와 섞인다.
        delete_snapshots_from_supabase(book_id)

    # 이번 실행 전체에 걸쳐 동일한 시각을 쓴다 — 프론트에서 "이 책 데이터가 언제
    # 마지막으로 갱신됐는지"를 볼 때, 경계선마다 시각이 제각각이면 오히려 혼란스럽다.
    run_started_at = datetime.now(timezone.utc).isoformat()

    entries: list[dict] = []
    first_seen: dict[str, int] = {}
    previous: dict = {"characters": [], "relations": [], "events": []}
    last_built_chunk_boundary = -1

    # 인물 이름 병합 상태 — 경계선을 넘어 계속 누적/재사용한다.
    canonical_registry: list[dict] = []
    global_name_map: dict[str, str] = {}
    prev_raw_names: set[str] = set()
    last_consolidated_at = 0

    def _run_consolidation() -> None:
        nonlocal last_consolidated_at
        consolidation = consolidate_registry(canonical_registry)
        merge_map = consolidation["merge_map"]
        remove_names = consolidation["remove_names"]
        last_consolidated_at = len(entries)

        if not merge_map and not remove_names:
            return

        canonical_registry[:] = [
            c
            for c in canonical_registry
            if c.get("name", "") not in merge_map and c.get("name", "") not in remove_names
        ]

        # 이후 새로 등장하는 원본 이름들이 최종 대표 이름으로 이어지도록 체이닝.
        for raw_name, mapped_name in list(global_name_map.items()):
            if mapped_name in merge_map:
                global_name_map[raw_name] = merge_map[mapped_name]
        global_name_map.update(merge_map)

        entries[:] = _apply_consolidation_to_entries(entries, merge_map, remove_names)

    for chunk_boundary in sorted(boundaries):
        result = incremental_build_agent(
            chunks=chunks,
            current_offset=chunk_boundary,
            last_built_offset=last_built_chunk_boundary,
            previous_results=previous,
        )
        previous = result
        last_built_chunk_boundary = chunk_boundary

        entry, rename_map = _build_single_entry(
            chunk_boundary,
            result,
            first_seen,
            book_id,
            canonical_registry,
            global_name_map,
            prev_raw_names,
        )
        entries.append(entry)
        if rename_map:
            entries[:] = _apply_consolidation_to_entries(entries, rename_map, set())

        # 주기적 전체 정리: canonical_registry가 자란 만큼 사각지대도 커지므로,
        # 몇 스냅샷마다 한 번씩 전체를 다시 훑어서 놓친 병합/비인물 항목을 잡는다.
        if len(entries) - last_consolidated_at >= CONSOLIDATION_INTERVAL:
            _run_consolidation()

        # 경계선 하나 끝날 때마다 즉시 저장(체크포인팅). 중간에 rate limit(429) 등으로
        # 실패해도 여기까지 처리한 경계선은 Supabase/로컬 파일에 이미 반영되어 있다.
        remapped_so_far = remap_entries_to_global_index(book_id, epub_path, entries)
        for entry in remapped_so_far:
            entry["graph"]["generated_at"] = run_started_at
        write_store(book_id, remapped_so_far, store_dir)
        if upload_to_supabase:
            upload_snapshots_to_supabase(book_id, remapped_so_far)

        if on_progress:
            on_progress(len(entries), len(boundaries))

    # 짧은 책은 CONSOLIDATION_INTERVAL 배수를 한 번도 못 채우고 끝날 수 있어(예: 전체
    # 스냅샷이 4개뿐), 마지막에 정리가 한 번도 안 도는 경우가 실제로 있었다. 남은
    # entries가 있으면 반드시 최소 한 번은 마지막에 전체 정리를 돌린다.
    if entries and last_consolidated_at != len(entries):
        _run_consolidation()
        remapped_so_far = remap_entries_to_global_index(book_id, epub_path, entries)
        for entry in remapped_so_far:
            entry["graph"]["generated_at"] = run_started_at
        write_store(book_id, remapped_so_far, store_dir)
        if upload_to_supabase:
            upload_snapshots_to_supabase(book_id, remapped_so_far)

    return store_path(book_id, store_dir)


if __name__ == "__main__":  # pragma: no cover
    import argparse

    p = argparse.ArgumentParser(description="SpoKeeper precompute (EPUB → 계약 JSON)")
    p.add_argument("epub", help="EPUB 경로")
    p.add_argument("book_id", help="책 id (예: b_mist)")
    p.add_argument("boundaries", help="쉼표구분 경계선 offset (예: 5,10,20)")
    args = p.parse_args()
    out = precompute_from_epub(
        args.epub, args.book_id, [int(x) for x in args.boundaries.split(",") if x.strip()]
    )
    print(f"wrote {out}")
