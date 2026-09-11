import React from 'react';

export default function Header({ isConnected, isConnecting, isSpeaking, isHearingUser, onOpenSettings }) {
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

        <button className="btn-icon" title="Service Settings" onClick={onOpenSettings}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="20" height="20">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        </button>
      </div>
    </header>
  );
}
