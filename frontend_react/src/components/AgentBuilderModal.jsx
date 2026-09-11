import React, { useState, useEffect } from 'react';

const EMOJI_OPTIONS = ['🤖', '🏥', '🦷', '🏡', '⚖️', '🚗', '✈️', '💻', '🩺', '🎓', '🏋️', '🛍️', '✨', '📞', '🎙️'];

const TEMPLATES = {
  dental: {
    name: 'Smile Dental Receptionist',
    icon: '🦷',
    voice_name: 'Sarah',
    description: 'Front-desk coordinator for dental checkups, cleanings, and emergencies.',
    initial_message: "Hello! Thank you for calling Smile Dental Care. Are you calling to book a routine cleaning or do you have a dental emergency today?",
    system_prompt: "You are the receptionist for Smile Dental Care. Your tone is calm, warm, and reassuring. Speak in 1-2 short conversational sentences. Inquire whether the caller is an existing or new patient, offer morning or afternoon slots, and answer basic questions about dental procedures. If it is an emergency, express empathy and prioritize immediate booking.",
  },
  real_estate: {
    name: 'Luxury Estates Advisor',
    icon: '🏡',
    voice_name: 'Charlotte',
    description: 'High-end property concierge for buyer inquiries and private home tours.',
    initial_message: "Welcome to Premier Real Estate. Are you interested in purchasing, selling, or booking a private walkthrough today?",
    system_prompt: "You are an upscale luxury real estate concierge. Speak with warmth, elegance, and clarity. Keep answers brief (1-2 sentences). Ask about desired location, bedroom count, and budget range, and offer to schedule a private walkthrough with a senior agent.",
  },
  tech_support: {
    name: 'Cloud Operations Support',
    icon: '💻',
    voice_name: 'Eric',
    description: 'Tier-1 IT specialist for diagnosing server and software connectivity issues.',
    initial_message: "NovaTech Support, Eric speaking. What technical issue or error code can I help you resolve today?",
    system_prompt: "You are a Tier-1 technical support engineer. You speak concisely and clearly with technical confidence. Ask clarifying diagnostic questions one at a time. Guide the user through simple verification steps and reassure them that their ticket is actively tracked.",
  },
  personal_trainer: {
    name: 'Coach Marcus — Fitness Guide',
    icon: '🏋️',
    voice_name: 'Roger',
    description: 'High-energy fitness and nutrition coach for habit tracking and motivation.',
    initial_message: "Hey there! Coach Marcus here. Ready to crush today's workout or plan your weekly meal goals?",
    system_prompt: "You are Coach Marcus, a motivating, friendly fitness and wellness coach. Keep responses punchy and inspiring (1-2 sentences). Ask about their current fitness goals, encourage healthy habits, and keep the energy positive and direct.",
  }
};

export default function AgentBuilderModal({ isOpen, onClose, onAgentCreated }) {
  const [voices, setVoices] = useState([]);
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [icon, setIcon] = useState('🤖');
  const [description, setDescription] = useState('');
  const [voiceId, setVoiceId] = useState('');
  const [voiceName, setVoiceName] = useState('Jessica');
  const [initialMessage, setInitialMessage] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [idleTimeout, setIdleTimeout] = useState(12.0);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [idleMsg1, setIdleMsg1] = useState("I'm still here whenever you're ready. What can I help you with?");
  const [idleMsg2, setIdleMsg2] = useState("Just checking in—are you still with me? Let me know if you can hear me.");
  const [idleGoodbye, setIdleGoodbye] = useState("It seems we might have disconnected. Feel free to call back anytime. Goodbye!");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // Fetch available voices on open
  useEffect(() => {
    if (isOpen) {
      fetch('/api/voices')
        .then(res => res.json())
        .then(data => {
          setVoices(data);
          if (data.length > 0 && !voiceId) {
            setVoiceId(data[0].voice_id);
            setVoiceName(data[0].name);
          }
        })
        .catch(err => console.error('Failed to load voices:', err));
    }
  }, [isOpen]);

  if (!isOpen) return null;

  // Auto-generate slug from name
  const handleNameChange = (e) => {
    const val = e.target.value;
    setName(val);
    const autoSlug = val.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    setSlug(autoSlug);
  };

  const handleApplyTemplate = (key) => {
    const t = TEMPLATES[key];
    if (!t) return;
    setName(t.name);
    setSlug(t.name.toLowerCase().replace(/[^a-z0-9]+/g, '_'));
    setIcon(t.icon);
    setDescription(t.description);
    setInitialMessage(t.initial_message);
    setSystemPrompt(t.system_prompt);

    const matchedVoice = voices.find(v => v.name.toLowerCase() === t.voice_name.toLowerCase());
    if (matchedVoice) {
      setVoiceId(matchedVoice.voice_id);
      setVoiceName(matchedVoice.name);
    }
  };

  const handleVoiceChange = (e) => {
    const vId = e.target.value;
    setVoiceId(vId);
    const v = voices.find(item => item.voice_id === vId);
    if (v) setVoiceName(v.name);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');

    if (!name.trim()) {
      setErrorMsg('Please enter a display name for the agent.');
      return;
    }
    if (!slug.trim()) {
      setErrorMsg('Please enter a valid unique slug identifier.');
      return;
    }
    if (!initialMessage.trim()) {
      setErrorMsg('Please enter an initial spoken greeting message.');
      return;
    }
    if (!systemPrompt.trim()) {
      setErrorMsg('Please provide system instructions/prompt.');
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = {
        id: slug,
        name: name.trim(),
        icon: icon || '🤖',
        description: description.trim(),
        system_prompt: systemPrompt.trim(),
        initial_message: initialMessage.trim(),
        voice_id: voiceId || 'cgSgspJ2msm6clMCkdW9',
        voice_name: voiceName || 'Jessica',
        model_name: 'gemini-3.5-flash-lite',
        temperature: 0.7,
        idle_nudge_timeout: parseFloat(idleTimeout) || 12.0,
        idle_messages: [idleMsg1, idleMsg2].filter(Boolean),
        idle_goodbye_message: idleGoodbye,
        is_custom: true,
      };

      const res = await fetch('/api/personas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to create persona');
      }

      onAgentCreated(data.persona);
      onClose();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div 
        className="drawer-panel card-glass custom-agent-modal" 
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: '680px', width: '95%', maxHeight: '90vh', overflowY: 'auto' }}
      >
        <div className="drawer-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '1.5rem' }}>{icon}</span>
            <div>
              <h2 style={{ margin: 0, fontSize: '1.25rem' }}>Create Custom AI Voice Agent</h2>
              <small style={{ color: 'var(--text-muted)' }}>Configure persona, voice, and system instructions</small>
            </div>
          </div>
          <button className="btn-icon" onClick={onClose} title="Close">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="20" height="20">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        {/* Quick Template Picker */}
        <div style={{ padding: '0 24px 16px 24px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '8px' }}>
            ⚡ Or start from a ready-to-use template:
          </label>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button type="button" className="btn-chip" onClick={() => handleApplyTemplate('dental')}>
              🦷 Dental Clinic
            </button>
            <button type="button" className="btn-chip" onClick={() => handleApplyTemplate('real_estate')}>
              🏡 Luxury Real Estate
            </button>
            <button type="button" className="btn-chip" onClick={() => handleApplyTemplate('tech_support')}>
              💻 Cloud IT Support
            </button>
            <button type="button" className="btn-chip" onClick={() => handleApplyTemplate('personal_trainer')}>
              🏋️ Fitness Coach
            </button>
          </div>
        </div>

        <form className="drawer-body" onSubmit={handleSubmit} style={{ padding: '20px 24px' }}>
          {errorMsg && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.15)',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              color: '#fca5a5',
              padding: '10px 14px',
              borderRadius: '8px',
              marginBottom: '16px',
              fontSize: '0.875rem'
            }}>
              ⚠️ {errorMsg}
            </div>
          )}

          {/* Row: Name & Icon */}
          <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
            <div className="form-group" style={{ flex: '0 0 80px' }}>
              <label htmlFor="agentIcon">Icon</label>
              <select
                id="agentIcon"
                value={icon}
                onChange={(e) => setIcon(e.target.value)}
                style={{ fontSize: '1.25rem', textAlign: 'center', height: '42px' }}
              >
                {EMOJI_OPTIONS.map(em => (
                  <option key={em} value={em}>{em}</option>
                ))}
              </select>
            </div>

            <div className="form-group" style={{ flex: 1 }}>
              <label htmlFor="agentName">Agent Display Name *</label>
              <input
                type="text"
                id="agentName"
                placeholder="e.g. Maya — Pediatric Dental Coordinator"
                value={name}
                onChange={handleNameChange}
                required
              />
            </div>
          </div>

          {/* Row: Slug ID & Voice Selection */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div className="form-group">
              <label htmlFor="agentSlug">Unique Identifier (Slug) *</label>
              <input
                type="text"
                id="agentSlug"
                placeholder="e.g. pediatric_dental"
                value={slug}
                onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                required
              />
              <small>Used for WebSocket URL: ?persona={slug || '...'}</small>
            </div>

            <div className="form-group">
              <label htmlFor="voiceSelect">ElevenLabs Voice Model</label>
              <select id="voiceSelect" value={voiceId} onChange={handleVoiceChange}>
                {voices.map(v => (
                  <option key={v.voice_id} value={v.voice_id}>
                    {v.name} ({v.gender}) — {v.description.slice(0, 32)}...
                  </option>
                ))}
              </select>
              <small>Studio Quality Linear16 PCM Streaming</small>
            </div>
          </div>

          {/* Opening Greeting */}
          <div className="form-group">
            <label htmlFor="initialMsg">Opening Spoken Greeting *</label>
            <input
              type="text"
              id="initialMsg"
              placeholder="e.g. Hello! Thanks for calling Nova Health. How can I assist you today?"
              value={initialMessage}
              onChange={(e) => setInitialMessage(e.target.value)}
              required
            />
            <small>The very first sentence the agent will speak out loud when connected.</small>
          </div>

          {/* System Instructions / Prompt */}
          <div className="form-group">
            <label htmlFor="sysPrompt">System Instructions & Speaking Persona *</label>
            <textarea
              id="sysPrompt"
              rows={4}
              placeholder="You are an ultra-responsive voice assistant. Speak naturally in 1-2 short sentences. Answer questions about..."
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              required
              style={{
                width: '100%',
                background: 'rgba(0, 0, 0, 0.25)',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: '8px',
                color: '#fff',
                padding: '10px 12px',
                fontFamily: 'inherit',
                fontSize: '0.875rem',
                resize: 'vertical'
              }}
            />
            <small>Directs how the LLM answers. Keep responses concise for spoken natural audio.</small>
          </div>

          {/* Collapsible Advanced Idle Watchdog Settings */}
          <div style={{ marginTop: '8px', marginBottom: '16px' }}>
            <button
              type="button"
              onClick={() => setShowAdvanced(prev => !prev)}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--primary-glow)',
                cursor: 'pointer',
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: 0
              }}
            >
              <span>{showAdvanced ? '▼ Hide' : '▶ Show'} Advanced Watchdog & Idle Settings</span>
            </button>

            {showAdvanced && (
              <div style={{
                marginTop: '12px',
                padding: '14px',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.06)'
              }}>
                <div className="form-group">
                  <label>Idle Silence Nudge Threshold: {idleTimeout}s</label>
                  <input
                    type="range"
                    min="6"
                    max="30"
                    step="1"
                    value={idleTimeout}
                    onChange={(e) => setIdleTimeout(e.target.value)}
                    style={{ width: '100%' }}
                  />
                  <small>Agent gently checks in if human goes silent for this duration.</small>
                </div>

                <div className="form-group">
                  <label>First Silence Check-in</label>
                  <input
                    type="text"
                    value={idleMsg1}
                    onChange={(e) => setIdleMsg1(e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label>Second Silence Check-in</label>
                  <input
                    type="text"
                    value={idleMsg2}
                    onChange={(e) => setIdleMsg2(e.target.value)}
                  />
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Disconnect Goodbye Phrase</label>
                  <input
                    type="text"
                    value={idleGoodbye}
                    onChange={(e) => setIdleGoodbye(e.target.value)}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '16px' }}>
            <button type="button" className="btn-secondary" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={isSubmitting}>
              {isSubmitting ? 'Saving Agent...' : 'Save & Select Persona'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
