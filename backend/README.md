# SpoKeeper — Serving Backend (FastAPI)

FE 계약(`graph_json`·`reminders`)을 그대로 서빙. 스포일러 게이팅(strict_chunk_end)은
**서버에서** 수행한다 — 경계선 뒤 데이터는 클라이언트로 보내지 않는다 (불변 규칙 2·6).

## 실행 (모든 명령은 **저장소 최상위**에서)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
pytest backend/tests -q
```
> 프론트(`frontend/`)는 `/api` 를 `127.0.0.1:8000` 으로 프록시한다(vite.config.ts).
> `localhost` 는 IPv6(::1)로 먼저 풀려 다른 리스너(Docker 등)와 충돌할 수 있으므로 IPv4 고정.

## 엔드포인트 (SPEC §3)
| 메서드 · 경로 | 설명 |
|---|---|
| `GET /api/books` · `/{id}` | 목록 / 메타·챕터 인덱스 |
| `GET /api/books/{id}/chapters/{index}` | 챕터 본문 |
| `GET /api/books/{id}/graph?offset=&reveal_all=` | 계약 graph_json |
| `GET /api/books/{id}/reminders?offset=&entity_id=` | 계약 reminders |
| `GET·PUT /api/books/{id}/progress` | 진행 조회/갱신 (boundary 단조증가) |

## 소스 추상화 (교체 지점)
`ContentSource` 인터페이스 뒤에 두 구현. `main.py._make_source()` 가 `SPO_SOURCE` 로 선택:
- **`FixtureSource`** (기본, `SPO_SOURCE` 미설정) — 정적 시드 픽스처 + strict_chunk_end 게이팅.
- **`AgentResultSource`** (`SPO_SOURCE=agent`) — 에이전트 precompute 결과(`backend/data/precomputed/<book>.json`)
  조회. 계약이 동일하므로 라우트/스키마 변경 없이 소스만 교체된다.

```bash
SPO_SOURCE=agent uvicorn backend.app.main:app --port 8000   # 실데이터 서빙
```

## 에이전트 연동 (다음 담당자 진입점)
BuildAgent 출력(`characters/relations/events`, 이름 기반)을 계약(`entities/relationships`,
id 기반)으로 바꾸는 어댑터가 준비돼 있다:
- `app/agent_adapter.py` — 순수 변환 함수 (LLM 의존 없음). 이름→안정 id, tone 휴리스틱,
  `revision_offset`(최초 등장 경계선) 처리.
- `app/precompute.py` — 경계선별 build 결과 → 계약 JSON store 생성/저장.
  - `precompute_from_epub(epub, book_id, boundaries)` — EPUB 에서 바로 (UPSTAGE_API_KEY 필요).
  - `build_entries(...)` / `write_store(...)` — 이미 계산된 결과로부터.
- `scripts/make_demo_store.py` — API 키 없이 도는 **살아있는 예제** (b_mist 데모 store 생성).
  담당자는 이 dict 를 실제 `incremental_build_agent` 출력으로 바꾸면 된다.

```bash
python -m backend.scripts.make_demo_store          # 데모 store 생성
python -m backend.app.precompute <epub> b_mist 5,10,20   # 실제 EPUB precompute
```

## 게이팅 경계 (청크 끝 = 공개 지점)
`FixtureSource`: `c1<215? empty · ≥215 c1 · ≥320 c2 · ≥380 c3`. 청크를 **끝까지** 읽어야 fact 공개.
`AgentResultSource`: precompute 된 경계선 중 **요청 경계선 이하 최대** 스냅샷을 서빙 (동일 원리).
