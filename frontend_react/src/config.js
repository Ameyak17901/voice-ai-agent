/**
 * Centralized API & WebSocket Endpoint Configuration
 *
 * Automatically supports:
 * 1. Local Development (via Vite dev server proxy at /api and /conversation)
 * 2. Vercel Production Deployments (configured with VITE_BACKEND_URL or VITE_API_URL/VITE_WS_URL)
 * 3. Unified Container Deployments
 */

const rawBackendUrl = (import.meta.env.VITE_BACKEND_URL || import.meta.env.VITE_API_URL || '').trim();

export const API_BASE_URL = rawBackendUrl.replace(/\/$/, '');

export const getWebSocketUrl = (persona) => {
  const personaParam = persona ? `?persona=${encodeURIComponent(persona)}` : '';

  // Explicit WebSocket URL if configured
  if (import.meta.env.VITE_WS_URL) {
    const wsBase = import.meta.env.VITE_WS_URL.trim().replace(/\/$/, '');
    return `${wsBase}/conversation${personaParam}`;
  }

  // Derive from VITE_BACKEND_URL (e.g. https://my-backend.railway.app -> wss://my-backend.railway.app)
  if (rawBackendUrl) {
    const wsBase = rawBackendUrl.replace(/^http/, 'ws').replace(/\/$/, '');
    return `${wsBase}/conversation${personaParam}`;
  }

  // Fallback to current browser origin (local development with Vite proxy or unified server)
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/conversation${personaParam}`;
};
