import React, { useState, useEffect, useRef } from 'react';

export default function TranscriptFeed({
  transcripts,
  interimTranscript,
  onClear,
  onSendMessage,
  personaName,
  activePersona,
  personas = [],
}) {
  const [inputText, setInputText] = useState('');
  const feedEndRef = useRef(null);

  const personasMap = React.useMemo(() => {
    const map = {};
    for (const p of personas) {
      if (p?.id) map[p.id] = p;
    }
    return map;
  }, [personas]);

  const defaultAgentLabel = activePersona?.name || personaName || 'AI Copilot';

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcripts, interimTranscript]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!inputText.trim()) return;
    onSendMessage(inputText.trim());
    setInputText('');
  };

  return (
    <div className="transcript-card card-glass">
      <div className="transcript-header">
        <h2>Live Audio Transcript</h2>
        <button className="btn-text-action" onClick={onClear} title="Clear Transcript">
          Clear
        </button>
      </div>

      <div className="transcript-feed">
        {transcripts.length === 0 && !interimTranscript ? (
          <div className="transcript-empty-state">
            <div className="empty-icon">🎙️</div>
            <p>Start a session and speak naturally.</p>
            <small>
              Your voice audio and {activePersona?.name ? `${activePersona.name}'s` : "the agent's"} spoken responses will stream here in real-time.
            </small>
          </div>
        ) : (
          transcripts.map((item) => {
            const isUser = item.sender === 'human' || item.sender === 'user';
            const itemPersona = item.persona ? personasMap[item.persona] : null;
            const botLabel = item.agentName || (itemPersona ? itemPersona.name : defaultAgentLabel);
            return (
              <div
                key={item.id}
                className={`chat-bubble ${isUser ? 'bubble-user' : 'bubble-agent'}`}
              >
                <div className="bubble-meta">
                  <strong>{isUser ? 'You' : botLabel}</strong>
                  <span>• {item.timestamp}</span>
                </div>
                <div className="bubble-content">{item.text}</div>
              </div>
            );
          })
        )}
        {interimTranscript && (
          <div
            className="chat-bubble bubble-user bubble-interim"
            style={{ opacity: 0.9, fontStyle: 'italic', border: '1px dashed var(--secondary)' }}
          >
            <div className="bubble-meta">
              <span style={{ color: 'var(--secondary)', fontWeight: 600 }}>🎙️ Hearing speech...</span>
            </div>
            <div
              className="bubble-content"
              style={{ background: 'rgba(6, 182, 212, 0.2)', color: 'var(--text-main)' }}
            >
              {interimTranscript.text}
              <span style={{ animation: 'pulseDot 1s infinite', marginLeft: '6px' }}>●</span>
            </div>
          </div>
        )}
        <div ref={feedEndRef} />
      </div>

      <form className="text-intercom-box" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Type or speak a message..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
        />
        <button type="submit" className="btn-intercom-send">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
          </svg>
        </button>
      </form>
    </div>
  );
}
