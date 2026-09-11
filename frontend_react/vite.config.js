import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', (err) => {
            if (err.code === 'ECONNRESET' || err.code === 'EPIPE') return;
            console.warn('[Vite API Proxy]:', err.message);
          });
        }
      },
      '/conversation': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        configure: (proxy) => {
          proxy.on('error', (err) => {
            if (err.code === 'ECONNRESET' || err.code === 'EPIPE') return;
            console.warn('[Vite WS Proxy Warning]:', err.message);
          });
          proxy.on('proxyReqWs', (proxyReq, req, socket) => {
            socket.on('error', (err) => {
              if (err.code === 'ECONNRESET' || err.code === 'EPIPE') return;
              console.warn('[Vite WS Socket Warning]:', err.message);
            });
          });
        }
      }
    }
  }
})
