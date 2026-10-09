import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function Header({
  isConnected,
  isConnecting,
  isSpeaking,
  isHearingUser,
  onOpenAuth,
  onOpenHistory,
  onOpenSettings,
}) {
  const { user, isAuthenticated, logout } = useAuth();
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  let statusText = 'Offline';
  let statusClass = 'status-disconnected';

  if (isConnecting) {
    statusText = 'Connecting...';
    statusClass = 'status-listening';
  } else if (isConnected) {
    if (isSpeaking) {
      statusText = 'Speaking';
      statusClass = 'status-speaking';
    } else if (isHearingUser) {
      statusText = 'Hearing You...';
      statusClass = 'status-listening';
    } else {
      statusText = 'Listening';
      statusClass = 'status-listening';
    }
  }

  const getInitials = (name) => {
    if (!name) return 'U';
    return name.slice(0, 2).toUpperCase();
  };

  return (
    <header className="app-header">
      <div className="brand-container">
        <div className="brand-logo">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="24" height="24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
          </svg>
        </div>
        <div className="brand-info">
          <h1>NovaVoice <span>AI Copilot</span></h1>
          <p className="brand-tagline">Vocode Open-Source Streaming Service (React)</p>
        </div>
      </div>

      <div className="header-actions">
        <div className={`status-pill ${statusClass}`}>
          <span className="status-dot"></span>
          <span>{statusText}</span>
        </div>

        {/* Call History Button */}
        <button
          type="button"
          className="btn-header-secondary"
          onClick={onOpenHistory}
          title="Call History & Transcripts"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
            <circle cx="12" cy="12" r="10"></circle>
            <polyline points="12 6 12 12 16 14"></polyline>
          </svg>
          <span>History</span>
        </button>

        {/* User Auth Section */}
        {isAuthenticated ? (
          <div className="user-profile-menu-container">
            <button
              type="button"
              className="user-profile-chip"
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
            >
              <div className="avatar-circle">{getInitials(user?.username)}</div>
              <span className="username-label">{user?.username}</span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
            </button>

            {isDropdownOpen && (
              <div className="user-dropdown-menu card-glass" onClick={() => setIsDropdownOpen(false)}>
                <div className="user-dropdown-header">
                  <strong>{user?.username}</strong>
                  <small>{user?.email}</small>
                </div>
                <div className="dropdown-divider"></div>
                <button
                  type="button"
                  className="dropdown-item"
                  onClick={() => {
                    setIsDropdownOpen(false);
                    if (onOpenSettings) onOpenSettings();
                  }}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                    <circle cx="12" cy="12" r="3"></circle>
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                  </svg>
                  Service Settings
                </button>
                <button
                  type="button"
                  className="dropdown-item"
                  onClick={() => {
                    setIsDropdownOpen(false);
                    if (onOpenHistory) onOpenHistory();
                  }}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                    <circle cx="12" cy="12" r="10"></circle>
                    <polyline points="12 6 12 12 16 14"></polyline>
                  </svg>
                  Call History
                </button>
                <div className="dropdown-divider"></div>
                <button
                  type="button"
                  className="dropdown-item dropdown-item-danger"
                  onClick={() => {
                    setIsDropdownOpen(false);
                    logout();
                  }}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                    <polyline points="16 17 21 12 16 7"></polyline>
                    <line x1="21" y1="12" x2="9" y2="12"></line>
                  </svg>
                  Sign Out
                </button>
              </div>
            )}
          </div>
        ) : (
          <button
            type="button"
            className="btn-header-primary"
            onClick={onOpenAuth}
          >
            Sign In / Register
          </button>
        )}
      </div>
    </header>
  );
}
