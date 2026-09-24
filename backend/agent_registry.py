import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger
from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).parent / "data"
REGISTRY_FILE = DATA_DIR / "agent_registry.json"


class VoicePreset(BaseModel):
    """Voice metadata for selection in UI."""
    voice_id: str
    name: str
    gender: str
    description: str


DEFAULT_VOICE_PRESETS: List[VoicePreset] = [
    VoicePreset(voice_id="cgSgspJ2msm6clMCkdW9", name="Jessica", gender="Female", description="Bright, playful, warm concierge"),
    VoicePreset(voice_id="EXAVITQu4vr4xnSDxMaL", name="Sarah", gender="Female", description="Reassuring, empathetic medical receptionist"),
    VoicePreset(voice_id="cjVigY5qzO86Huf0OWal", name="Eric", gender="Male", description="Smooth, technical, professional interviewer"),
    VoicePreset(voice_id="XrExE9yKIg1WjnnlVkGX", name="Matilda", gender="Female", description="Articulate, patient, calm school administrator"),
    VoicePreset(voice_id="pNInz6obpgDQGcFmaJgB", name="Adam", gender="Male", description="Deep, authoritative, confident narrator"),
    VoicePreset(voice_id="CwhRBWXzGAHq8TQ4Fs17", name="Roger", gender="Male", description="Casual, relatable, easygoing assistant"),
    VoicePreset(voice_id="XB0fDUnXU5powFXDhCwa", name="Charlotte", gender="Female", description="Elegant, articulate, refined voice"),
    VoicePreset(voice_id="Xb7hH8MSUJpSbSDYk0k2", name="Alice", gender="Female", description="Clear, upbeat, modern corporate voice"),
    VoicePreset(voice_id="JBFqnCBsd6RMkjVDRZzb", name="George", gender="Male", description="Warm, mature, approachable counselor"),
]


class VoicePersona(BaseModel):
    """Complete schema for a real-time Voice AI Persona."""
    id: str = Field(..., description="Unique slug identifier (e.g. dental_receptionist)")
    name: str = Field(..., description="Display title for UI (e.g. Chloe — Medical Receptionist)")
    icon: str = Field(default="🤖", description="Emoji or UI badge icon")
    description: str = Field(default="", description="Short functional summary")
    system_prompt: str = Field(..., description="LLM system instruction preamble")
    initial_message: str = Field(..., description="Spoken greeting when call starts")
    voice_id: str = Field(default="cgSgspJ2msm6clMCkdW9", description="ElevenLabs voice ID")
    voice_name: Optional[str] = Field(default="Jessica", description="Readable voice name")
    model_name: str = Field(default="gemini-3.5-flash", description="LLM model identifier")
    temperature: float = Field(default=0.7, ge=0.0, le=1.5)
    idle_nudge_timeout: float = Field(default=12.0, ge=4.0, le=60.0)
    idle_messages: List[str] = Field(
        default_factory=lambda: [
            "I'm still here whenever you're ready. How can I assist you?",
            "Just checking in—are you still with me? Let me know if you can hear me."
        ]
    )
    idle_goodbye_message: str = Field(
        default="I haven't heard back for a while, so I will end this call for now. Feel free to call back anytime. Goodbye!"
    )
    is_custom: bool = Field(default=True, description="False for factory built-in presets")
    created_at: float = Field(default_factory=time.time)


BUILTIN_PERSONAS: Dict[str, VoicePersona] = {
    "concierge": VoicePersona(
        id="concierge",
        name="Nova — Executive Concierge",
        icon="✨",
        description="Ultra-responsive, friendly AI voice copilot for general concierge and appointment assistance.",
        system_prompt=(
            "You are Nova, an ultra-responsive, friendly AI voice assistant. "
            "Keep your responses concise, conversational, and direct (1 to 2 sentences max) "
            "because your responses are spoken out loud. Avoid bullet points or lists. "
            "You can help schedule appointments, answer questions about NovaVoice systems, "
            "and provide polite assistance."
        ),
        initial_message="Hello! I'm Nova, your real-time voice copilot. How can I assist you today?",
        voice_id="cgSgspJ2msm6clMCkdW9",
        voice_name="Jessica",
        model_name="gemini-3.5-flash",
        temperature=0.7,
        idle_nudge_timeout=12.0,
        idle_messages=[
            "I'm here whenever you're ready. What can I help you with today?",
            "Just checking in—are you still with me? Let me know if you can hear me.",
        ],
        idle_goodbye_message="It seems we might be disconnected. I'll hang up for now. Feel free to reach out anytime. Goodbye!",
        is_custom=False,
    ),
    "receptionist": VoicePersona(
        id="receptionist",
        name="Chloe — Medical Receptionist",
        icon="🏥",
        description="Warm, empathetic front-desk receptionist for Nova Medical & Wellness Clinic.",
        system_prompt=(
            "You are Chloe, the front-desk voice receptionist for Nova Medical & Wellness Clinic. "
            "Your tone is warm, professional, and empathetic. "
            "Speak naturally in short sentences. Inquire about how you can help, offer available "
            "appointment times, and confirm patient bookings efficiently."
        ),
        initial_message="Hello! I'm Chloe, your voice receptionist. How can I help you today?",
        voice_id="EXAVITQu4vr4xnSDxMaL",
        voice_name="Sarah",
        model_name="gemini-3.5-flash",
        temperature=0.7,
        idle_nudge_timeout=12.0,
        idle_messages=[
            "Take your time. Were you looking to book an appointment or check clinic hours?",
            "Are you still on the line? Just let me know if you can hear me okay.",
        ],
        idle_goodbye_message="I haven't heard back for a while, so I will end this call. Please call Nova Medical Clinic back anytime. Take care!",
        is_custom=False,
    ),
    "tech_screener": VoicePersona(
        id="tech_screener",
        name="Alex — Technical Interviewer",
        icon="💻",
        description="Rigorous and clear technical interviewer evaluating software engineering fundamentals.",
        system_prompt=(
            "You are Alex, an engineering interviewer assistant. "
            "You ask crisp, relevant software engineering questions, evaluate candidate reasoning, "
            "and converse naturally with audio brevity."
        ),
        initial_message="Hello! I'm Alex, your engineering interviewer assistant. How can I help you today?",
        voice_id="cjVigY5qzO86Huf0OWal",
        voice_name="Eric",
        model_name="gemini-3.5-flash",
        temperature=0.6,
        idle_nudge_timeout=14.0,
        idle_messages=[
            "Feel free to think aloud as you work through that technical question.",
            "Still there? Let me know if you'd like me to clarify anything.",
        ],
        idle_goodbye_message="Looks like we lost connection. Your responses so far have been saved. Thanks for your time today!",
        is_custom=False,
    ),
    "school_receptionist": VoicePersona(
        id="school_receptionist",
        name="Mary — School Receptionist",
        icon="🏫",
        description="Patient and articulate school front-desk receptionist for parent and student queries.",
        system_prompt=(
            "You are the school receptionist. "
            "Your tone is warm, professional, and empathetic. "
            "Speak naturally in short sentences. Inquire about how you can help, offer available "
            "appointment times, and confirm patient bookings efficiently."
        ),
        initial_message="Hello! I'm the school receptionist. How can I help you today?",
        voice_id="XrExE9yKIg1WjnnlVkGX",
        voice_name="Matilda",
        model_name="gemini-3.5-flash",
        temperature=0.7,
        idle_nudge_timeout=12.0,
        idle_messages=[
            "I'm still here. How may I assist you or your student today?",
            "Hello, are you still there? Please let me know if you can hear me.",
        ],
        idle_goodbye_message="I haven't heard back, so I will disconnect for now. Feel free to call the main school office back anytime. Goodbye!",
        is_custom=False,
    ),
}


class AgentRegistry:
    """Thread-safe, atomic file-backed registry for Voice AI personas."""

    def __init__(self, storage_path: Path = REGISTRY_FILE):
        self.storage_path = storage_path
        self._custom_personas: Dict[str, VoicePersona] = {}
        self._ensure_storage_dir()
        self._load_from_disk()

    def _ensure_storage_dir(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_from_disk(self) -> None:
        """Loads custom personas from agent_registry.json."""
        if not self.storage_path.exists():
            self._save_to_disk()
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                loaded: Dict[str, VoicePersona] = {}
                for item in raw_data:
                    persona = VoicePersona.model_validate(item)
                    loaded[persona.id] = persona
                self._custom_personas = loaded
                logger.info(f"Loaded {len(self._custom_personas)} custom personas from {self.storage_path.name}")
        except Exception as e:
            logger.error(f"Error loading {self.storage_path}: {e}. Initializing empty custom personas.", exc_info=True)
            self._custom_personas = {}

    def _save_to_disk(self) -> None:
        """Performs an atomic write to agent_registry.json using os.replace."""
        temp_path = self.storage_path.with_suffix(".tmp")
        try:
            data = [p.model_dump() for p in self._custom_personas.values()]
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, self.storage_path)
        except Exception as e:
            logger.error(f"Failed to atomically persist {self.storage_path}: {e}", exc_info=True)
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise

    def get_all_personas(self) -> List[VoicePersona]:
        """Returns all built-in and custom personas merged together."""
        merged: List[VoicePersona] = list(BUILTIN_PERSONAS.values())
        merged.extend(self._custom_personas.values())
        return merged

    def get_persona(self, persona_id: Optional[str]) -> Optional[VoicePersona]:
        """Look up a persona by ID from built-ins or custom."""
        if not persona_id:
            return BUILTIN_PERSONAS.get("concierge")
        if persona_id in self._custom_personas:
            return self._custom_personas[persona_id]
        if persona_id in BUILTIN_PERSONAS:
            return BUILTIN_PERSONAS[persona_id]
        return None

    def save_custom_persona(self, persona: VoicePersona) -> VoicePersona:
        """Saves or updates a custom persona."""
        persona_id = persona.id.strip().lower().replace(" ", "_")
        if persona_id in BUILTIN_PERSONAS:
            raise ValueError(f"Cannot overwrite factory built-in persona: '{persona_id}'")

        persona.id = persona_id
        persona.is_custom = True
        self._custom_personas[persona_id] = persona
        self._save_to_disk()
        logger.info(f"Successfully saved custom persona: '{persona.name}' (id: {persona_id})")
        return persona

    def delete_custom_persona(self, persona_id: str) -> bool:
        """Deletes a custom persona by ID. Built-ins cannot be deleted."""
        clean_id = persona_id.strip().lower()
        if clean_id in BUILTIN_PERSONAS:
            raise ValueError("Built-in personas cannot be deleted.")
        if clean_id in self._custom_personas:
            del self._custom_personas[clean_id]
            self._save_to_disk()
            logger.info(f"Successfully deleted custom persona: '{clean_id}'")
            return True
        return False

    def get_voice_presets(self) -> List[VoicePreset]:
        """Returns available ElevenLabs voice presets for the UI."""
        return DEFAULT_VOICE_PRESETS


agent_registry = AgentRegistry()
