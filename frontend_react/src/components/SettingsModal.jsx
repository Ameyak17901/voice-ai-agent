import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { apiGet } from '../api/client';

export default function SettingsModal({ isOpen, onClose, onSave, currentTts }) {
  const { isAuthenticated, user } = useAuth();
  const [openAiKey, setOpenAiKey] = useState('');
  const [deepgramKey, setDeepgramKey] = useState('');
  const [cartesiaKey, setCartesiaKey] = useState('');
  const [elevenLabsKey, setElevenLabsKey] = useState('');
  const [ttsProvider, setTtsProvider] = useState(currentTts || 'eleven_labs');
  const [loading, setLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState(null);

  // Load existing settings when modal opens
  useEffect(() => {
    if (!isOpen) {
      setSaveStatus(null);
      return;
    }

    const loadSettings = async () => {
      setLoading(true);
      try {
        const res = await apiGet('/api/settings');
        if (res.ok) {
          const data = await res.json();
          if (data.tts_provider) setTtsProvider(data.tts_provider);
          // Note: keys may be partially masked or present
          if (data.openai_api_key) setOpenAiKey(data.openai_api_key);
          if (data.deepgram_api_key) setDeepgramKey(data.deepgram_api_key);
          if (data.cartesia_api_key) setCartesiaKey(data.cartesia_api_key);
          if (data.eleven_labs_api_key) setElevenLabsKey(data.eleven_labs_api_key);
        }
      } catch (e) {
        console.error('Failed to load settings:', e);
      } finally {
        setLoading(false);
      }
    };

    loadSettings();
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaveStatus('Saving...');
    try {
      await onSave({
        openai_api_key: openAiKey || undefined,
        deepgram_api_key: deepgramKey || undefined,
        cartesia_api_key: cartesiaKey || undefined,
        eleven_labs_api_key: elevenLabsKey || undefined,
        tts_provider: ttsProvider,
      });
      setSaveStatus('Settings saved successfully!');
      setTimeout(() => {
        setSaveStatus(null);
        onClose();
      }, 1200);
    } catch (err) {
      setSaveStatus('Failed to save settings: ' + err.message);
    }
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
          <div>
            <h2>Service Settings & API Keys</h2>
            <div className="settings-scope-badge">
              {isAuthenticated ? (
                <span className="badge-user-active">Isolated to {user?.username}</span>
              ) : (
                <span className="badge-guest">Guest Mode (Ephemeral)</span>
              )}
            </div>
          </div>
          <button className="btn-icon" onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="20" height="20">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        {!isAuthenticated && (
          <div className="guest-banner">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            <span>You are currently in Guest Mode. Sign in to permanently persist personal API keys.</span>
          </div>
        )}

        <form className="drawer-body" onSubmit={handleSubmit}>
          {loading && <p className="loading-indicator">Loading your saved configuration...</p>}

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

          {saveStatus && (
            <div className={`save-status-msg ${saveStatus.includes('success') ? 'text-success' : 'text-info'}`}>
              {saveStatus}
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
