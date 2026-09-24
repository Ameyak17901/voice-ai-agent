import os
import warnings
from pathlib import Path

# In-memory miniaudio is used for decoding; suppress legacy pydub binary scan warning
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub.*")
import typing
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CustomizableConversationRouter(ConversationRouter):
    """
    Enhanced ConversationRouter that dynamically selects and instantiates the agent persona
    per session based on query parameters (?persona=...) without global state race conditions.
    """
    def get_conversation_for_persona(
        self,
        output_device: WebsocketOutputDevice,
        start_message: AudioConfigStartMessage,
        persona: Optional[str] = None,
    ) -> StreamingConversation:
        selected_persona = persona or settings.default_persona
        transcriber = self.transcriber_thunk(start_message.input_audio_config)
        synthesizer = create_synthesizer(start_message.output_audio_config, persona_key=selected_persona)
        synthesizer.get_synthesizer_config().should_encode_as_wav = True
        agent = create_agent(persona_key=selected_persona)
        return StreamingConversation(
            output_device=output_device,
            transcriber=transcriber,
            agent=agent,
            synthesizer=synthesizer,
            conversation_id=start_message.conversation_id,
            events_manager=(
                TranscriptEventManager(output_device)
                if start_message.subscribe_transcript
                else None
            ),
        )

    async def conversation(self, websocket: WebSocket):
        persona = websocket.query_params.get("persona") or settings.default_persona
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

        output_device = WebsocketOutputDevice(
            websocket,
            start_message.output_audio_config.sampling_rate,
            start_message.output_audio_config.audio_encoding,
        )
        conversation = self.get_conversation_for_persona(output_device, start_message, persona=persona)
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


# Request Models
class UpdateSettingsRequest(BaseModel):
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    deepgram_api_key: Optional[str] = None
    cartesia_api_key: Optional[str] = None
    eleven_labs_api_key: Optional[str] = None
    eleven_labs_voice_id: Optional[str] = None
    eleven_labs_model_id: Optional[str] = None
    streamelements_api_key: Optional[str] = None
    streamelements_voice: Optional[str] = None
    edge_tts_voice: Optional[str] = None
    tts_provider: Optional[str] = None
    default_persona: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_model_name: Optional[str] = None


class BookAppointmentRequest(BaseModel):
    name: str
    date: str
    time: str
    service: Optional[str] = "General Consultation"


@app.get("/healthz")
async def health_check() -> Dict[str, str]:
    """Lightweight liveness probe for Render / Docker health checks."""
    return {"status": "ok"}


@app.get("/api/status")
async def get_system_status() -> Dict[str, Any]:
    """Inspect current service configuration and credentials."""
    all_personas = agent_registry.get_all_personas()
    return {
        "status": "online",
        "has_stt_creds": settings.has_stt_creds,
        "has_llm_creds": settings.has_llm_creds,
        "has_gemini_key": bool(settings.gemini_api_key or os.getenv("GEMINI_API_KEY")),
        "tts_provider": settings.tts_provider,
        "current_persona": settings.default_persona,
        "openai_model_name": settings.openai_model_name,
        "edge_tts_voice": settings.edge_tts_voice,
        "eleven_labs_voice_id": settings.eleven_labs_voice_id,
        "eleven_labs_model_id": settings.eleven_labs_model_id,
        "streamelements_voice": settings.streamelements_voice,
        "has_streamelements_key": bool(settings.streamelements_api_key),
        "available_personas": [p.id for p in all_personas],
        "personas_count": len(all_personas),
        "endpoints": {
            "websocket_conversation": "/conversation",
            "health": "/api/status",
            "personas": "/api/personas",
            "voices": "/api/voices",
        },
    }


@app.get("/api/personas")
async def list_personas() -> List[Dict[str, Any]]:
    """Get all available personas (built-in + user-created custom)."""
    return [p.model_dump() for p in agent_registry.get_all_personas()]


@app.get("/api/personas/{persona_id}")
async def get_persona(persona_id: str) -> Dict[str, Any]:
    """Get full configuration for a single persona."""
    persona = agent_registry.get_persona(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona.model_dump()


@app.post("/api/personas")
async def create_or_update_persona(persona: VoicePersona) -> Dict[str, Any]:
    """Create or update a custom AI Voice Persona (persisted to agent_registry.json)."""
    try:
        saved = agent_registry.save_custom_persona(persona)
        return {"status": "success", "action": "created", "persona": saved.model_dump()}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error saving custom persona: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to persist persona: {str(e)}")


@app.delete("/api/personas/{persona_id}")
async def delete_persona(persona_id: str) -> Dict[str, Any]:
    """Delete a custom AI Voice Persona. Factory built-in presets cannot be deleted."""
    try:
        success = agent_registry.delete_custom_persona(persona_id)
        if not success:
            raise HTTPException(status_code=404, detail="Custom persona not found or already deleted")
        return {"status": "success", "action": "deleted", "persona_id": persona_id}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@app.get("/api/voices")
async def list_voices() -> List[Dict[str, Any]]:
    """Get available ElevenLabs studio voice presets for persona creation."""
    return [v.model_dump() for v in agent_registry.get_voice_presets()]


@app.post("/api/settings")
async def update_settings(req: UpdateSettingsRequest) -> Dict[str, Any]:
    """Dynamically update API keys or personas for the current runtime."""
    print(req)
    if req.gemini_api_key is not None:
        settings.gemini_api_key = req.gemini_api_key
        os.environ["GEMINI_API_KEY"] = req.gemini_api_key
    if req.openai_api_key is not None:
        settings.openai_api_key = req.openai_api_key
        os.environ["OPENAI_API_KEY"] = req.openai_api_key
    if req.deepgram_api_key is not None:
        settings.deepgram_api_key = req.deepgram_api_key
        os.environ["DEEPGRAM_API_KEY"] = req.deepgram_api_key
    if req.cartesia_api_key is not None:
        settings.cartesia_api_key = req.cartesia_api_key
        os.environ["CARTESIA_API_KEY"] = req.cartesia_api_key
    if req.eleven_labs_api_key is not None:
        settings.eleven_labs_api_key = req.eleven_labs_api_key
        os.environ["ELEVEN_LABS_API_KEY"] = req.eleven_labs_api_key
    if req.eleven_labs_voice_id is not None:
        settings.eleven_labs_voice_id = req.eleven_labs_voice_id
    if req.eleven_labs_model_id is not None:
        settings.eleven_labs_model_id = req.eleven_labs_model_id
    if req.streamelements_api_key is not None:
        settings.streamelements_api_key = req.streamelements_api_key
        os.environ["STREAMELEMENTS_API_KEY"] = req.streamelements_api_key
    if req.streamelements_voice is not None:
        settings.streamelements_voice = req.streamelements_voice
    if req.edge_tts_voice is not None:
        settings.edge_tts_voice = req.edge_tts_voice
    if req.tts_provider is not None:
        settings.tts_provider = req.tts_provider
    if req.default_persona is not None:
        print(req.default_persona)
        settings.default_persona = req.default_persona
    if req.openai_base_url is not None:
        settings.openai_base_url = req.openai_base_url
    if req.openai_model_name is not None:
        settings.openai_model_name = req.openai_model_name

    return {
        "status": "updated",
        "has_stt_creds": settings.has_stt_creds,
        "has_llm_creds": settings.has_llm_creds,
        "has_gemini_key": bool(settings.gemini_api_key or os.getenv("GEMINI_API_KEY")),
        "tts_provider": settings.tts_provider,
        "edge_tts_voice": settings.edge_tts_voice,
        "current_persona": settings.default_persona,
        "openai_model_name": settings.openai_model_name,
        "eleven_labs_voice_id": settings.eleven_labs_voice_id,
        "streamelements_voice": settings.streamelements_voice,
    }


@app.get("/api/appointments")
async def list_appointments() -> Dict[str, Any]:
    """Get all scheduled appointments."""
    return {
        "appointments": SCHEDULED_APPOINTMENTS,
        "availability": check_availability(),
    }


@app.post("/api/appointments/book")
async def api_book_appointment(req: BookAppointmentRequest) -> Dict[str, Any]:
    """Book an appointment via REST."""
    return book_appointment(req.name, req.date, req.time, req.service or "General Consultation")


@app.get("/api/company")
async def api_company_info() -> Dict[str, Any]:
    return get_company_info()


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

