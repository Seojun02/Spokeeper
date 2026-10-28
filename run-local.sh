#!/usr/bin/env bash
# SpoKeeper 로컬 실행 (dev 브랜치, 도커 없이).
#   저장소 루트에서:  ./run-local.sh
#   중지: Ctrl+C  (두 서버 함께 종료)
#
# 지금까지 로컬 실행에 필요했던 셋업을 전부 자동화한다:
#   - Python venv + 백엔드 의존성 + 에이전트 LLM(langchain-upstage)
#   - CFI 빌더(Node) 의존성  (EPUB 업로드 시 필요)
#   - 프론트 의존성
#   - .env (백업에서 복원)
set -euo pipefail
cd "$(dirname "$0")"

# ── 0) .env (실 Supabase 접속 정보) ─────────────────────────────────────────
if [ ! -f .env ]; then
  if [ -f .env.localrun.bak ]; then
    cp .env.localrun.bak .env; echo "[.env] 백업(.env.localrun.bak)에서 복원"
  else
    echo "❌ .env 가 없습니다. SUPABASE_DB_URL / UPSTAGE_API_KEY / SPO_SOURCE=agent 등을 설정하세요."; exit 1
  fi
fi

# ── 1) Python venv + 의존성 ─────────────────────────────────────────────────
if [ ! -d .venv ]; then echo "[venv] 생성"; python3 -m venv .venv; fi
echo "[pip] 백엔드 의존성"
./.venv/bin/pip install -q -r backend/requirements.txt
# 에이전트 분석(BuildAgent 등)용 LLM SDK. Python 3.14 에서 tokenizers 소스빌드 회피 위해 사전빌드 휠만.
echo "[pip] langchain-upstage (에이전트 분석)"
./.venv/bin/pip install -q --only-binary=:all: langchain-upstage langchain-core

# ── 2) CFI 빌더(Node) 의존성 — EPUB 업로드 시 node cfi_tools/build_cfi_index.js 실행 ──
if [ ! -d backend/cfi_tools/node_modules ]; then
  echo "[npm] cfi_tools 의존성"; ( cd backend/cfi_tools && npm ci )
fi

# ── 3) 프론트 의존성 ─────────────────────────────────────────────────────────
if [ ! -d frontend/node_modules ]; then
  echo "[npm] frontend 의존성"; ( cd frontend && npm install )
fi

# ── 4) 이전 인스턴스 정리 (포트 재사용) ─────────────────────────────────────
lsof -ti:8000 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true
lsof -ti:5173 2>/dev/null | xargs kill 2>/dev/null || true

# ── 5) 서버 기동 ─────────────────────────────────────────────────────────────
echo ""
echo "▶ backend   http://127.0.0.1:8000"
./.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
BACK=$!
echo "▶ frontend  http://localhost:5173   ← 브라우저에서 여세요"
( cd frontend && npm run dev ) &
FRONT=$!

trap 'echo; echo "종료 중..."; kill $BACK $FRONT 2>/dev/null || true' INT TERM
wait
