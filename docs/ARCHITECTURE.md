# SpoKeeper — 시스템 아키텍처 (현재 구조)

> 목적: EPUB 전자책을 읽으면서, **아직 읽지 않은 뒷부분의 스포일러 없이** 지금까지 등장한
> 인물·관계·사건을 보여주는 리더. 책을 4단계 LLM 파이프라인으로 분석해 "읽은 위치(offset)"
> 기준으로 인물 관계도와 리마인더를 서빙한다.

## 1. 한눈에 보기

```
사용자(브라우저)
      │  http://localhost:8080
      ▼
┌───────────────┐   /  (정적 React dist)
│    nginx      │───────────────────────────────┐
│ (웹 서버/프록시)│   /api/*  리버스 프록시         │
└───────┬───────┘                               ▼
        │                              ┌──────────────────┐
        └─────────────────────────────▶│     backend      │
                                       │    (FastAPI)     │
                                       └───┬─────────┬────┘
                          업로드 시 분석 잡 │         │ 조회/적재
                           enqueue         ▼         ▼
                                    ┌──────────┐  ┌───────────────┐
                                    │  redis   │  │   Supabase    │
                                    │ (큐+진행률)│ │ (원격 Postgres)│
                                    └────┬─────┘  └───────▲───────┘
                                    job  │                │ 결과 적재
                                         ▼                │
                                    ┌──────────┐          │
                                    │  agent   │──────────┘
                                    │ (RQ 워커) │──────▶ Upstage LLM API
                                    └──────────┘
```

- **컨테이너 4개**: `nginx` · `backend` · `agent` · `redis` (docker compose)
- **외부 의존성 2개**: Supabase(원격 Postgres), Upstage LLM API
- `backend` 와 `agent` 는 **동일한 이미지(`spokeeper-app`)** 를 공유하고 실행 command 만 다르다.

## 2. 컨테이너별 상세

| 서비스 | 이미지 | 실행(command) | 호스트 포트 | 역할 |
|---|---|---|---|---|
| **nginx** | build `./frontend` → `nginx:1.27-alpine` | `nginx` | `8080:80` | React 정적 빌드(dist) 서빙 + `/api`→backend 리버스 프록시(SPA 폴백) |
| **backend** | `spokeeper-app` (build `.`, python3.12+node) | `uvicorn backend.app.main:app` | `8001:8000` | REST API 서빙, 업로드 시 CFI 생성(node), 분석 잡 enqueue |
| **agent** | `spokeeper-app` (동일 이미지 재사용) | `rq worker ... spokeeper` | 없음(내부) | Redis 큐에서 분석 잡 dequeue → 4단계 LLM 파이프라인 실행 |
| **redis** | `redis:7-alpine` | 기본 | 없음(내부) | 잡 큐 브로커(RQ) + 분석 진행률 공유 저장소 |

### nginx
- 멀티스테이지 빌드: `node:20-alpine` 로 `npm run build`(Vite) → 산출물 `dist/` 를 `nginx` 이미지에 복사.
- `nginx.conf`: `location / { try_files ... /index.html }` (SPA 폴백), `location /api/ { proxy_pass http://backend:8000 }` (프리픽스 유지, `client_max_body_size 100m`, `proxy_read_timeout 300s`).
- 프론트는 **빌드 전용** — 별도의 실행 컨테이너가 아니라 nginx 안에 정적 파일로 굽힌다.

### backend (FastAPI, python 3.12 + node)
- 주요 엔드포인트: `/api/books`, `/api/books/{id}`, `.../graph`, `.../reminders`, `.../progress`, `.../file`(원본 EPUB), `/api/books/upload`, `.../analysis-status`, `/api/health`.
- **읽기**: 콘텐츠 소스는 `SPO_SOURCE=agent` → Supabase(`build_agent_snapshots`) 우선 + 로컬 `precomputed/*.json` 보충.
- **업로드**: EPUB 수신 → (동기) `node cfi_tools/build_cfi_index.js` 로 CFI 인덱스 생성 후 Supabase 적재 → 즉시 응답 → (비동기) 분석 잡을 Redis 큐로 enqueue.
- 이미지에 **node 포함** 이유: 업로드 시 CFI 생성을 subprocess 로 호출하기 때문.

### agent (RQ 워커)
- backend 와 같은 코드/이미지. `rq worker` 로 `spokeeper` 큐 구독.
- 잡: `backend.app.analysis_jobs.run_full_analysis(book_id)` — **4단계 파이프라인**
  `BuildAgent(인물/관계/사건 추출) → Verifier → ReminderWriter → IndirectLeakageJudge`, 전부 Upstage LLM 호출.
- 결과를 Supabase `build_agent_snapshots` + 로컬 `precomputed/*.json` 에 적재, 진행률은 Redis 에 기록.
- 분석은 **몇 분~수십 분** 소요(LLM 다회 호출).

### redis
- RQ 큐 브로커. 분석 진행률(`status/completed/total`)도 Redis 키로 저장해 backend·agent 가 공유.

## 3. 요청 흐름 2가지

**① 읽기(평상시 서빙) — 빠름**
```
브라우저 → nginx(/api 프록시) → backend → Supabase / precomputed JSON → 응답
```
브라우저는 EPUB 본문을 epub.js 로 직접 렌더링하고, 인물 관계도(cytoscape)·리마인더는
현재 읽은 위치(offset=스포일러 경계)를 파라미터로 backend 에서 받아 그린다.

**② 업로드 → 분석 — 느림(비동기)**
```
브라우저 업로드 → nginx → backend
   ├─ (동기) node CFI 생성 → Supabase book_cfi_index, EPUB를 ./backend/data 저장 → 즉시 응답
   └─ (비동기) jobs.enqueue_analysis → redis 큐
                                        └→ agent 가 dequeue → 4단계 LLM 분석
                                             ├─ 진행률 → redis (backend가 /analysis-status로 폴링)
                                             └─ 결과 → Supabase + precomputed JSON
```

## 4. 큐를 둔 이유 (생산자 backend ↔ 소비자 agent 사이)
1. **비동기** — 분석이 오래 걸려 업로드 요청/ API 워커를 붙잡지 않도록 접수만 하고 즉시 응답.
2. **관심사·자원 분리** — 가벼운 API(backend) vs 무겁고 느린 LLM 분석(agent) 을 격리.
3. **확장** — `docker compose up --scale agent=N` 으로 워커만 늘려 병렬 처리.
4. **내구성** — agent/backend 재시작·장애 시에도 잡이 redis 에 남아 재처리 가능.
5. **부하 완충** — 업로드 폭주를 큐에 쌓고 워커가 자기 페이스로 소비(LLM 과부하/요금 방지).

## 5. 데이터 저장소 (무엇이 어디에)

| 데이터 | 위치 | 쓰는 쪽 / 읽는 쪽 |
|---|---|---|
| 책·CFI 인덱스(`books`, `book_cfi_index`) | **Supabase** (원격) | backend(업로드 시 write, 서빙 시 read) |
| 분석 결과 스냅샷(`build_agent_snapshots`) | **Supabase** (원격) | agent write / backend read |
| 분석 결과 로컬 보충본 `precomputed/*.json` | bind `./backend/data` | agent write / backend read |
| 업로드 원본 EPUB `uploaded_books/*.epub` | bind `./backend/data` | backend write / agent read (분석 입력) |
| 리더 진행 상태(reading_offset/스포일러 경계) | SQLite `./backend/data/spokeeper.db` | backend only |
| 분석 잡 진행률(status/completed/total) | **Redis** | agent write / backend read |
| Redis 영속 | named volume `redis-data` | redis |

> `./backend/data` 를 **backend·agent 가 bind mount 로 공유** → 업로드 EPUB(입력)·분석 결과(출력)를 두 컨테이너가 주고받는다.

## 6. 핵심 설계 결정 & 트레이드오프
- **단일 이미지 공유(`spokeeper-app`)**: backend·agent 코드 100% 동일 보장, 빌드 1회. 대신 이미지가 크고(≈0.9GB) 한쪽 코드 변경이 양쪽 재빌드를 유발(강결합).
- **`.env` 마운트(env_file 미사용)**: compose `env_file` 이 값의 `$` 를 변수 보간해 Supabase 비밀번호(`...$kA6`)를 깨뜨리는 걸 실측 → `./.env:/app/.env:ro` 로 마운트하고 앱 `load_dotenv()` 가 직접 읽게 함(로컬 실행과 동일 경로).
- **`SPO_EPUB_PATH` 오버라이드**: `.env` 값이 호스트 절대경로라 컨테이너에 없어 크래시 → compose `environment` 에서 컨테이너 경로로 덮어씀(`load_dotenv(override=False)` 라 compose 값 우선).
- **큐 폴백**: `REDIS_URL` 이 없으면(도커 없이 `run-local.sh`) enqueue 가 FastAPI BackgroundTask + 인메모리 진행률로 자동 폴백 → 도커 없이도 동일 코드로 동작.
- **CFI 생성은 backend 동기 처리**: 업로드 응답 전에 node 로 CFI 만 만들고 무거운 LLM 분석만 큐로 넘김(그래서 backend 이미지에 node 필요).
- **포트**: 호스트 8000 을 다른 프로젝트가 점유 중이라 backend 를 8001:8000 으로 노출(디버깅용). 사용자 접속은 nginx `8080`.

## 7. 알려진 한계 / 피드백 받고 싶은 지점
- **헬스체크 부재**: compose `depends_on` 은 기동 순서만 보장하고 준비 완료를 기다리지 않음(nginx/agent 가 backend·redis 준비 전에 뜰 수 있음). `healthcheck` + `condition: service_healthy` 미적용.
- **nginx `proxy_pass` 정적 DNS**: `backend` 를 시작 시 1회 해석 → backend 재시작으로 IP 바뀌면 stale 가능(리로드 필요). resolver 미사용.
- **backend↔agent 강결합**: 단일 이미지 공유의 단순함 vs 독립 배포 어려움.
- **Supabase 하드 의존**: 도커 구성에서 원격 Postgres 없이는 서빙 제한(precomputed JSON 보충만 존재).
- **워커 신뢰성**: RQ 기본값에 의존(재시도/타임아웃/실패 큐 정책 커스터마이즈 안 함). 단일 워커.
- **시크릿 관리**: 마운트된 `.env` 파일(시크릿 매니저 아님) — dev 수준.
- **CORS**: backend 가 여전히 `allow_origins=["*"]`(이제 nginx 동일 오리진이라 조일 여지).
- **이미지 크기**: `spokeeper-app` ≈0.9GB(python+node+LLM SDK). 슬림화 여지.

## 8. 실행
```bash
docker compose up --build        # 4개 컨테이너 기동
# 브라우저: http://localhost:8080
docker compose logs -f agent     # 분석 워커 로그
docker compose down              # 중지
```
전제: 저장소 루트에 `.env`(`SUPABASE_DB_URL`, `UPSTAGE_API_KEY`, `SPO_SOURCE=agent`) 존재.
