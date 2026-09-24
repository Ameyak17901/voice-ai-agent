import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import VisualizerCanvas from './components/VisualizerCanvas';
import VoiceOrb from './components/VoiceOrb';
import Controls from './components/Controls';
import QuickPrompts from './components/QuickPrompts';
import TranscriptFeed from './components/TranscriptFeed';
import DiagnosticsCard from './components/DiagnosticsCard';
import AgentBuilderModal from './components/AgentBuilderModal';
import { useVocodeVoice } from './hooks/useVocodeVoice';
import { API_BASE_URL } from './config';

export default function App() {
  const {
    isConnected,
    isConnecting,
    isSpeaking,
    isMuted,
    transcripts,
    interimTranscript,
    micAnalyser,
    playbackAnalyser,
    startSession,
    stopSession,
    toggleMute,
    clearTranscripts,
    sendManualMessage,
  } = useVocodeVoice();

  const [persona, setPersona] = useState('concierge');
  const [personas, setPersonas] = useState([]);
  const [isAgentBuilderOpen, setIsAgentBuilderOpen] = useState(false);
  const [systemStatus, setSystemStatus] = useState(null);

  // Fetch backend status
  const fetchStatus = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/status`);
      if (res.ok) {
        const data = await res.json();
        setSystemStatus(data);
        if (data.current_persona) setPersona(data.current_persona);
      }
    } catch (e) {
      console.error('Failed to fetch status:', e);
    }
  };

  // Fetch all personas (built-in + custom from agent_registry.json)
  const fetchPersonas = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/personas`);
      if (res.ok) {
        const data = await res.json();
        setPersonas(data);
      }
    } catch (e) {
      console.error('Failed to fetch personas:', e);
    }
  };

  useEffect(() => {
    fetchStatus();
    fetchPersonas();
  }, []);

  const handlePersonaChange = async (newPersona) => {
    setPersona(newPersona);
    try {
      await fetch(`${API_BASE_URL}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ default_persona: newPersona }),
      });
      fetchStatus();
    } catch (e) {
      console.error(e);
    }
  };

  const handleAgentCreated = (newAgent) => {
    setPersonas((prev) => {
      const filtered = prev.filter((p) => p.id !== newAgent.id);
      return [...filtered, newAgent];
    });
    setPersona(newAgent.id);
    fetchStatus();
  };

  const handleDeletePersona = async (personaId) => {
    if (!window.confirm('Are you sure you want to delete this custom agent?')) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/personas/${personaId}`, { method: 'DELETE' });
      if (res.ok) {
        setPersona('concierge');
        fetchPersonas();
        fetchStatus();
      } else {
        const err = await res.json();
        alert('Could not delete agent: ' + (err.detail || 'Unknown error'));
      }
    } catch (e) {
      alert('Failed to delete persona: ' + e.message);
    }
  };

  const activePersona = personas.find((p) => p.id === persona);

  const handleToggleSession = () => {
    if (isConnected) {
      stopSession();
    } else {
      startSession(persona);
    }
  };

  return (
    <div className="app-wrapper">
      <div className="ambient-glow glow-1"></div>
      <div className="ambient-glow glow-2"></div>
      <div className="ambient-glow glow-3"></div>

      <Header
        isConnected={isConnected}
        isConnecting={isConnecting}
        isSpeaking={isSpeaking}
        isHearingUser={Boolean(interimTranscript)}
      />

      <main className="main-layout">
        {/* Left Stage Section */}
        <section className="stage-section card-glass">
          <div className="visualizer-wrapper">
            <VisualizerCanvas
              isConnected={isConnected}
              isSpeaking={isSpeaking}
              micAnalyser={micAnalyser}
              playbackAnalyser={playbackAnalyser}
            />

            <VoiceOrb
              isConnected={isConnected}
              isSpeaking={isSpeaking}
              onClick={handleToggleSession}
            />
          </div>

          <Controls
            isConnected={isConnected}
            isConnecting={isConnecting}
            isMuted={isMuted}
            persona={persona}
            personas={personas}
            onPersonaChange={handlePersonaChange}
            onOpenAgentBuilder={() => setIsAgentBuilderOpen(true)}
            onDeletePersona={handleDeletePersona}
            onToggleSession={handleToggleSession}
            onToggleMute={toggleMute}
          />

          <QuickPrompts onSelectPrompt={sendManualMessage} />
        </section>

        {/* Right Sidebar Section */}
        <aside className="sidebar-section">
          <TranscriptFeed
            transcripts={transcripts}
            interimTranscript={interimTranscript}
            onClear={clearTranscripts}
            onSendMessage={sendManualMessage}
            activePersona={activePersona}
            personaName={activePersona?.name}
            personas={personas}
          />

          <DiagnosticsCard
            systemStatus={systemStatus}
            activePersona={activePersona}
          />
        </aside>
      </main>

      <AgentBuilderModal
        isOpen={isAgentBuilderOpen}
        onClose={() => setIsAgentBuilderOpen(false)}
        onAgentCreated={handleAgentCreated}
      />
    </div>
  );
}
