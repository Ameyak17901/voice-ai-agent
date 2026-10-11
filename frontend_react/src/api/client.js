import { API_BASE_URL } from '../config';

const ACCESS_TOKEN_KEY = 'novavoice_jwt_token';
const REFRESH_TOKEN_KEY = 'novavoice_refresh_token';

export function getStoredToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setStoredToken(token) {
  if (token) {
    localStorage.setItem(ACCESS_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
  }
}

export function getStoredRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setStoredRefreshToken(refreshToken) {
  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  } else {
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  }
}

export function clearAllTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

// Concurrency lock so multiple simultaneous 401s queue behind a single refresh request
let refreshPromise = null;

async function executeTokenRefresh() {
  const currentRefreshToken = getStoredRefreshToken();
  if (!currentRefreshToken) {
    throw new Error('No refresh token available');
  }

  const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: currentRefreshToken }),
  });

  if (!response.ok) {
    clearAllTokens();
    window.dispatchEvent(new CustomEvent('novavoice:auth_expired'));
    throw new Error('Failed to refresh session');
  }

  const data = await response.json();
  setStoredToken(data.access_token);
  setStoredRefreshToken(data.refresh_token);

  // Notify components that session was refreshed with updated token & user
  window.dispatchEvent(new CustomEvent('novavoice:auth_refreshed', { detail: data }));
  return data.access_token;
}

export async function apiRequest(endpoint, options = {}, isRetry = false) {
  const url = `${API_BASE_URL}${endpoint}`;
  const token = getStoredToken();

  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  // Senior Engineer Interceptor:
  // If response is 401 and we haven't retried yet and this is not already an auth endpoint
  if (response.status === 401 && !isRetry && !endpoint.startsWith('/api/auth/login') && !endpoint.startsWith('/api/auth/refresh')) {
    const refreshToken = getStoredRefreshToken();
    if (refreshToken) {
      try {
        if (!refreshPromise) {
          refreshPromise = executeTokenRefresh().finally(() => {
            refreshPromise = null;
          });
        }
        const newAccessToken = await refreshPromise;

        // Replay original request with the new access token
        const retryHeaders = {
          ...headers,
          'Authorization': `Bearer ${newAccessToken}`,
        };
        return await fetch(url, {
          ...options,
          headers: retryHeaders,
        });
      } catch (refreshErr) {
        console.warn('[API Client] Refresh rotation failed:', refreshErr);
        clearAllTokens();
        window.dispatchEvent(new CustomEvent('novavoice:auth_expired'));
        return response;
      }
    } else {
      clearAllTokens();
      window.dispatchEvent(new CustomEvent('novavoice:auth_expired'));
    }
  }

  return response;
}

export async function apiGet(endpoint) {
  return apiRequest(endpoint, { method: 'GET' });
}

export async function apiPost(endpoint, body) {
  return apiRequest(endpoint, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function apiDelete(endpoint) {
  return apiRequest(endpoint, { method: 'DELETE' });
}
