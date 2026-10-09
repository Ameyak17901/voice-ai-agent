import datetime
import json
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from backend.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(64), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relationships
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    calls = relationship("CallSession", back_populates="user", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="user", cascade="all, delete-orphan")
    personas = relationship("CustomPersona", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "settings": self.settings.to_dict() if self.settings else None,
        }


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True, nullable=False)

    # Scoped AI Credentials
    openai_api_key = Column(String(255), nullable=True)
    gemini_api_key = Column(String(255), nullable=True)
    deepgram_api_key = Column(String(255), nullable=True)
    eleven_labs_api_key = Column(String(255), nullable=True)

    # Scoped Preferences
    eleven_labs_voice_id = Column(String(64), default="EXAVITQu4vr4xnSDxMaL", nullable=False)
    tts_provider = Column(String(32), default="eleven_labs", nullable=False)
    default_persona = Column(String(64), default="concierge", nullable=False)
    openai_model_name = Column(String(64), default="gemini-1.5-flash", nullable=False)
    openai_base_url = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="settings")

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "has_openai_key": bool(self.openai_api_key),
            "has_gemini_key": bool(self.gemini_api_key),
            "has_deepgram_key": bool(self.deepgram_api_key),
            "has_eleven_labs_key": bool(self.eleven_labs_api_key),
            "eleven_labs_voice_id": self.eleven_labs_voice_id,
            "tts_provider": self.tts_provider,
            "default_persona": self.default_persona,
            "openai_model_name": self.openai_model_name,
            "openai_base_url": self.openai_base_url,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CustomPersona(Base):
    __tablename__ = "custom_personas"

    id = Column(String(64), primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)  # NULL for global/system presets
    name = Column(String(128), nullable=False)
    icon = Column(String(16), default="🤖")
    description = Column(Text, default="")
    system_prompt = Column(Text, nullable=False)
    initial_message = Column(Text, nullable=False)
    voice_id = Column(String(64), default="cgSgspJ2msm6clMCkdW9")
    voice_name = Column(String(64), default="Jessica")
    model_name = Column(String(64), default="gemini-1.5-flash")
    temperature = Column(Float, default=0.7)
    idle_nudge_timeout = Column(Float, default=12.0)
    idle_messages_json = Column(Text, nullable=True)
    idle_goodbye_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="personas")

    def to_dict(self):
        idle_msgs = []
        if self.idle_messages_json:
            try:
                idle_msgs = json.loads(self.idle_messages_json)
            except Exception:
                pass
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "icon": self.icon,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "initial_message": self.initial_message,
            "voice_id": self.voice_id,
            "voice_name": self.voice_name,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "idle_nudge_timeout": self.idle_nudge_timeout,
            "idle_messages": idle_msgs,
            "idle_goodbye_message": self.idle_goodbye_message,
            "is_custom": True,
            "created_at": self.created_at.timestamp() if self.created_at else None,
        }


class CallSession(Base):
    __tablename__ = "call_sessions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    conversation_id = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    persona = Column(String(64), default="concierge", nullable=False)
    status = Column(String(32), default="active", nullable=False)  # active, completed, disconnected, error
    start_time = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0)
    summary = Column(Text, nullable=True)
    sentiment = Column(String(32), nullable=True)
    audio_chunks_count = Column(Integer, default=0)
    total_audio_bytes = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="calls")
    transcripts = relationship("TranscriptItem", back_populates="session", cascade="all, delete-orphan", order_by="TranscriptItem.timestamp")
    appointments = relationship("Appointment", back_populates="session")

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "persona": self.persona,
            "status": self.status,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "summary": self.summary,
            "sentiment": self.sentiment,
            "audio_chunks_count": self.audio_chunks_count,
            "total_audio_bytes": self.total_audio_bytes,
            "transcript_count": len(self.transcripts) if self.transcripts else 0,
        }


class TranscriptItem(Base):
    __tablename__ = "transcript_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    conversation_id = Column(String(64), index=True, nullable=False)
    session_id = Column(Integer, ForeignKey("call_sessions.id"), nullable=True)
    sender = Column(String(16), nullable=False)  # human, bot, tool, system
    text = Column(Text, nullable=False)
    latency_ms = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    session = relationship("CallSession", back_populates="transcripts")

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender": self.sender,
            "text": self.text,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(String(32), primary_key=True, index=True)  # APPT-101
    conversation_id = Column(String(64), index=True, nullable=True)
    session_id = Column(Integer, ForeignKey("call_sessions.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    name = Column(String(128), nullable=False)
    date = Column(String(64), nullable=False)
    time = Column(String(32), nullable=False)
    service = Column(String(128), default="General Consultation", nullable=False)
    status = Column(String(32), default="confirmed", nullable=False)  # confirmed, cancelled, rescheduled
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="appointments")
    session = relationship("CallSession", back_populates="appointments")

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "name": self.name,
            "date": self.date,
            "time": self.time,
            "service": self.service,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
