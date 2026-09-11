import React, { useState } from 'react';

export default function SettingsModal({ isOpen, onClose, onSave, currentTts }) {
  const [openAiKey, setOpenAiKey] = useState('');
  const [deepgramKey, setDeepgramKey] = useState('');
  const [cartesiaKey, setCartesiaKey] = useState('');
  const [elevenLabsKey, setElevenLabsKey] = useState('');
  const [ttsProvider, setTtsProvider] = useState(currentTts || 'eleven_labs');

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave({
      openai_api_key: openAiKey || undefined,
      deepgram_api_key: deepgramKey || undefined,
      cartesia_api_key: cartesiaKey || undefined,
      eleven_labs_api_key: elevenLabsKey || undefined,
      tts_provider: ttsProvider,
    });
  };

  const handleTestChime = () => {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.2);

      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start();
      osc.stop(ctx.currentTime + 0.5);
    } catch (e) {
      alert('Audio error: ' + e.message);
    }
  };

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer-panel card-glass" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <h2>Service Settings & API Keys</h2>
          <button className="btn-icon" onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="20" height="20">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <form className="drawer-body" onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="openAiKey">OpenAI API Key (LLM)</label>
            <input
              type="password"
              id="openAiKey"
              placeholder="sk-proj-..."
              value={openAiKey}
              onChange={(e) => setOpenAiKey(e.target.value)}
            />
            <small>Enables dynamic GPT-4o-mini dialogue generation.</small>
          </div>

          <div className="form-group">
            <label htmlFor="deepgramKey">Deepgram API Key (Real-time STT)</label>
            <input
              type="password"
              id="deepgramKey"
              placeholder="Deepgram Token..."
              value={deepgramKey}
              onChange={(e) => setDeepgramKey(e.target.value)}
            />
            <small>Used for sub-200ms streaming speech-to-text.</small>
          </div>

          <div className="form-group">
            <label htmlFor="ttsSelect">TTS Speech Engine</label>
            <select
              id="ttsSelect"
              value={ttsProvider}
              onChange={(e) => setTtsProvider(e.target.value)}
            >
              <option value="eleven_labs">ElevenLabs Turbo v2.5 (Studio Quality - Active)</option>
              <option value="edge_tts">Microsoft Edge TTS (Neural)</option>
              <option value="stream_elements">StreamElements (Free / Zero-config)</option>
              <option value="cartesia">Cartesia Sonic (Ultra-low latency)</option>
              <option value="azure">Azure Cognitive Speech</option>
            </select>
          </div>

          {ttsProvider === 'cartesia' && (
            <div className="form-group">
              <label htmlFor="cartesiaKey">Cartesia API Key</label>
              <input
                type="password"
                id="cartesiaKey"
                placeholder="Cartesia API Key..."
                value={cartesiaKey}
                onChange={(e) => setCartesiaKey(e.target.value)}
              />
            </div>
          )}

          {ttsProvider === 'eleven_labs' && (
            <div className="form-group">
              <label htmlFor="elevenLabsKey">ElevenLabs API Key</label>
              <input
                type="password"
                id="elevenLabsKey"
                placeholder="ElevenLabs API Key..."
                value={elevenLabsKey}
                onChange={(e) => setElevenLabsKey(e.target.value)}
              />
            </div>
          )}

          <div className="form-actions">
            <button type="submit" className="btn-primary">
              Save Settings
            </button>
            <button type="button" className="btn-secondary" onClick={handleTestChime}>
              Test Voice Audio
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
