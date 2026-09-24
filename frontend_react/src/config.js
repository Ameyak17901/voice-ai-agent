/**
 * Centralized API & WebSocket Configuration
 * 
 * Supports decoupled deployments (e.g., Frontend on Vercel, Backend on Render):
 * - Vercel / Production: Uses VITE_API_URL and VITE_WS_URL environment variables.
 * - Local Development: Falls back to relative paths routed through Vite's local dev proxy.
 */

const resolveApiBaseUrl = () => {
  const envApi = import.meta.env.VITE_API_URL;
  if (envApi && envApi.trim()) {
    return envApi.trim().replace(/\/+$/, '');
  }
  return '';
};

const resolveWsBaseUrl = () => {
  const envWs = import.meta.env.VITE_WS_URL;
  if (envWs && envWs.trim()) {
    return envWs.trim().replace(/\/+$/, '');
  }

  const envApi = import.meta.env.VITE_API_URL;
  if (envApi && envApi.trim()) {
    // Automatically derive WSS/WS URL from API URL if VITE_WS_URL wasn't explicitly supplied
    const cleanApi = envApi.trim().replace(/\/+$/, '');
    if (cleanApi.startsWith('https://')) {
      return cleanApi.replace(/^https:\/\//, 'wss://');
    }
    if (cleanApi.startsWith('http://')) {
      return cleanApi.replace(/^http:\/\//, 'ws://');
    }
  }

  // Fallback for local development or same-origin deployment
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}`;
  }

  return 'ws://127.0.0.1:8000';
};

export const API_BASE_URL = resolveApiBaseUrl();
export const WS_BASE_URL = resolveWsBaseUrl();
