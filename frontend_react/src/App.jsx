import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import VisualizerCanvas from './components/VisualizerCanvas';
import VoiceOrb from './components/VoiceOrb';
import Controls from './components/Controls';
import QuickPrompts from './components/QuickPrompts';
import TranscriptFeed from './components/TranscriptFeed';
import DiagnosticsCard from './components/DiagnosticsCard';
import SettingsModal from './components/SettingsModal';
import AgentBuilderModal from './components/AgentBuilderModal';
import { useVocodeVoice } from './hooks/useVocodeVoice';

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
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isAgentBuilderOpen, setIsAgentBuilderOpen] = useState(false);
  const [systemStatus, setSystemStatus] = useState(null);
  const [appointmentsCount, setAppointmentsCount] = useState(0);

  // Fetch backend status
  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const data = await res.json();
        setSystemStatus(data);
        if (data.current_persona) setPersona(data.current_persona);
      }

      const apptRes = await fetch('/api/appointments');
      if (apptRes.ok) {
        const apptData = await apptRes.json();
        setAppointmentsCount(apptData.appointments?.length || 0);
      }
    } catch (e) {
      console.error('Failed to fetch status:', e);
    }
  };

  // Fetch all personas (built-in + custom from agent_registry.json)
  const fetchPersonas = async () => {
    try {
      const res = await fetch('/api/personas');
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
      await fetch('/api/settings', {
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
      const res = await fetch(`/api/personas/${personaId}`, { method: 'DELETE' });
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

  const handleSaveSettings = async (payload) => {
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        alert('Settings saved successfully!');
        setIsSettingsOpen(false);
        fetchStatus();
      }
    } catch (err) {
      alert('Failed to save settings: ' + err.message);
    }
  };

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
        onOpenSettings={() => setIsSettingsOpen(true)}
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
          />

          <DiagnosticsCard
            systemStatus={systemStatus}
            appointmentsCount={appointmentsCount}
          />
        </aside>
      </main>

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        onSave={handleSaveSettings}
        currentTts={systemStatus?.tts_provider}
      />

      <AgentBuilderModal
        isOpen={isAgentBuilderOpen}
        onClose={() => setIsAgentBuilderOpen(false)}
        onAgentCreated={handleAgentCreated}
      />
    </div>
  );
}
