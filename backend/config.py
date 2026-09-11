import os
from typing import Optional
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from current directory or web_voice_copilot root
load_dotenv()


class Settings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True

    # STT Settings
    deepgram_api_key: Optional[str] = None

    # LLM Settings: OpenAI, Google Gemini, or Groq
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_model_name: str = "gemini-3.5-flash-lite"

    # TTS Settings: eleven_labs (Studio Quality Streaming Voice), cartesia, stream_elements, azure
    tts_provider: str = "eleven_labs"
    eleven_labs_api_key: Optional[str] = None
    eleven_labs_voice_id: str = "EXAVITQu4vr4xnSDxMaL"  # Default: Sarah (warm, natural, reassuring)
    eleven_labs_model_id: str = "eleven_turbo_v2_5"
    eleven_labs_optimize_streaming_latency: int = 3
    edge_tts_voice: str = "en-US-AriaNeural"
    cartesia_api_key: Optional[str] = None
    streamelements_api_key: Optional[str] = None
    streamelements_voice: str = "Brian"
    azure_speech_key: Optional[str] = None
    azure_speech_region: str = "eastus"

    # Agent Persona & Idle Watching Settings
    default_persona: str = "concierge"
    allowed_idle_time_seconds: float = 12.0
    num_check_human_present_times: int = 2

    model_config = SettingsConfigDict(
        env_file=".env.example",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def has_stt_creds(self) -> bool:
        return bool(self.deepgram_api_key or os.getenv("DEEPGRAM_API_KEY"))

    @property
    def has_llm_creds(self) -> bool:
        return bool(
            self.gemini_api_key
            or self.openai_api_key
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )


settings = Settings()
