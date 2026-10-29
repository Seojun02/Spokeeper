# 🍀 SpoKeeper

> **읽은 곳까지만 알려주는 독서 도우미.** 소설을 읽다가 "이 사람 누구였지?" 싶을 때, 지금 읽은 위치까지의 내용만으로 인물 관계도와 줄거리 요약을 보여 줍니다. 뒤에 나올 내용은 보여 주지 않습니다.

[English summary](#english-summary)

## 무엇을 하나

- EPUB 소설을 올리면, 책을 일정 간격(경계선)마다 끊어 그 위치까지의 **인물, 관계, 사건**을 LLM으로 미리 분석해 둡니다.
- 독자가 책을 읽으면 현재 위치에 맞는 **인물 관계도**와 **리마인드**(여기까지의 줄거리 요약)를 보여 줍니다.
- 핵심 원칙은 하나입니다. **읽기 위치가 스포일러의 경계다.** 각 위치의 결과는 그 위치까지의 본문만으로 만듭니다.

## 이 저장소에 대해

SpoKeeper는 Upstage AI 부트캠프에서 4인 팀으로 만든 프로젝트입니다(아래 [만든 사람들](#만든-사람들)). 팀 프로젝트는 원래 저장소에 기록으로 남겨 두었습니다.

이 저장소는 팀 프로젝트가 끝난 뒤 **양준서(@Seojun02)가 개인적으로 이어서 진행한 연구와 개선**을 담은 포트폴리오용 저장소입니다. 팀 커밋 기록은 가져오지 않았습니다.

### 개인 연구에서 한 일

| 주제 | 내용 | 문서 |
|---|---|---|
| 모델 비교 | solar-pro3 → solar-pro4 교체 효과를 정답 세트로 측정. 관계 재현율 30.7% → 63.0%, 틀린 관계 20 → 2 | [model-comparison.md](docs/model-comparison.md) |
| 파이프라인 경량화 | 멀티 에이전트 파이프라인을 줄여도 정확도가 같거나 나음을 확인(LLM 호출 약 1/4) | [model-comparison.md](docs/model-comparison.md) |
| 간접 누출 판정 제거 | 리마인드 스포일러 시험 후, 이득이 없고 오히려 복선을 덧붙인 판정 에이전트를 제거 | [indirect-leakage-test.md](docs/indirect-leakage-test.md) |
| 인물 검사 | 책 하나에 맞춰진 단어 규칙 필터를 solar-decide 질문 4개로 교체 | [entity-screening.md](docs/entity-screening.md) |
| 역할 호칭 연결 | "예언자" → "브리감 영"처럼 호칭을 본문 근거가 있을 때만 기존 인물에 연결 | [entity-screening.md](docs/entity-screening.md) |
| 로컬 실행 | DB 없이 JSON 파일로 동작하는 로컬 모드 | 아래 [실행하기](#실행하기) |

파이프라인을 처음 보는 분은 [docs/pipeline-explainer.html](docs/pipeline-explainer.html)을 브라우저로 열어 보세요. 이름 세 개가 파이프라인을 지나가는 과정을 단계별로 보여 줍니다.

## 분석 파이프라인 (현재)

```text
EPUB → 청크 분할 → 경계선마다 반복
                      │
                      ▼
   증분 추출 (LLM)             지금까지 읽은 글에서 인물·관계·사건 추출
                      │
                      ▼
   인물 검사 (solar-decide)    새 이름마다 질문 4개: 개인 이름인가 / 한 명인가 /
                      │        이야기 속 인물인가 / 실재하는 존재인가
                      │        └ 역할 호칭이면 → 본문 근거로 기존 인물에 연결, 못 하면 제거
                      ▼
   동일 인물 병합 (LLM)        새 이름을 기존 인물 목록과 비교
                      │
                      ▼
   근거 검증                   원문 근거 없는 관계·사건 제거
                      │
                      ▼
   그래프 + 리마인드 (LLM)     → 위치별로 저장, 읽기 위치에 맞춰 서빙
```

- 기본 모델: `solar-pro4` (`UPSTAGE_CHAT_MODEL`로 변경)
- 인물 검사 끄기: `SCREENER=off`, 호칭 연결 끄기: `ALIAS_RESOLVE=0`

## 실행하기

DB 없이 로컬에서 실행하는 방법입니다. Python 3.12 이상(3.13에서 확인), Node.js, Upstage API 키가 필요합니다.

```bash
# 1) 설치
python -m venv .venv && .venv/Scripts/pip install -r backend/requirements.txt -r agents/requirements.txt   # macOS/Linux: .venv/bin/pip
(cd backend/cfi_tools && npm ci)
(cd frontend && npm ci)
echo "UPSTAGE_API_KEY=..." > .env

# 2) EPUB을 backend/data/ 아래에 둔다 (서버 시작 시 자동 등록, 책 ID는 파일 내용으로 정해진다)

# 3) 백엔드 (저장소 최상위에서)
SPO_SOURCE=local .venv/Scripts/python -m uvicorn backend.app.main:app --port 8000

# 4) 책 분석 (책 ID는 /api/books 에서 확인)
.venv/Scripts/python backend/scripts/run_full_analysis.py <book_id>

# 5) 프론트엔드 → http://127.0.0.1:5173
(cd frontend && npm run dev)
```

`SUPABASE_DB_URL`이 없으면 자동으로 로컬 모드가 되어 `backend/data/local_db/`의 JSON 파일을 씁니다. 원래의 Docker + Supabase 구성은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)에 있습니다.

## 저장소 구조

```text
agents/      추출·검사·병합·리마인드 에이전트 (entity_screener.py, role_alias_resolver.py 등)
backend/     FastAPI 서버, 위치별 결과 생성(precompute.py), 테스트
frontend/    React + Vite 리더 UI (관계도, 리마인드)
eval/        모델 비교 하네스, 정답 세트, 결과(eval/results), 제거한 구성요소(eval/legacy)
docs/        실험 문서, 아키텍처, 파이프라인 설명 페이지
```

## 한계

- 실험은 『주홍색의 연구』 한 권으로 했고, 정답 세트는 사람의 전수 검토를 마치지 않았습니다.
- 인물 검사의 기준값은 이 책으로 정했습니다. 다른 책에서의 적정성은 확인하지 않았습니다.
- 역할 호칭 연결은 정확도를 우선해, 본문에 호칭과 이름이 함께 나오지 않으면 연결하지 않습니다. 놓치는 연결이 많습니다.
- 번역본 원문과 그 분석 결과는 저작권 때문에 저장소에 넣지 않았습니다.

## 만든 사람들

팀 프로젝트(Upstage AI 부트캠프):

| 이름 | 역할 | GitHub |
|---|---|---|
| 김원재 | 백엔드 및 아키텍처 | @1jaekim |
| 양준서 | 프로젝트 매니저 | @Seojun02 |
| 최정재 | AI 에이전트 개발 | @Giseulg |
| 현지민 | UX/UI | @jmmom0320 |

팀 이후의 개인 연구(이 저장소의 추가 작업): 양준서

---

## English summary

**SpoKeeper** is a spoiler-safe reading assistant. For an EPUB novel, it pre-computes characters, relationships, and events at fixed reading positions, and shows a relationship graph and a story reminder based only on the text up to the reader's current position.

It started as a 4-person team project at the Upstage AI Bootcamp. This repository holds the follow-up research by Seojun Yang (@Seojun02):

- **Model comparison:** switching extraction from solar-pro3 to solar-pro4 doubled core-relation recall (30.7% → 63.0%) and cut wrong relations from 20 to 2 on a hand-built answer set ([details](docs/model-comparison.md)).
- **Lighter pipeline:** a reduced pipeline matched or beat the full multi-agent one with about 1/4 of the LLM calls.
- **Removed the indirect-leakage judge** after a reminder spoiler test showed no benefit ([details](docs/indirect-leakage-test.md)).
- **Entity screening:** replaced a book-specific word-list filter with four solar-decide questions, and links role names (e.g., "the prophet") to named characters only when the text names both in one sentence ([details](docs/entity-screening.md)).
- **Local mode:** runs without a database, using JSON files.

Limits: one book, an answer set not fully human-reviewed, thresholds tuned on that book.
