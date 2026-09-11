import React from 'react';

const PROMPTS = [
  { label: '"Who are you?"', text: "Hello! Who are you and how can you help me?" },
  { label: '"Check availability"', text: "What appointment slots do you have available today?" },
  { label: '"Book appointment"', text: "I would like to book an appointment for tomorrow morning." },
  { label: '"Company services"', text: "Tell me about NovaVoice AI services." },
];

export default function QuickPrompts({ onSelectPrompt }) {
  return (
    <div className="quick-prompts">
      <span className="prompt-hint">Try saying:</span>
      {PROMPTS.map((p, i) => (
        <button
          key={i}
          className="chip-prompt"
          onClick={() => onSelectPrompt(p.text)}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
