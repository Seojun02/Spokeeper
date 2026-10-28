import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 백엔드(FastAPI) 프록시 대상. 로컬(run-local.sh)에선 127.0.0.1:8000, 도커
// 구성에선 VITE_PROXY_TARGET=http://backend:8000 으로 주입한다.
// 127.0.0.1 로 고정: localhost 는 ::1(IPv6) 로 먼저 풀려 다른 리스너(예: Docker)와
// 충돌할 수 있어 IPv4 로 직접 지정한다.
const proxyTarget = process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000'

const apiProxy = {
  '/api': {
    target: proxyTarget,
    changeOrigin: true,
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // dev 서버(npm run dev): /api → 백엔드 프록시. mock 모드에선 무시됨.
  server: {
    proxy: apiProxy,
  },
  // 프로덕션 정적 빌드 서빙(npm run preview / 도커 frontend 컨테이너):
  // nginx 없이 vite preview 가 정적 파일 서빙 + /api 프록시를 함께 처리한다.
  preview: {
    host: true,
    port: 4173,
    allowedHosts: true,
    proxy: apiProxy,
  },
})
