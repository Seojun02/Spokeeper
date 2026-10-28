# 프론트엔드: Vite 로 정적 빌드 → nginx 가 서빙 + /api 프록시.
# 최종 실행 컨테이너는 nginx 이고, React 빌드 산출물(dist)은 이미지 안에 굽는다.

# ── build stage ─────────────────────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# 빌드타임 주입: 실서버(/api) 사용 + BASE 는 상대경로(=nginx 가 같은 오리진에서 프록시).
ENV VITE_USE_MOCK=false \
    VITE_API_BASE=
RUN npm run build

# ── runtime stage (nginx) ───────────────────────────────────────────────────
FROM nginx:1.27-alpine AS run

# React 정적 빌드 산출물
COPY --from=build /app/dist /usr/share/nginx/html
# 정적 서빙 + /api 프록시 설정
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
