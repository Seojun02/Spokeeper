# SpoKeeper — Frontend (React + FastAPI 서빙 담당)

스포일러 없이 읽는 리딩 컴패니언. 사용자가 읽은 경계선까지의 정보만 보여준다.
계약(`graph_json`·`reminders`) 소비 전용 — FE는 계약이 이미 스포일러 안전하다고 신뢰한다.

## 스택
React 18 + TS · Vite · TanStack Query · Zustand · Tailwind v4

## 실행
```bash
npm install
npm run dev        # mock 모드 (VITE_USE_MOCK=true, 기본)
npm run build      # 타입체크 + 프로덕션 번들
```

## mock ↔ 실서버 스위치
- `.env`의 `VITE_USE_MOCK=true` → MOCKS.md 픽스처 사용 (BE 없이 개발).
- `VITE_USE_MOCK=false` → `/api`를 FastAPI(:8000)로 프록시 (vite.config.ts).
  ```bash
  VITE_USE_MOCK=false npm run dev   # backend uvicorn 먼저 실행
  ```

## 구조
```
src/
  api/        types(계약) · mock(픽스처) · client(mock↔실서버) · hooks(Query)
  components/ Header · ReaderView · Footer · SlideOverPanel
              · RelationshipPanel/Graph/List · ReminderPanel · SettingsPanel
  lib/        mergeEdges((source,label) 병합) · constants(청크경계)
  store.ts    Zustand (spoilerSafe/panel/offset/boundary)
```

## 데모 상태 (offset별 관계도)
- `offset 150` → 빈 그래프 (읽은 청크 없음)
- `offset 215` → c1: 개체3·관계2
- `offset 380` → c1+c2+c3: 개체5·관계5 (윤 팀장 — 압박 조사 — 민우/서현 병합)
