import React from 'react';

export default function VoiceOrb({ isConnected, isSpeaking, onClick }) {
  let orbClass = 'voice-orb idle';
  if (isSpeaking) {
    orbClass = 'voice-orb speaking';
  } else if (isConnected) {
    orbClass = 'voice-orb active';
  }

  return (
    <div className={orbClass} onClick={onClick} title={isConnected ? 'Click to end session' : 'Click to start session'}>
      <div className="orb-core">
        {isConnected ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="36" height="36">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="36" height="36">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
        )}
      </div>
      <div className="orb-ring ring-1"></div>
      <div className="orb-ring ring-2"></div>
      <div className="orb-ring ring-3"></div>
    </div>
  );
}
