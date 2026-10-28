"""데모 시드 데이터.

Book/Chapter 메타데이터(제목·offset)는 Supabase `book_cfi_index`(cfi_db)를 소스로 삼는다 —
offset은 곧 cfi_path 정렬 기준 global_index다. 화면에 보여줄 본문 텍스트는 아직
book_cfi_index에 전체 텍스트가 없어 agents.parsers.epub_parser로 EPUB에서 직접 읽는다
(문단 단위 정확도는 CFI와 100% 일치하지 않을 수 있음 — 알려진 한계).

graph_json/reminders 픽스처(GRAPH_C1 등)는 아직 예전 데모 소설("안개 궤도") 데이터로,
셜록 홈즈용 BuildAgent 결과가 준비되면 교체될 예정이다.
"""
from __future__ import annotations

import re
from functools import lru_cache

from . import cfi_db
from .book_repository import resolve_epub_path
from .config import DEFAULT_BOOK_ID, PARSER_CHAPTER_OFFSET
from .schemas import (
    Book,
    Chapter,
    Entity,
    GraphJson,
    ReminderLine,
    Reminders,
    Relationship,
)

BOOK_ID = DEFAULT_BOOK_ID


def _epub_path_for(book_id: str) -> str:
    """구버전 호출부 호환용 wrapper. 경로 해석은 공통 repository에 위임한다."""
    return str(resolve_epub_path(book_id))


# maxsize=8이었을 때는 등록된 책이 8권을 넘는 순간(업로드가 쌓이면서 자연히 넘김)
# 매 요청마다 LRU 캐시가 밀려나면서(스래싱) 사실상 캐시가 하나도 안 먹혀 API가
# 몇 초씩 걸리는 문제가 있었다 — 책 수가 작고 자연스럽게 유계(bounded)라 무제한으로 둔다.
@lru_cache(maxsize=None)
def _parsed_chapters(book_id: str) -> list[dict]:
    from agents.parsers.epub_parser import parse_epub

    return parse_epub(resolve_epub_path(book_id))["chapters"]


def _normalize_title(title: str) -> str:
    # [^a-z0-9]+로 영문/숫자만 남기면 한글(또는 다른 비ASCII) 제목은 전부 빈 문자열이
    # 돼서, 이 값을 쓰는 매칭이 항상 실패한다(precompute.py의 같은 버그 참고). \w는
    # 파이썬 re 기본 설정에서 유니코드 문자(한글 포함)도 단어 문자로 인식한다.
    return re.sub(r"[^\w]+", "", title.lower())


@lru_cache(maxsize=None)
def _parser_chapter_offset(book_id: str, first_cfi_title: str) -> int:
    """cfi_db의 chapter_index=1 제목을 epub_parser 결과에서 찾아 두 인덱싱 체계의
    오프셋을 자동으로 맞춘다 (책마다 표지·목차 문서 개수가 달라서 고정값을 쓰면 안 됨).
    실패 시 셜록 홈즈에서 실측한 기본값으로 폴백한다."""
    target = _normalize_title(first_cfi_title)
    for c in _parsed_chapters(book_id):
        if target and target in _normalize_title(c["title"]):
            return c["chapter_index"] - 1
    return PARSER_CHAPTER_OFFSET


def _chapter_text(book_id: str, cfi_chapter_index: int, cfi_chapter_title: str) -> str | None:
    offset = _parser_chapter_offset(book_id, cfi_chapter_title) if cfi_chapter_index >= 1 else 0
    parser_index = cfi_chapter_index + offset
    for c in _parsed_chapters(book_id):
        if c["chapter_index"] == parser_index:
            return c["text"]
    return None


@lru_cache(maxsize=None)
def book_for(book_id: str, title: str = "", author: str = "—") -> Book:
    paragraphs = cfi_db.get_paragraphs(book_id)

    by_chapter: dict[int, list[cfi_db.CfiParagraph]] = {}
    for p in paragraphs:
        by_chapter.setdefault(p.chapter_index, []).append(p)

    chapters = [
        Chapter(
            id=f"ch{idx}",
            index=idx,
            title=ps[0].chapter_title,
            start_offset=ps[0].global_index,
            end_offset=ps[-1].global_index,
        )
        for idx, ps in sorted(by_chapter.items())
    ]

    total_offset = paragraphs[-1].global_index if paragraphs else 0

    return Book(
        id=book_id,
        title=title or book_id,
        author=author,
        total_offset=total_offset,
        parts=[],
        chapters=chapters,
    )


def chapter_with_content(book_id: str, index: int) -> Chapter:
    book = book_for(book_id)
    base = next(c for c in book.chapters if c.index == index)
    # 오프셋은 항상 1챕터 제목을 기준으로 계산해야 한다 — 요청한 챕터 자신의 제목을
    # 넘기면 챕터마다 다른(그리고 틀린) 오프셋이 나와 엉뚱한 챕터 본문이 매칭된다.
    anchor = next((c for c in book.chapters if c.index == 1), base)
    text = _chapter_text(book_id, index, anchor.title)
    return base.model_copy(update={"content": text})


# ── 기존 단일 책(셜록 홈즈) 코드와의 호환용 별칭 ──────────────────────────
BOOK_MIST = book_for(BOOK_ID, title="The Hound of the Baskervilles", author="Arthur Conan Doyle")
_BOOK_MIST_ANCHOR_TITLE = next((c.title for c in BOOK_MIST.chapters if c.index == 1), "")
CHAPTER_CONTENT: dict[int, str] = {
    c.index: text
    for c in BOOK_MIST.chapters
    if (text := _chapter_text(BOOK_ID, c.index, _BOOK_MIST_ANCHOR_TITLE)) is not None
}


# ── graph/reminders 픽스처 (교체 대기 중 — 아직 이전 데모 소설 데이터) ──────────
_E_MINU = Entity(id="e_minu", name="민우", type="person", color="blue")
_E_SEOHYUN = Entity(id="e_seohyun", name="서현", type="person", color="blue")
_E_ATLAS = Entity(id="e_atlas", name="아틀라스 호", type="ship", color="blue")
_E_KANG = Entity(id="e_kang", name="강 국장", type="person", color="dark")
_E_YOON = Entity(id="e_yoon", name="윤 팀장", type="person", color="dark")

_R1 = Relationship(id="r1", source="e_minu", target="e_seohyun", label="동료 연구원", tone="ally",
                   description="통제실에서 함께 아틀라스 호 신호를 확인함.", revision_offset=40)
_R2 = Relationship(id="r2", source="e_minu", target="e_atlas", label="신호 추적", tone="neutral",
                   description="민우가 실종 탐사선의 고유 신호를 포착함.", revision_offset=120)
_R3 = Relationship(id="r3", source="e_seohyun", target="e_kang", label="은폐 의혹", tone="tense",
                   description="서현이 신호 속 강 국장의 보안 서명을 확인함.", revision_offset=260)
_R4A = Relationship(id="r4a", source="e_yoon", target="e_minu", label="압박 조사", tone="tense",
                    description="윤 팀장이 무장 요원들과 통제실에 진입함.", revision_offset=370)
_R4B = Relationship(id="r4b", source="e_yoon", target="e_seohyun", label="압박 조사", tone="tense",
                    description="윤 팀장이 무장 요원들과 통제실에 진입함.", revision_offset=370)

GRAPH_C1 = GraphJson(offset=215, spoiler_safe=True,
                     entities=[_E_MINU, _E_SEOHYUN, _E_ATLAS],
                     relationships=[_R1, _R2])
GRAPH_C2 = GraphJson(offset=320, spoiler_safe=True,
                     entities=[_E_MINU, _E_SEOHYUN, _E_ATLAS, _E_KANG],
                     relationships=[_R1, _R2, _R3])
GRAPH_C3 = GraphJson(offset=380, spoiler_safe=True,
                     entities=[_E_MINU, _E_SEOHYUN, _E_ATLAS, _E_KANG, _E_YOON],
                     relationships=[_R1, _R2, _R3, _R4A, _R4B])
GRAPH_EMPTY = GraphJson(offset=0, spoiler_safe=True, entities=[], relationships=[])

_RL_R1 = ReminderLine(text="민우와 서현은 통제실에서 아틀라스 호의 신호를 함께 확인했다.",
                      entity_ids=["e_minu", "e_seohyun"])
_RL_R2 = ReminderLine(text="민우가 실종 탐사선 아틀라스 호의 고유 신호를 포착했다.",
                      entity_ids=["e_minu", "e_atlas"])
_RL_R3 = ReminderLine(text="서현은 신호 속에서 강 국장의 보안 서명을 발견해 은폐 의혹을 품었다.",
                      entity_ids=["e_seohyun", "e_kang"])
_RL_R4 = ReminderLine(text="강 국장의 집행관 윤 팀장이 무장 요원들과 통제실에 진입해 압박을 시작했다.",
                      entity_ids=["e_yoon", "e_minu", "e_seohyun"])

REMINDERS_C1 = [_RL_R1, _RL_R2]
REMINDERS_C2 = [_RL_R1, _RL_R3]
REMINDERS_C3 = [_RL_R1, _RL_R3, _RL_R4]
