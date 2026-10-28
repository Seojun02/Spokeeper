# backend(FastAPI)와 agent(RQ 워커)가 공유하는 단일 이미지.
# 같은 코드베이스를 쓰므로 이미지를 하나로 두고 compose 에서 command 만 바꿔 띄운다.
#   - backend: uvicorn (API 서빙 + 업로드 시 node CFI 생성)
#   - agent  : rq worker (Redis 큐에서 분석 잡을 집어 실행)
#
# Python 3.12 사용: 3.14 에선 langchain-upstage 계열이 소스빌드를 유발하는 이슈가
# 있어 3.12 의 사전빌드 휠을 쓴다.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# node: 업로드 시 backend 가 cfi_tools/build_cfi_index.js 를 subprocess 로 호출한다.
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs npm \
 && rm -rf /var/lib/apt/lists/*

# 파이썬 의존성 (레이어 캐시 위해 소스보다 먼저)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# CFI 빌더(Node) 의존성
COPY backend/cfi_tools/package.json backend/cfi_tools/package-lock.json /app/backend/cfi_tools/
RUN cd /app/backend/cfi_tools && npm ci

# 애플리케이션 소스 (backend + agents + cfi_tools 스크립트 등)
COPY . /app

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
