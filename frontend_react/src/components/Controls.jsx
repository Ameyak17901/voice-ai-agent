import React from 'react';

const FALLBACK_METADATA = {
  concierge: { label: 'Nova — Executive Concierge', icon: '✨' },
  receptionist: { label: 'Chloe — Medical Receptionist', icon: '🏥' },
  tech_screener: { label: 'Alex — Technical Interviewer', icon: '💻' },
  school_receptionist: { label: 'Mary — School Receptionist', icon: '🏫' },
};

export default function Controls({
  isConnected,
  isConnecting,
  isMuted,
  persona,
  personas = [],
  onPersonaChange,
  onOpenAgentBuilder,
  onDeletePersona,
  onToggleSession,
  onToggleMute,
}) {
  // Separate built-in and custom personas
  const builtinList = personas.filter(p => !p.is_custom);
  const customList = personas.filter(p => p.is_custom);

  // Check if current persona is custom to show delete button
  const currentPersonaObj = personas.find(p => p.id === persona);
  const isCurrentCustom = currentPersonaObj?.is_custom;

  return (
    <div className="controls-container">
      <div className="stage-controls-top">
        <div className="persona-selector" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <label htmlFor="personaSelect" style={{ fontWeight: 600 }}>Persona:</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <select
              id="personaSelect"
              value={persona}
              disabled={isConnected || isConnecting}
              onChange={(e) => onPersonaChange(e.target.value)}
              title={isConnected ? "End current call to switch persona" : "Select AI Persona"}
              style={{ minWidth: '220px' }}
            >
              {builtinList.length > 0 ? (
                <>
                  <optgroup label="Standard Built-in Personas">
                    {builtinList.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.icon || '🤖'} {p.name}
                      </option>
                    ))}
                  </optgroup>
                  {customList.length > 0 && (
                    <optgroup label="Custom Created Agents">
                      {customList.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.icon || '✨'} {p.name} (Custom)
                        </option>
                      ))}
                    </optgroup>
                  )}
                </>
              ) : (
                Object.keys(FALLBACK_METADATA).map((key) => {
                  const meta = FALLBACK_METADATA[key];
                  return (
                    <option key={key} value={key}>
                      {meta.icon} {meta.label}
                    </option>
                  );
                })
              )}
            </select>

            {/* Button to trigger custom agent builder modal */}
            <button
              type="button"
              className="btn-secondary"
              onClick={onOpenAgentBuilder}
              disabled={isConnected || isConnecting}
              title="Build and customize a new Voice AI Agent"
              style={{
                padding: '6px 12px',
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                whiteSpace: 'nowrap'
              }}
            >
              <span>➕</span>
              <span>New Agent</span>
            </button>

            {/* Optional delete button if user selected a custom agent */}
            {isCurrentCustom && !isConnected && !isConnecting && (
              <button
                type="button"
                className="btn-icon"
                onClick={() => onDeletePersona && onDeletePersona(persona)}
                title="Delete this custom agent"
                style={{
                  color: '#f87171',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.25)',
                  width: '34px',
                  height: '34px'
                }}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            )}
          </div>
        </div>

        <div className="latency-metrics">
          <span className="metric-label">Pipeline:</span>
          <span className="metric-value">Full-Duplex Streaming</span>
        </div>
      </div>

      <div className="stage-actions">
        <button
          className={`btn-primary ${isConnected ? 'btn-active-call' : ''}`}
          disabled={isConnecting}
          onClick={onToggleSession}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="20" height="20">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
          </svg>
          <span>
            {isConnecting
              ? 'Connecting...'
              : isConnected
              ? 'End Voice Session'
              : 'Start Voice Session'}
          </span>
        </button>

        <button
          className={`btn-secondary ${isMuted ? 'is-muted' : ''}`}
          disabled={!isConnected}
          onClick={onToggleMute}
        >
          {isMuted ? (
            <>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="18" height="18">
                <line x1="1" y1="1" x2="23" y2="23"></line>
                <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"></path>
                <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"></path>
                <line x1="12" y1="19" x2="12" y2="23"></line>
                <line x1="8" y1="23" x2="16" y2="23"></line>
              </svg>
              <span>Unmute Mic</span>
            </>
          ) : (
            <>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="18" height="18">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                <line x1="12" y1="19" x2="12" y2="23"></line>
                <line x1="8" y1="23" x2="16" y2="23"></line>
              </svg>
              <span>Mute Mic</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
