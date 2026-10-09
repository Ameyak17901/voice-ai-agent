import datetime
import json
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_
from loguru import logger

from backend.db.database import SessionLocal, init_db
from backend.db.models import User, UserSettings, CustomPersona, CallSession, TranscriptItem, Appointment

# Ensure tables exist
init_db()


class DBRepository:
    """Thread-safe transactional repository with multi-user isolation."""

    # ==========================================
    # 1. User & Authentication Methods
    # ==========================================
    @staticmethod
    def create_user(email: str, username: str, plain_password: str) -> Dict[str, Any]:
        """Creates a new user with a hashed password and default settings."""
        from backend.auth import hash_password
        with SessionLocal() as db:
            clean_email = email.strip().lower()
            clean_username = username.strip().lower()
            existing = db.query(User).filter(
                or_(User.email == clean_email, User.username == clean_username)
            ).first()
            if existing:
                if existing.email == clean_email:
                    raise ValueError(f"Email '{clean_email}' is already registered.")
                raise ValueError(f"Username '{clean_username}' is already taken.")

            user = User(
                email=clean_email,
                username=clean_username,
                hashed_password=hash_password(plain_password),
                is_active=True,
                created_at=datetime.datetime.utcnow(),
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # Initialize empty user settings
            settings = UserSettings(
                user_id=user.id,
                created_at=datetime.datetime.utcnow(),
                updated_at=datetime.datetime.utcnow(),
            )
            db.add(settings)
            db.commit()

            return user.to_dict()

    @staticmethod
    def authenticate_user(email_or_username: str, plain_password: str) -> Optional[Dict[str, Any]]:
        """Verifies candidate credentials against stored salted hash."""
        from backend.auth import verify_password
        with SessionLocal() as db:
            query_val = email_or_username.strip().lower()
            user = db.query(User).filter(
                or_(User.email == query_val, User.username == query_val)
            ).first()
            if not user or not user.is_active:
                return None
            if not verify_password(plain_password, user.hashed_password):
                return None
            return user.to_dict()

    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            return user.to_dict() if user else None

    @staticmethod
    def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email.strip().lower()).first()
            return user.to_dict() if user else None

    @staticmethod
    def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
        with SessionLocal() as db:
            user = db.query(User).filter(User.username == username.strip().lower()).first()
            return user.to_dict() if user else None

    # ==========================================
    # 2. User-Specific Settings
    # ==========================================
    @staticmethod
    def get_user_settings(user_id: int) -> Dict[str, Any]:
        """Returns safe user preferences for UI presentation."""
        with SessionLocal() as db:
            s = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
            if not s:
                s = UserSettings(user_id=user_id)
                db.add(s)
                db.commit()
                db.refresh(s)
            return s.to_dict()

    @staticmethod
    def get_user_credentials(user_id: Optional[int]) -> Dict[str, Any]:
        """Returns raw credentials for runtime agent construction (internal use only)."""
        if not user_id:
            return {}
        with SessionLocal() as db:
            s = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
            if not s:
                return {}
            return {
                "openai_api_key": s.openai_api_key,
                "gemini_api_key": s.gemini_api_key,
                "deepgram_api_key": s.deepgram_api_key,
                "eleven_labs_api_key": s.eleven_labs_api_key,
                "eleven_labs_voice_id": s.eleven_labs_voice_id,
                "tts_provider": s.tts_provider,
                "default_persona": s.default_persona,
                "openai_model_name": s.openai_model_name,
                "openai_base_url": s.openai_base_url,
            }

    @staticmethod
    def update_user_settings(user_id: int, **kwargs) -> Dict[str, Any]:
        """Updates private user settings without modifying any global process state."""
        with SessionLocal() as db:
            s = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
            if not s:
                s = UserSettings(user_id=user_id)
                db.add(s)

            allowed_fields = [
                "openai_api_key",
                "gemini_api_key",
                "deepgram_api_key",
                "eleven_labs_api_key",
                "eleven_labs_voice_id",
                "tts_provider",
                "default_persona",
                "openai_model_name",
                "openai_base_url",
            ]
            for field in allowed_fields:
                if field in kwargs and kwargs[field] is not None:
                    setattr(s, field, kwargs[field])

            s.updated_at = datetime.datetime.utcnow()
            db.commit()
            db.refresh(s)
            return s.to_dict()

    # ==========================================
    # 3. Call Sessions & Transcripts (User Scoped)
    # ==========================================
    @staticmethod
    def create_call_session(
        conversation_id: str,
        persona: str = "concierge",
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        with SessionLocal() as db:
            existing = db.query(CallSession).filter(CallSession.conversation_id == conversation_id).first()
            if existing:
                if user_id and not existing.user_id:
                    existing.user_id = user_id
                    db.commit()
                return existing.to_dict()
            session = CallSession(
                conversation_id=conversation_id,
                user_id=user_id,
                persona=persona,
                status="active",
                start_time=datetime.datetime.utcnow(),
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            return session.to_dict()

    @staticmethod
    def end_call_session(
        conversation_id: str,
        status: str = "completed",
        summary: Optional[str] = None,
        sentiment: Optional[str] = None,
        audio_chunks_count: int = 0,
        total_audio_bytes: int = 0,
    ) -> Optional[Dict[str, Any]]:
        with SessionLocal() as db:
            session = db.query(CallSession).filter(CallSession.conversation_id == conversation_id).first()
            if not session:
                return None
            now = datetime.datetime.utcnow()
            session.end_time = now
            session.status = status
            if session.start_time:
                session.duration_seconds = max(0.0, (now - session.start_time).total_seconds())
            if summary:
                session.summary = summary
            if sentiment:
                session.sentiment = sentiment
            if audio_chunks_count:
                session.audio_chunks_count = audio_chunks_count
            if total_audio_bytes:
                session.total_audio_bytes = total_audio_bytes
            db.commit()
            db.refresh(session)
            return session.to_dict()

    @staticmethod
    def add_transcript_item(
        conversation_id: str,
        sender: str,
        text: str,
        latency_ms: Optional[float] = None,
    ) -> Dict[str, Any]:
        with SessionLocal() as db:
            session = db.query(CallSession).filter(CallSession.conversation_id == conversation_id).first()
            session_id = session.id if session else None
            item = TranscriptItem(
                conversation_id=conversation_id,
                session_id=session_id,
                sender=sender,
                text=text.strip(),
                latency_ms=latency_ms,
                timestamp=datetime.datetime.utcnow(),
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            return item.to_dict()

    @staticmethod
    def list_call_sessions(user_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with SessionLocal() as db:
            query = db.query(CallSession)
            if user_id is not None:
                query = query.filter(CallSession.user_id == user_id)
            sessions = query.order_by(CallSession.start_time.desc()).limit(limit).all()
            return [s.to_dict() for s in sessions]

    @staticmethod
    def get_call_session(conversation_id: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        with SessionLocal() as db:
            query = db.query(CallSession).filter(CallSession.conversation_id == conversation_id)
            if user_id is not None:
                query = query.filter(CallSession.user_id == user_id)
            session = query.first()
            if not session:
                return None
            res = session.to_dict()
            res["transcripts"] = [t.to_dict() for t in session.transcripts]
            res["appointments"] = [a.to_dict() for a in session.appointments]
            return res

    # ==========================================
    # 4. Appointments (User Scoped)
    # ==========================================
    @staticmethod
    def create_appointment(
        name: str,
        date: str,
        time: str,
        service: str = "General Consultation",
        conversation_id: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        with SessionLocal() as db:
            count = db.query(Appointment).count()
            booking_id = f"APPT-{count + 101}"

            session_id = None
            resolved_user_id = user_id
            if conversation_id:
                session = db.query(CallSession).filter(CallSession.conversation_id == conversation_id).first()
                if session:
                    session_id = session.id
                    if not resolved_user_id:
                        resolved_user_id = session.user_id

            appt = Appointment(
                id=booking_id,
                conversation_id=conversation_id,
                session_id=session_id,
                user_id=resolved_user_id,
                name=name,
                date=date,
                time=time,
                service=service or "General Consultation",
                status="confirmed",
                created_at=datetime.datetime.utcnow(),
            )
            db.add(appt)
            db.commit()
            db.refresh(appt)
            return appt.to_dict()

    @staticmethod
    def list_appointments(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with SessionLocal() as db:
            query = db.query(Appointment)
            if user_id is not None:
                query = query.filter(Appointment.user_id == user_id)
            appts = query.order_by(Appointment.created_at.desc()).all()
            return [a.to_dict() for a in appts]

    # ==========================================
    # 5. Personas (User Scoped)
    # ==========================================
    @staticmethod
    def save_custom_persona(persona_data: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
        with SessionLocal() as db:
            p_id = persona_data["id"]
            existing = db.query(CustomPersona).filter(CustomPersona.id == p_id).first()
            if existing and existing.user_id != user_id and existing.user_id is not None:
                raise ValueError("Unauthorized: Cannot modify a persona owned by another user.")

            idle_msgs = persona_data.get("idle_messages", [])
            idle_msgs_json = json.dumps(idle_msgs) if isinstance(idle_msgs, list) else str(idle_msgs)

            if existing:
                existing.name = persona_data.get("name", existing.name)
                existing.icon = persona_data.get("icon", existing.icon)
                existing.description = persona_data.get("description", existing.description)
                existing.system_prompt = persona_data.get("system_prompt", existing.system_prompt)
                existing.initial_message = persona_data.get("initial_message", existing.initial_message)
                existing.voice_id = persona_data.get("voice_id", existing.voice_id)
                existing.voice_name = persona_data.get("voice_name", existing.voice_name)
                existing.model_name = persona_data.get("model_name", existing.model_name)
                existing.temperature = float(persona_data.get("temperature", existing.temperature))
                existing.idle_nudge_timeout = float(persona_data.get("idle_nudge_timeout", existing.idle_nudge_timeout))
                existing.idle_messages_json = idle_msgs_json
                existing.idle_goodbye_message = persona_data.get("idle_goodbye_message", existing.idle_goodbye_message)
                p_obj = existing
            else:
                p_obj = CustomPersona(
                    id=p_id,
                    user_id=user_id,
                    name=persona_data.get("name", p_id),
                    icon=persona_data.get("icon", "🤖"),
                    description=persona_data.get("description", ""),
                    system_prompt=persona_data["system_prompt"],
                    initial_message=persona_data["initial_message"],
                    voice_id=persona_data.get("voice_id", "cgSgspJ2msm6clMCkdW9"),
                    voice_name=persona_data.get("voice_name", "Jessica"),
                    model_name=persona_data.get("model_name", "gemini-1.5-flash"),
                    temperature=float(persona_data.get("temperature", 0.7)),
                    idle_nudge_timeout=float(persona_data.get("idle_nudge_timeout", 12.0)),
                    idle_messages_json=idle_msgs_json,
                    idle_goodbye_message=persona_data.get("idle_goodbye_message", "Goodbye!"),
                    created_at=datetime.datetime.utcnow(),
                )
                db.add(p_obj)

            db.commit()
            db.refresh(p_obj)
            return p_obj.to_dict()

    @staticmethod
    def get_custom_persona(persona_id: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        with SessionLocal() as db:
            query = db.query(CustomPersona).filter(CustomPersona.id == persona_id)
            if user_id is not None:
                query = query.filter(or_(CustomPersona.user_id == user_id, CustomPersona.user_id == None))
            p = query.first()
            return p.to_dict() if p else None

    @staticmethod
    def list_custom_personas(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with SessionLocal() as db:
            query = db.query(CustomPersona)
            if user_id is not None:
                query = query.filter(or_(CustomPersona.user_id == user_id, CustomPersona.user_id == None))
            return [p.to_dict() for p in query.all()]

    @staticmethod
    def delete_custom_persona(persona_id: str, user_id: Optional[int] = None) -> bool:
        with SessionLocal() as db:
            query = db.query(CustomPersona).filter(CustomPersona.id == persona_id)
            if user_id is not None:
                query = query.filter(CustomPersona.user_id == user_id)
            p = query.first()
            if not p:
                return False
            db.delete(p)
            db.commit()
            return True


db_repository = DBRepository()
