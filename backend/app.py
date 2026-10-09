import os
import warnings
from pathlib import Path

# In-memory miniaudio is used for decoding; suppress legacy pydub binary scan warning
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub.*")
import typing
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from loguru import logger

from vocode.logging import configure_pretty_logging
from vocode.streaming.client_backend.conversation import ConversationRouter, TranscriptEventManager
from vocode.streaming.models.websocket import (
    AudioConfigStartMessage,
    AudioMessage,
    ReadyMessage,
    StopMessage,
    WebSocketMessage,
    WebSocketMessageType,
)
from vocode.streaming.output_device.websocket_output_device import WebsocketOutputDevice
from vocode.streaming.streaming_conversation import StreamingConversation

from vocode.streaming.models.events import Event, EventType
from vocode.streaming.models.transcript import TranscriptEvent
from .config import settings
from .agent_registry import agent_registry, VoicePersona
from .agent_factory import (
    create_agent,
    create_transcriber,
    create_synthesizer,
    PERSONA_PROMPTS,
)
from .tools import (
    SCHEDULED_APPOINTMENTS,
    check_availability,
    book_appointment,
    get_company_info,
)
from backend.db.repository import db_repository
from backend.auth import (
    create_access_token,
    decode_access_token,
    get_current_user,
    get_optional_current_user,
)

# Enable pretty logging for Vocode streaming events
configure_pretty_logging()

app = FastAPI(
    title="Vocode Web Voice Copilot Service",
    description="Full-duplex real-time streaming voice agent built with Vocode open-source",
    version="1.0.0",
)

# Enable CORS for web clients (Vercel frontend, local development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PersistentTranscriptEventManager(TranscriptEventManager):
    """
    Subclasses Vocode TranscriptEventManager to capture and persist final
    conversation turn transcripts to the SQLite database while streaming to the web client.
    """
    def __init__(self, output_device: WebsocketOutputDevice, conversation_id: str):
        super().__init__(output_device)
        self.conversation_id = conversation_id

    async def handle_event(self, event: Event):
        if event.type == EventType.TRANSCRIPT:
            transcript_event = typing.cast(TranscriptEvent, event)
            sender_name = getattr(transcript_event.sender, "value", str(transcript_event.sender))
            status_name = "FINAL" if transcript_event.is_final else "INTERIM"
            logger.info(f"Transcript [{sender_name.upper()} {status_name}]: '{transcript_event.text}'")

            # Persist final turns into SQLite database
            if transcript_event.is_final and transcript_event.text.strip():
                try:
                    db_repository.add_transcript_item(
                        conversation_id=self.conversation_id,
                        sender=sender_name.lower(),
                        text=transcript_event.text.strip(),
                    )
                except Exception as ex:
                    logger.warning(f"Failed to persist transcript item: {ex}")

            await self.output_device.send_transcript(transcript_event)


class CustomizableConversationRouter(ConversationRouter):
    """
    Enhanced ConversationRouter that dynamically selects and instantiates the agent persona
    per session based on query parameters (?persona=...) without global state race conditions,
    and persists call sessions and transcripts into SQLite.
    """
    def get_conversation_for_persona(
        self,
        output_device: WebsocketOutputDevice,
        start_message: AudioConfigStartMessage,
        persona: Optional[str] = None,
        user_id: Optional[int] = None,
        user_settings: Optional[Dict[str, Any]] = None,
    ) -> StreamingConversation:
        selected_persona = persona or (user_settings.get("default_persona") if user_settings else None) or settings.default_persona
        transcriber = create_transcriber(start_message.input_audio_config, user_settings=user_settings)
        synthesizer = create_synthesizer(
            start_message.output_audio_config,
            persona_key=selected_persona,
            user_id=user_id,
            user_settings=user_settings,
        )
        synthesizer.get_synthesizer_config().should_encode_as_wav = True
        agent = create_agent(persona_key=selected_persona, user_id=user_id, user_settings=user_settings)
        return StreamingConversation(
            output_device=output_device,
            transcriber=transcriber,
            agent=agent,
            synthesizer=synthesizer,
            conversation_id=start_message.conversation_id,
            events_manager=PersistentTranscriptEventManager(
                output_device,
                conversation_id=start_message.conversation_id,
            ),
        )

    async def conversation(self, websocket: WebSocket):
        persona = websocket.query_params.get("persona") or settings.default_persona
        token = websocket.query_params.get("token")
        user_id: Optional[int] = None
        user_settings: Optional[Dict[str, Any]] = None

        if token:
            payload = decode_access_token(token)
            if payload and "sub" in payload:
                try:
                    user_id = int(payload["sub"])
                    user_settings = db_repository.get_user_credentials(user_id)
                    logger.info(f"[WS_AUTH] Authenticated WebSocket session for user_id={user_id} (persona='{persona}').")
                except Exception as ex:
                    logger.warning(f"[WS_AUTH] Failed to resolve user credentials from token: {ex}")

        await websocket.accept()
        try:
            start_message: AudioConfigStartMessage = AudioConfigStartMessage.parse_obj(
                await websocket.receive_json()
            )
        except (WebSocketDisconnect, RuntimeError):
            logger.info("Client disconnected before session start.")
            return
        except Exception as e:
            logger.warning(f"Failed to receive audio config start message: {e}")
            await websocket.close()
            return

        conversation_id = start_message.conversation_id
        # Persist session start into SQLite database associated with user_id
        try:
            db_repository.create_call_session(
                conversation_id=conversation_id,
                persona=persona,
                user_id=user_id,
            )
            logger.info(f"[CALL_SESSION: CREATED] Session '{conversation_id}' initialized (persona='{persona}', user_id={user_id}).")
        except Exception as ex:
            logger.error(f"Failed to record call session start: {ex}")

        output_device = WebsocketOutputDevice(
            websocket,
            start_message.output_audio_config.sampling_rate,
            start_message.output_audio_config.audio_encoding,
        )
        conversation = self.get_conversation_for_persona(
            output_device,
            start_message,
            persona=persona,
            user_id=user_id,
            user_settings=user_settings,
        )
        await conversation.start(lambda: websocket.send_text(ReadyMessage().json()))

        audio_chunks_count = 0
        total_audio_bytes = 0
        try:
            while conversation.is_active():
                try:
                    message: WebSocketMessage = WebSocketMessage.parse_obj(await websocket.receive_json())
                except (WebSocketDisconnect, RuntimeError):
                    logger.info("Client disconnected gracefully.")
                    break
                except Exception as e:
                    logger.warning(f"WebSocket read loop exit: {type(e).__name__} - {e}")
                    break

                if message.type == WebSocketMessageType.STOP:
                    logger.info("Received STOP signal from client.")
                    break
                audio_message = typing.cast(AudioMessage, message)
                chunk_bytes = audio_message.get_bytes()
                audio_chunks_count += 1
                total_audio_bytes += len(chunk_bytes)
                if audio_chunks_count % 50 == 1:
                    logger.info(
                        f"[VOICE_PIPELINE: 1. AUDIO_INGRESS_WS] Received {audio_chunks_count} chunks "
                        f"({total_audio_bytes} bytes total) from client microphone (persona='{persona}')"
                    )
                conversation.receive_audio(chunk_bytes)
        finally:
            output_device.mark_closed()
            await conversation.terminate()
            # Finalize session metrics and status in SQLite database
            try:
                db_repository.end_call_session(
                    conversation_id=conversation_id,
                    status="completed",
                    audio_chunks_count=audio_chunks_count,
                    total_audio_bytes=total_audio_bytes,
                )
                logger.info(f"[CALL_SESSION: ENDED] Session '{conversation_id}' closed ({audio_chunks_count} chunks, {total_audio_bytes} bytes).")
            except Exception as ex:
                logger.warning(f"Failed to record call session end: {ex}")

            try:
                if websocket.client_state.name == "CONNECTED":
                    await websocket.send_text(StopMessage().json())
                    await websocket.close(code=1000)
            except Exception:
                pass


# Initialize Vocode CustomizableConversationRouter
conversation_router = CustomizableConversationRouter(
    agent_thunk=lambda: create_agent(),
    transcriber_thunk=lambda input_cfg: create_transcriber(input_cfg),
    synthesizer_thunk=lambda output_cfg: create_synthesizer(output_cfg),
    conversation_endpoint="/conversation",
)
app.include_router(conversation_router.get_router())


# Request & Response Models
class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str


class LoginRequest(BaseModel):
    email_or_username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


class UpdateSettingsRequest(BaseModel):
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    deepgram_api_key: Optional[str] = None
    cartesia_api_key: Optional[str] = None
    eleven_labs_api_key: Optional[str] = None
    eleven_labs_voice_id: Optional[str] = None
    tts_provider: Optional[str] = None
    default_persona: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_model_name: Optional[str] = None


class BookAppointmentRequest(BaseModel):
    name: str
    date: str
    time: str
    service: Optional[str] = "General Consultation"


# ==========================================
# 1. Authentication Endpoints
# ==========================================
@app.post("/api/auth/register", response_model=TokenResponse)
async def register(req: RegisterRequest) -> Dict[str, Any]:
    """Register a new user, initialize isolated settings, and return a JWT access token."""
    try:
        user = db_repository.create_user(req.email, req.username, req.password)
        token = create_access_token({"sub": str(user["id"]), "username": user["username"]})
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": user,
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to register user")


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest) -> Dict[str, Any]:
    """Authenticate with email or username and password, returning a JWT access token."""
    user = db_repository.authenticate_user(req.email_or_username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email/username or password")
    token = create_access_token({"sub": str(user["id"]), "username": user["username"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
    }


@app.get("/api/auth/me")
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Get profile and settings for the authenticated user."""
    return current_user


# ==========================================
# 2. System & Health Endpoints
# ==========================================
@app.get("/healthz")
async def health_check() -> Dict[str, str]:
    """Lightweight liveness probe for Render / Docker health checks."""
    return {"status": "ok"}


@app.get("/api/status")
async def get_system_status(
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
) -> Dict[str, Any]:
    """Inspect system status and user-specific credentials."""
    user_id = current_user["id"] if current_user else None
    all_personas = agent_registry.get_all_personas(user_id=user_id)
    u_creds = db_repository.get_user_credentials(user_id) if user_id else {}
    has_stt = bool(u_creds.get("deepgram_api_key") or settings.has_stt_creds)
    has_llm = bool(u_creds.get("gemini_api_key") or u_creds.get("openai_api_key") or settings.has_llm_creds)
    return {
        "status": "online",
        "authenticated": bool(current_user),
        "user_id": user_id,
        "has_stt_creds": has_stt,
        "has_llm_creds": has_llm,
        "tts_provider": u_creds.get("tts_provider") or settings.tts_provider,
        "current_persona": u_creds.get("default_persona") or settings.default_persona,
        "openai_model_name": u_creds.get("openai_model_name") or settings.openai_model_name,
        "eleven_labs_voice_id": u_creds.get("eleven_labs_voice_id") or settings.eleven_labs_voice_id,
        "available_personas": [p.id for p in all_personas],
        "personas_count": len(all_personas),
        "endpoints": {
            "websocket_conversation": "/conversation",
            "health": "/api/status",
            "auth_register": "/api/auth/register",
            "auth_login": "/api/auth/login",
            "auth_me": "/api/auth/me",
            "settings": "/api/settings",
            "personas": "/api/personas",
            "calls": "/api/calls",
            "appointments": "/api/appointments",
        },
    }


# ==========================================
# 3. User-Specific Settings Endpoints
# ==========================================
@app.get("/api/settings")
async def get_settings(
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
) -> Dict[str, Any]:
    """Get user-specific settings if authenticated, otherwise server defaults."""
    if current_user:
        return db_repository.get_user_settings(current_user["id"])
    return {
        "user_id": None,
        "has_openai_key": bool(settings.openai_api_key),
        "has_gemini_key": bool(settings.gemini_api_key),
        "has_deepgram_key": bool(settings.deepgram_api_key),
        "has_eleven_labs_key": bool(settings.eleven_labs_api_key),
        "eleven_labs_voice_id": settings.eleven_labs_voice_id,
        "tts_provider": settings.tts_provider,
        "default_persona": settings.default_persona,
        "openai_model_name": settings.openai_model_name,
        "openai_base_url": settings.openai_base_url,
    }


@app.post("/api/settings")
async def update_settings(
    req: UpdateSettingsRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> Dict[str, Any]:
    """Persist user-specific credentials without modifying global process environment."""
    if current_user:
        fields = req.model_dump(exclude_unset=True)
        updated = db_repository.update_user_settings(current_user["id"], **fields)
        return {
            "status": "updated",
            "scope": "user",
            "settings": updated,
        }
    else:
        # Fallback for unauthenticated local development without multi-user isolation
        if req.gemini_api_key is not None:
            settings.gemini_api_key = req.gemini_api_key
        if req.openai_api_key is not None:
            settings.openai_api_key = req.openai_api_key
        if req.deepgram_api_key is not None:
            settings.deepgram_api_key = req.deepgram_api_key
        if req.eleven_labs_api_key is not None:
            settings.eleven_labs_api_key = req.eleven_labs_api_key
        if req.tts_provider is not None:
            settings.tts_provider = req.tts_provider
        if req.default_persona is not None:
            settings.default_persona = req.default_persona
        if req.openai_model_name is not None:
            settings.openai_model_name = req.openai_model_name
        return {
            "status": "updated",
            "scope": "guest_runtime",
            "settings": {
                "user_id": None,
                "current_persona": settings.default_persona,
                "tts_provider": settings.tts_provider,
            },
        }


# ==========================================
# 4. User-Scoped Personas Endpoints
# ==========================================
@app.get("/api/personas")
async def list_personas(
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
) -> List[Dict[str, Any]]:
    """Get all available personas (built-in presets + user's private custom personas)."""
    user_id = current_user["id"] if current_user else None
    return [p.model_dump() for p in agent_registry.get_all_personas(user_id=user_id)]


@app.get("/api/personas/{persona_id}")
async def get_persona(
    persona_id: str,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> Dict[str, Any]:
    """Get full configuration for a single persona."""
    user_id = current_user["id"] if current_user else None
    persona = agent_registry.get_persona(persona_id, user_id=user_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona.model_dump()


@app.post("/api/personas")
async def create_or_update_persona(
    persona: VoicePersona,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> Dict[str, Any]:
    """Create or update a custom AI Voice Persona isolated to the current user."""
    user_id = current_user["id"] if current_user else None
    try:
        saved = agent_registry.save_custom_persona(persona, user_id=user_id)
        return {"status": "success", "action": "created", "persona": saved.model_dump()}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error saving custom persona: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to persist persona: {str(e)}")


@app.delete("/api/personas/{persona_id}")
async def delete_persona(
    persona_id: str,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> Dict[str, Any]:
    """Delete a custom AI Voice Persona owned by the current user."""
    user_id = current_user["id"] if current_user else None
    try:
        success = agent_registry.delete_custom_persona(persona_id, user_id=user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Custom persona not found or not owned by you")
        return {"status": "success", "action": "deleted", "persona_id": persona_id}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@app.get("/api/voices")
async def list_voices() -> List[Dict[str, Any]]:
    """Get available ElevenLabs studio voice presets for persona creation."""
    return [v.model_dump() for v in agent_registry.get_voice_presets()]


# ==========================================
# 5. User-Scoped Calls & Appointments Endpoints
# ==========================================
@app.get("/api/appointments")
async def list_appointments(
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
) -> Dict[str, Any]:
    """Get scheduled appointments scoped to the authenticated user."""
    user_id = current_user["id"] if current_user else None
    return {
        "appointments": db_repository.list_appointments(user_id=user_id),
        "availability": check_availability(),
    }


@app.post("/api/appointments/book")
async def api_book_appointment(
    req: BookAppointmentRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> Dict[str, Any]:
    """Book an appointment via REST into SQLite database associated with user."""
    user_id = current_user["id"] if current_user else None
    return book_appointment(
        name=req.name,
        date=req.date,
        time=req.time,
        service=req.service or "General Consultation",
        user_id=user_id,
    )


@app.get("/api/company")
async def api_company_info() -> Dict[str, Any]:
    """Get company and clinic knowledge base details."""
    return get_company_info()


@app.get("/api/calls")
async def list_calls(
    limit: int = 50,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> List[Dict[str, Any]]:
    """List call sessions scoped to the authenticated user."""
    user_id = current_user["id"] if current_user else None
    return db_repository.list_call_sessions(user_id=user_id, limit=limit)


@app.get("/api/calls/{conversation_id}")
async def get_call_details(
    conversation_id: str,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> Dict[str, Any]:
    """Get full call details, including turn transcripts and booked appointments."""
    user_id = current_user["id"] if current_user else None
    session_data = db_repository.get_call_session(conversation_id, user_id=user_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Call session not found")
    return session_data


# Mount Frontend (Prioritize React build in frontend_react/dist, fallback to static frontend)
REACT_DIST_DIR = Path(__file__).resolve().parent.parent / "frontend_react" / "dist"
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if REACT_DIST_DIR.exists() and (REACT_DIST_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=str(REACT_DIST_DIR / "assets")), name="react-assets")

    @app.get("/")
    async def serve_react_index():
        return FileResponse(REACT_DIST_DIR / "index.html")

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    if not (REACT_DIST_DIR.exists() and (REACT_DIST_DIR / "index.html").exists()):
        @app.get("/")
        async def serve_index():
            return FileResponse(FRONTEND_DIR / "index.html")

