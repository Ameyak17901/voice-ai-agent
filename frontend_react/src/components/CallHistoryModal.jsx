import React, { useState, useEffect } from 'react';
import { apiGet } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function CallHistoryModal({ isOpen, onClose }) {
  const { isAuthenticated } = useAuth();
  const [calls, setCalls] = useState([]);
  const [selectedCall, setSelectedCall] = useState(null);
  const [transcripts, setTranscripts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isOpen || !isAuthenticated) return;

    const fetchCalls = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await apiGet('/api/calls');
        if (res.ok) {
          const data = await res.json();
          setCalls(data);
          if (data.length > 0) {
            handleSelectCall(data[0]);
          }
        } else {
          setError('Failed to load call history.');
        }
      } catch (e) {
        setError(e.message || 'Error fetching calls.');
      } finally {
        setLoading(false);
      }
    };

    fetchCalls();
  }, [isOpen, isAuthenticated]);

  const handleSelectCall = async (call) => {
    setSelectedCall(call);
    setDetailLoading(true);
    try {
      const res = await apiGet(`/api/calls/${call.id}`);
      if (res.ok) {
        const detail = await res.json();
        setTranscripts(detail.transcripts || []);
      } else {
        setTranscripts([]);
      }
    } catch {
      setTranscripts([]);
    } finally {
      setDetailLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="call-history-panel card-glass" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div className="history-header-title">
            <h2>Call History & Transcripts</h2>
            <span className="badge-user-scope">User Scope</span>
          </div>
          <button className="btn-icon" onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="20" height="20">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        {!isAuthenticated ? (
          <div className="history-empty-state">
            <p>Please sign in to view your saved voice sessions and transcripts.</p>
          </div>
        ) : loading ? (
          <div className="history-empty-state">
            <p>Loading your call history...</p>
          </div>
        ) : error ? (
          <div className="history-empty-state">
            <p style={{ color: '#ef4444' }}>{error}</p>
          </div>
        ) : calls.length === 0 ? (
          <div className="history-empty-state">
            <p>No call sessions found yet. Start a conversation with an agent!</p>
          </div>
        ) : (
          <div className="call-history-body">
            {/* Left side: list of calls */}
            <div className="call-list-column">
              {calls.map((call) => {
                const isSelected = selectedCall?.id === call.id;
                const formattedDate = new Date(call.created_at).toLocaleString([], {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                });

                return (
                  <div
                    key={call.id}
                    className={`call-list-item ${isSelected ? 'active' : ''}`}
                    onClick={() => handleSelectCall(call)}
                  >
                    <div className="call-item-header">
                      <span className="call-persona-tag">{call.persona_id || 'concierge'}</span>
                      <span className="call-date-tag">{formattedDate}</span>
                    </div>
                    <div className="call-item-session">
                      <code>{call.session_id}</code>
                    </div>
                    <div className="call-item-footer">
                      <span className={`status-badge status-${call.status}`}>
                        {call.status}
                      </span>
                      {call.duration_seconds > 0 && (
                        <span className="call-duration">{call.duration_seconds}s</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Right side: transcript detail */}
            <div className="call-detail-column">
              {selectedCall ? (
                <>
                  <div className="call-detail-meta">
                    <h4>Session: {selectedCall.session_id}</h4>
                    <p>Persona: <strong>{selectedCall.persona_id}</strong> | Status: <strong>{selectedCall.status}</strong></p>
                  </div>

                  <div className="call-transcript-container">
                    {detailLoading ? (
                      <p className="loading-transcript">Loading transcripts...</p>
                    ) : transcripts.length === 0 ? (
                      <p className="no-transcript">No transcript items logged for this session.</p>
                    ) : (
                      transcripts.map((t) => (
                        <div key={t.id} className={`transcript-bubble bubble-${t.sender.toLowerCase()}`}>
                          <div className="bubble-sender">{t.sender === 'user' ? 'You' : 'Agent'}</div>
                          <div className="bubble-text">{t.text}</div>
                        </div>
                      ))
                    )}
                  </div>
                </>
              ) : (
                <div className="history-empty-state">
                  <p>Select a call from the list to view its full transcript.</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
