# 🍀 SpoKeeper

<div align="right">

[🇺🇸 English Version](#-english-version)

</div>

> **"읽기 위치가 스포일러의 경계가 됩니다."**

---

## 1. 프로젝트 소개

**SpoKeeper**는 사용자가 현재까지 읽은 소설의 내용만을 기반으로 **인물 관계도(Context Graph)** 와 **맥락 리마인드(Context Reminder)** 를 제공하는 AI 기반 **Spoiler-Safe 독서 보조 서비스**입니다.

기존 AI 요약 서비스나 RAG 기반 검색은 책 전체를 참조하기 때문에 의도치 않은 스포일러가 발생할 수 있습니다.

SpoKeeper는 **현재 읽기 위치(Offset)** 를 기준으로 정보 접근을 제한하고, **Multi-Agent Workflow**를 통해 미래 내용을 차단하면서 독서 경험을 돕는 것을 목표로 합니다.

사용자는 EPUB 소설을 업로드한 후 평소처럼 책을 읽기만 하면 됩니다.

SpoKeeper는 사용자의 현재 읽기 위치까지 등장한 다음 정보를 자동으로 분석합니다.

* 등장인물
* 인물 관계
* 주요 사건

현재까지 읽은 내용만을 기반으로 다음 기능을 제공합니다.

* 인물 관계도
* Context Reminder

---

## 2. 문제 정의

독서 중 AI를 활용할 때 가장 큰 문제는 **스포일러**입니다.

| 문제          | 설명                           |
| ----------- | ---------------------------- |
| 스포일러 발생     | AI가 미래 사건이나 등장인물을 함께 설명하는 문제 |
| 등장인물 기억 어려움 | 장편 소설일수록 인물 관계를 기억하기 어려움     |
| 줄거리 기억 부족   | 오랜만에 다시 읽으면 앞 내용을 잊어버림       |

기존 AI 요약 서비스나 RAG 기반 검색은 책 전체를 참조할 수 있기 때문에, 사용자가 아직 읽지 않은 미래 사건이나 등장인물 정보를 의도치 않게 제공할 수 있습니다.

SpoKeeper는 **"현재 읽은 위치까지만"** 정보를 제공하여 이러한 문제를 해결합니다.

---

## 3. 문제 해결

SpoKeeper는 사용자의 **현재 읽기 위치(Offset)** 를 스포일러의 경계로 설정합니다.

사용자가 EPUB 소설을 업로드하면 본문과 챕터를 분석하고, 현재 읽은 위치까지 등장한 인물, 관계, 사건을 추출합니다.

이후 **Multi-Agent Workflow**를 통해 현재 Offset 이후의 정보가 사용자에게 노출되지 않도록 제한합니다.

### Spoiler Guard

#### 1. VerifierAgent (1차 Guard)

RetrieverAgent가 검색한 결과 중 다음 조건을 만족하는 정보만 통과시킵니다.

> **정보 Offset ≤ 사용자 Offset**

#### 2. ReminderWriterAgent

현재 Offset 이하의 정보만 이용하여 리마인드를 생성합니다.

추측, 해석, 미래 예측은 수행하지 않습니다.

#### 3. Render Guard (예정)

생성된 결과를 다시 Offset 기준으로 검증하여 미래 정보가 포함되지 않았는지 확인합니다.

#### 4. IndirectLeakageJudge (예정)

직접적인 스포일러뿐 아니라 다음 요소까지 판단합니다.

* 암시
* 복선
* 미래를 연상시키는 표현

판단 결과에 따라 다음 중 하나를 선택합니다.

* `PASS`
* `REWRITE`
* `SUPPRESS`

### Agent Workflow

```text
                 EPUB
                   │
             ParserAgent
                   │
             ChunkAgent
                   │
              ChromaDB
                   │
      Incremental BuildAgent
                   │
             BuildAgent
                   │
         Knowledge Graph
        ┌──────────┴──────────┐
        ▼                     ▼
 CharacterProfiler      Graph Viewer
        │
        ▼
 Avatar Prompt (예정)

────────────────────────────────────

       RetrieverAgent
              │
              ▼
      VerifierAgent
              │
              ▼
    ReminderWriterAgent
              │
              ▼
 IndirectLeakageJudge (예정)
              │
              ▼
      Render Guard (예정)
              │
              ▼
            사용자
```

### 프로젝트 구조

저장소는 `frontend` / `backend` / `agents` 세 개의 주요 폴더로 구성됩니다.

```text
.
├── frontend/                # React + Vite (읽기 UI, 관계도, 리마인드)
│   ├── src/
│   │   ├── api/             # 통합 계약 타입·클라이언트·훅
│   │   └── components/
│   └── vite.config.ts       # /api → 127.0.0.1:8000 프록시
│
├── backend/                 # FastAPI 서빙 (graph_json, reminders, progress 계약)
│   ├── app/
│   │   ├── main.py          # 라우트 + 소스 주입(_make_source)
│   │   ├── schemas.py       # 통합 계약 스키마
│   │   ├── content_source.py# FixtureSource / AgentResultSource
│   │   ├── agent_adapter.py # 에이전트 출력 → 계약 변환
│   │   ├── precompute.py    # 경계선별 build 결과 → 계약 JSON 저장소
│   │   └── db.py, fixtures.py
│   ├── scripts/make_demo_store.py
│   └── tests/
│
└── agents/                  # AI 에이전트 파이프라인 (Solar-Pro2 + LangChain)
    ├── build_agent.py       # 인물·관계·사건 추출 (+ 증분 빌드)
    ├── character_profiler_agent.py
    ├── parsers/epub_parser.py
    ├── tools/chunk_tool.py
    ├── config.py
    ├── app.py               # Streamlit 프로토타입
    ├── data/books/          # EPUB 샘플
    └── requirements.txt
```

**실행:** 모든 명령은 저장소 최상위 경로에서 실행합니다.

`agents`와 `backend`는 저장소 최상위를 `sys.path` 기준으로 사용합니다.

```python
from agents.build_agent import ...
from backend.app...
```

### 기술 스택

#### AI

* Upstage Solar-Pro2
* LangChain

#### Vector Database

* ChromaDB

#### Backend

* Python
* Streamlit (Prototype)

#### 예정

* FastAPI
* React

---

## 4. 핵심 기능

### EPUB Parser

EPUB 파일에서 본문과 챕터를 자동으로 추출합니다.

### AI BuildAgent

등장인물, 관계, 사건을 자동으로 분석합니다.

### Knowledge Graph

현재 읽은 위치까지 등장한 인물 관계를 시각화합니다.

### Context Reminder

현재 읽은 위치까지의 내용을 자연스럽게 요약합니다.

### Spoiler Guard

Offset을 기준으로 미래 내용을 차단하여 스포일러를 방지합니다.

### 개발 진행 현황

| 기능                     | 상태 |
| ---------------------- | -- |
| EPUB Parser            | ✅  |
| Chunk Generator        | ✅  |
| ChromaDB               | ✅  |
| Incremental BuildAgent | ✅  |
| BuildAgent             | ✅  |
| CharacterProfilerAgent | ✅  |
| Graph Viewer           | ✅  |
| VerifierAgent          | ✅  |
| ReminderWriterAgent    | 🚧 |
| Render Guard           | 🚧 |
| IndirectLeakageJudge   | 🚧 |
| AvatarGeneratorAgent   | 🚧 |

### 기대 효과

#### 독자

* 등장인물 관계를 쉽게 이해
* 줄거리 기억 부담 감소
* 스포일러 없는 독서 경험

#### AI 서비스

* Offset 기반 접근 제어
* Multi-Agent Workflow
* Knowledge Graph 기반 관계 관리
* Spoiler Guard 구조를 통한 안전한 AI 독서 지원

---

## 5. 데모 영상

프로젝트를 확인할 수 있는 데모 영상 및 시연 자료를 첨부합니다.

* **데모 영상:** 추가 예정
* **배포 URL:** 추가 예정
* **추가 시연 자료:** 추가 예정

---

## 6. 팀원 소개

| 이름  | 역할         | GitHub     |
| --- | ---------- | ---------- |
| 김원재 | 백엔드 및 아키텍처 | @1jaekim   |
| 양준서 | 프로젝트 매니저   | @Seojun02  |
| 최정재 | AI 에이전트 개발 | @Giseulg   |
| 현지민 | UX/UI      | @jmmom0320 |

---

## 7. 참고자료 / 발표자료

프로젝트를 이해하는 데 도움이 되는 자료를 첨부합니다.

* **발표자료:** 추가 예정
* **기획서:** 추가 예정
* **참고한 문서:** 추가 예정
* **참고한 오픈소스:** 추가 예정
* **기타 자료:** 추가 예정

---

# 🇺🇸 English Version

<details>
<summary><b>🇺🇸 Click to view the English version</b></summary>

<br>

> **"Your reading position becomes the boundary against spoilers."**

---

## 1. Project Introduction

**SpoKeeper** is an AI-powered **Spoiler-Safe Reading Assistant** that provides a **Character Relationship Graph (Context Graph)** and **Context Reminder** based only on the content of a novel that the user has read so far.

Existing AI summarization services and RAG-based search systems may reference the entire book, which can unintentionally expose users to spoilers.

SpoKeeper aims to enhance the reading experience while preventing access to future content by restricting information based on the user's **current reading position (Offset)** and using a **Multi-Agent Workflow**.

Users simply upload an EPUB novel and read it as usual.

SpoKeeper automatically analyzes the following information that has appeared up to the user's current reading position:

* Characters
* Character relationships
* Major events

Based only on the content read so far, it provides:

* Character Relationship Graph
* Context Reminder

---

## 2. Problem Definition

The biggest challenge when using AI while reading is **spoilers**.

| Problem                           | Description                                                                          |
| --------------------------------- | ------------------------------------------------------------------------------------ |
| Spoiler Exposure                  | AI may reveal future events or characters                                            |
| Difficulty Remembering Characters | It becomes increasingly difficult to remember character relationships in long novels |
| Difficulty Remembering the Story  | Readers may forget previous events when returning to a book after a long break       |

Existing AI summarization services and RAG-based search systems may reference the entire book, potentially exposing users to future events or characters they have not yet encountered.

SpoKeeper solves these problems by providing information **only up to the user's current reading position**.

---

## 3. Problem Solution

SpoKeeper defines the user's **current reading position (Offset)** as the boundary against spoilers.

When a user uploads an EPUB novel, SpoKeeper analyzes the text and chapters and extracts characters, relationships, and events that have appeared only up to the user's current reading position.

A **Multi-Agent Workflow** then prevents information beyond the current Offset from being exposed to the user.

### Spoiler Guard

#### 1. VerifierAgent (First Guard)

Among the results retrieved by the RetrieverAgent, only information that satisfies the following condition is allowed to pass:

> **Information Offset ≤ User Offset**

#### 2. ReminderWriterAgent

The ReminderWriterAgent generates reminders using only information at or below the current Offset.

It does not perform speculation, interpretation, or prediction of future events.

#### 3. Render Guard (Planned)

The generated results are verified again based on the Offset to ensure that no future information is included.

#### 4. IndirectLeakageJudge (Planned)

In addition to direct spoilers, the IndirectLeakageJudge evaluates elements such as:

* Implications
* Foreshadowing
* Expressions that may suggest future events

Based on the evaluation result, one of the following actions is selected:

* `PASS`
* `REWRITE`
* `SUPPRESS`

### Agent Workflow

```text
                 EPUB
                   │
             ParserAgent
                   │
             ChunkAgent
                   │
              ChromaDB
                   │
      Incremental BuildAgent
                   │
             BuildAgent
                   │
         Knowledge Graph
        ┌──────────┴──────────┐
        ▼                     ▼
 CharacterProfiler      Graph Viewer
        │
        ▼
 Avatar Prompt (Planned)

────────────────────────────────────

       RetrieverAgent
              │
              ▼
      VerifierAgent
              │
              ▼
    ReminderWriterAgent
              │
              ▼
 IndirectLeakageJudge (Planned)
              │
              ▼
      Render Guard (Planned)
              │
              ▼
             User
```

### Project Structure

The repository consists of three main directories: `frontend`, `backend`, and `agents`.

```text
.
├── frontend/                # React + Vite (Reading UI, Graph, Reminder)
│   ├── src/
│   │   ├── api/             # Unified contract types, client, and hooks
│   │   └── components/
│   └── vite.config.ts       # /api → 127.0.0.1:8000 proxy
│
├── backend/                 # FastAPI serving (graph_json, reminders, progress contract)
│   ├── app/
│   │   ├── main.py          # Routes + source injection (_make_source)
│   │   ├── schemas.py       # Unified contract schemas
│   │   ├── content_source.py# FixtureSource / AgentResultSource
│   │   ├── agent_adapter.py # Agent output → contract conversion
│   │   ├── precompute.py    # Boundary-based build results → contract JSON storage
│   │   └── db.py, fixtures.py
│   ├── scripts/make_demo_store.py
│   └── tests/
│
└── agents/                  # AI Agent Pipeline (Solar-Pro2 + LangChain)
    ├── build_agent.py       # Character, relationship, and event extraction (+ incremental build)
    ├── character_profiler_agent.py
    ├── parsers/epub_parser.py
    ├── tools/chunk_tool.py
    ├── config.py
    ├── app.py               # Streamlit prototype
    ├── data/books/          # EPUB samples
    └── requirements.txt
```

**Execution:** All commands should be run from the repository root directory.

The `agents` and `backend` modules use the repository root as the `sys.path` base.

```python
from agents.build_agent import ...
from backend.app...
```

### Tech Stack

#### AI

* Upstage Solar-Pro2
* LangChain

#### Vector Database

* ChromaDB

#### Backend

* Python
* Streamlit (Prototype)

#### Planned

* FastAPI
* React

---

## 4. Core Features

### EPUB Parser

Automatically extracts text and chapters from EPUB files.

### AI BuildAgent

Automatically analyzes characters, relationships, and events.

### Knowledge Graph

Visualizes character relationships that have appeared up to the user's current reading position.

### Context Reminder

Naturally summarizes the story only up to the user's current reading position.

### Spoiler Guard

Prevents spoilers by blocking future information based on the user's current Offset.

### Development Status

| Feature                | Status |
| ---------------------- | ------ |
| EPUB Parser            | ✅      |
| Chunk Generator        | ✅      |
| ChromaDB               | ✅      |
| Incremental BuildAgent | ✅      |
| BuildAgent             | ✅      |
| CharacterProfilerAgent | ✅      |
| Graph Viewer           | ✅      |
| VerifierAgent          | ✅      |
| ReminderWriterAgent    | 🚧     |
| Render Guard           | 🚧     |
| IndirectLeakageJudge   | 🚧     |
| AvatarGeneratorAgent   | 🚧     |

### Expected Benefits

#### For Readers

* Easier understanding of character relationships
* Reduced burden of remembering previous story details
* A spoiler-free reading experience

#### For AI Services

* Offset-based access control
* Multi-Agent Workflow
* Knowledge Graph-based relationship management
* Safe AI-powered reading assistance through the Spoiler Guard architecture

---

## 5. Demo Video

Demo videos and other materials showcasing the project can be found below.

* **Demo Video:** Coming soon
* **Deployment URL:** Coming soon
* **Additional Demo Materials:** Coming soon

---

## 6. Team Members

| Name          | Role                   | GitHub     |
| ------------- | ---------------------- | ---------- |
| Wonjae Kim    | Backend & Architecture | @1jaekim   |
| Junseo Yang   | Project Manager        | @Seojun02  |
| Jeongjae Choi | AI Agent Development   | @Giseulg   |
| Jimin Hyun    | UX/UI                  | @jmmom0320 |

---

## 7. References / Presentation Materials

Materials that provide additional information about the project are listed below.

* **Presentation:** Coming soon
* **Project Plan:** Coming soon
* **Reference Documents:** Coming soon
* **Open Source References:** Coming soon
* **Other Materials:** Coming soon

</details>
