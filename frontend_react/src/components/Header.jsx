import React from 'react';

export default function Header({ isConnected, isConnecting, isSpeaking, isHearingUser }) {
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
      </div>
    </header>
  );
}
