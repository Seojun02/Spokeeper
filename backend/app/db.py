"""progress 영속 (SQLite + SQLAlchemy 2.x). boundary = max(기존, 신규) 단조 증가."""
from __future__ import annotations

import os

from sqlalchemy import Integer, String, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DB_PATH = os.environ.get("SPO_DB", "sqlite:///./spokeeper.db")
engine = create_engine(DB_PATH, connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class ProgressRow(Base):
    __tablename__ = "progress"
    # (user_id, book_id) 복합 키
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    book_id: Mapped[str] = mapped_column(String, primary_key=True)
    reading_offset: Mapped[int] = mapped_column(Integer, default=0)
    spoiler_boundary: Mapped[int] = mapped_column(Integer, default=0)
    reading_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spoiler_boundary_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_cfi: Mapped[str | None] = mapped_column(String, nullable=True)


def init_db() -> None:
    Base.metadata.create_all(engine)
    # create_all은 기존 테이블에 컬럼을 추가하지 않으므로 설치된 DB도 additive하게 올린다.
    existing = {column["name"] for column in inspect(engine).get_columns("progress")}
    additions = {
        "reading_page": "INTEGER",
        "total_pages": "INTEGER",
        "spoiler_boundary_page": "INTEGER",
        "current_cfi": "TEXT",
    }
    with engine.begin() as connection:
        for name, sql_type in additions.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE progress ADD COLUMN {name} {sql_type}"))


def get_progress(user_id: str, book_id: str) -> ProgressRow:
    with Session(engine) as s:
        row = s.get(ProgressRow, (user_id, book_id))
        if row is None:
            row = ProgressRow(user_id=user_id, book_id=book_id, reading_offset=0, spoiler_boundary=0)
            s.add(row)
            s.commit()
            s.refresh(row)
        return row


def put_progress(
    user_id: str,
    book_id: str,
    reading_offset: int,
    force: bool = False,
    reading_page: int | None = None,
    total_pages: int | None = None,
    current_cfi: str | None = None,
) -> ProgressRow:
    with Session(engine) as s:
        row = s.get(ProgressRow, (user_id, book_id))
        if row is None:
            row = ProgressRow(user_id=user_id, book_id=book_id,
                              reading_offset=0, spoiler_boundary=0)
            s.add(row)
        prev_boundary = row.spoiler_boundary or 0
        row.reading_offset = reading_offset
        if reading_page is not None:
            row.reading_page = reading_page
        if total_pages is not None:
            row.total_pages = total_pages
        if current_cfi is not None:
            row.current_cfi = current_cfi
        if force:
            # 재독 모드: 단조 증가 규칙을 의도적으로 깨고 현재 위치로 경계선을 되돌린다.
            row.spoiler_boundary = reading_offset
            row.spoiler_boundary_page = reading_page
        else:
            # 단조 증가 (SPEC progress 규칙 / 불변 규칙 5)
            row.spoiler_boundary = max(prev_boundary, reading_offset)
            # 같은 CFI에서 화면 크기/폰트만 바뀐 경우에도 boundary page를 새 layout에 맞춘다.
            if reading_page is not None and reading_offset >= prev_boundary:
                row.spoiler_boundary_page = reading_page
        s.commit()
        s.refresh(row)
        return row


def seed_demo_progress(user_id: str = "local", book_id: str = "b_mist", offset: int = 380) -> None:
    """데모 기본값: reading_offset=380 (스크린샷과 일치)."""
    with Session(engine) as s:
        row = s.get(ProgressRow, (user_id, book_id))
        if row is None:
            s.add(ProgressRow(user_id=user_id, book_id=book_id,
                              reading_offset=offset, spoiler_boundary=offset))
            s.commit()
