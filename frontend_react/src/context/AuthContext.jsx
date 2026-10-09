import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost, getStoredToken, setStoredToken } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => getStoredToken());
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState(null);

  // Validate stored token against /api/auth/me on initial load
  const checkAuth = useCallback(async () => {
    const existingToken = getStoredToken();
    if (!existingToken) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    try {
      const res = await apiGet('/api/auth/me');
      if (res.ok) {
        const userData = await res.json();
        setUser(userData);
      } else {
        // Token invalid or expired
        setStoredToken(null);
        setToken(null);
        setUser(null);
      }
    } catch (err) {
      console.error('[AuthContext] Error validating session:', err);
      setStoredToken(null);
      setToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();

    // Listen for auth_expired events dispatched by apiRequest
    const handleExpired = () => {
      setToken(null);
      setUser(null);
    };
    window.addEventListener('novavoice:auth_expired', handleExpired);
    return () => window.removeEventListener('novavoice:auth_expired', handleExpired);
  }, [checkAuth]);

  const login = async (username, password) => {
    setAuthError(null);
    try {
      const res = await apiPost('/api/auth/login', { username, password });
      const data = await res.json();
      if (!res.ok) {
        const errMsg = data.detail || 'Login failed. Please check credentials.';
        setAuthError(errMsg);
        return { success: false, error: errMsg };
      }

      setStoredToken(data.access_token);
      setToken(data.access_token);
      setUser(data.user);
      return { success: true, user: data.user };
    } catch (err) {
      const errMsg = err.message || 'Network error during login.';
      setAuthError(errMsg);
      return { success: false, error: errMsg };
    }
  };

  const register = async (username, email, password) => {
    setAuthError(null);
    try {
      const res = await apiPost('/api/auth/register', { username, email, password });
      const data = await res.json();
      if (!res.ok) {
        const errMsg = data.detail || 'Registration failed.';
        setAuthError(errMsg);
        return { success: false, error: errMsg };
      }

      setStoredToken(data.access_token);
      setToken(data.access_token);
      setUser(data.user);
      return { success: true, user: data.user };
    } catch (err) {
      const errMsg = err.message || 'Network error during registration.';
      setAuthError(errMsg);
      return { success: false, error: errMsg };
    }
  };

  const logout = () => {
    setStoredToken(null);
    setToken(null);
    setUser(null);
    setAuthError(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: Boolean(user && token),
        isLoading,
        authError,
        setAuthError,
        login,
        register,
        logout,
        refreshProfile: checkAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
