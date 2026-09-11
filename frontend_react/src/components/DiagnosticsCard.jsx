import React from 'react';

export default function DiagnosticsCard({ systemStatus, activePersona }) {
  const hasStt = systemStatus?.has_stt_creds;
  const hasLlm = systemStatus?.has_llm_creds;
  const ttsProvider = systemStatus?.tts_provider || 'stream_elements';

  return (
    <div className="diagnostics-card card-glass">
      <div className="diag-header">
        <h3>Service Status</h3>
        <span className="badge-online">Connected</span>
      </div>

      <div className="diag-grid">
        <div className="diag-item">
          <span className="diag-title">STT (Speech-to-Text)</span>
          <span className={`diag-badge ${hasStt ? 'badge-success' : 'badge-warning'}`}>
            {hasStt ? 'Deepgram (Active)' : 'Demo / WebSpeech'}
          </span>
        </div>

        <div className="diag-item">
          <span className="diag-title">LLM Intelligence</span>
          <span className={`diag-badge ${hasLlm ? 'badge-success' : 'badge-warning'}`}>
            {hasLlm ? 'Gemini 3.5 Flash Lite' : 'Built-in Copilot'}
          </span>
        </div>

        <div className="diag-item">
          <span className="diag-title">TTS Voice Engine</span>
          <span className="diag-badge badge-success">
            {ttsProvider.toUpperCase()}
          </span>
        </div>

        <div className="diag-item">
          <span className="diag-title">Active Persona</span>
          <span
            className="diag-badge badge-success"
            style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            title={activePersona?.name || 'Nova Copilot'}
          >
            {activePersona?.name || 'Nova Copilot'}
          </span>
        </div>
      </div>
    </div>
  );
}
