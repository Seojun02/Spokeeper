"""B1 계약/게이팅 테스트. 스포일러 0 불변식 스팟체크 포함."""
import os
import tempfile

os.environ["SPO_DB"] = f"sqlite:///{tempfile.gettempdir()}/spokeeper_test.db"

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import db  # noqa: E402
from backend.app.main import app  # noqa: E402

db.init_db()  # 테스트에선 lifespan이 자동 실행되지 않으므로 명시적으로 초기화
client = TestClient(app)


def test_book_meta():
    r = client.get("/api/books/b_mist")
    assert r.status_code == 200
    body = r.json()
    assert body["total_offset"] == 430
    assert len(body["chapters"]) == 3


def test_chapter_content():
    r = client.get("/api/books/b_mist/chapters/3")
    assert r.status_code == 200
    assert "윤 팀장" in r.json()["content"]


def test_graph_empty_before_c1():
    # offset 150 → 읽은 청크 없음 → 빈 그래프
    r = client.get("/api/books/b_mist/graph", params={"offset": 150})
    body = r.json()
    assert body["entities"] == []
    assert body["relationships"] == []


def test_graph_partial_c1():
    # offset 215 → c1 → 개체3·관계2
    body = client.get("/api/books/b_mist/graph", params={"offset": 215}).json()
    assert len(body["entities"]) == 3
    assert len(body["relationships"]) == 2


def test_graph_full_c3_matches_screenshot():
    # offset 380 → c1+c2+c3 → 개체5·관계5 (r4a·r4b 포함)
    body = client.get("/api/books/b_mist/graph", params={"offset": 380}).json()
    assert len(body["entities"]) == 5
    assert len(body["relationships"]) == 5
    ids = {r["id"] for r in body["relationships"]}
    assert {"r1", "r2", "r3", "r4a", "r4b"} == ids


def test_strict_chunk_end_no_leak():
    # 스포일러 0: 청크를 끝까지 읽기 전에는 그 청크 fact 미공개
    # offset 379 (c3 끝 380 직전) → 윤 팀장(e_yoon) 노출 금지
    body = client.get("/api/books/b_mist/graph", params={"offset": 379}).json()
    names = {e["id"] for e in body["entities"]}
    assert "e_yoon" not in names
    # offset 319 (c2 끝 320 직전) → 강 국장(e_kang) 노출 금지
    body2 = client.get("/api/books/b_mist/graph", params={"offset": 319}).json()
    assert "e_kang" not in {e["id"] for e in body2["entities"]}


def test_progress_monotonic_boundary():
    # boundary = max(기존, 신규) 단조 증가
    client.put("/api/books/b_mist/progress", json={"reading_offset": 300, "user_id": "t1"})
    client.put("/api/books/b_mist/progress", json={"reading_offset": 120, "user_id": "t1"})
    body = client.get("/api/books/b_mist/progress", params={"user_id": "t1"}).json()
    assert body["reading_offset"] == 120
    assert body["spoiler_boundary"] == 300  # 뒤로 가도 경계선은 유지


def test_reminders_gated():
    body = client.get("/api/books/b_mist/reminders", params={"offset": 380}).json()
    assert len(body["lines"]) == 3
    empty = client.get("/api/books/b_mist/reminders", params={"offset": 150}).json()
    assert empty["lines"] == []
