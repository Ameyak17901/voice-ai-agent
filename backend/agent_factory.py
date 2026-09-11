import os
from typing import AsyncGenerator, Callable, Dict, Tuple, Optional
from loguru import logger

from vocode.streaming.agent.base_agent import BaseAgent, GeneratedResponse, RespondAgent
from vocode.streaming.agent.chat_gpt_agent import ChatGPTAgent
from vocode.streaming.models.agent import ChatGPTAgentConfig, AgentConfig, AgentType
from vocode.streaming.models.client_backend import InputAudioConfig, OutputAudioConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.synthesizer import (
    AzureSynthesizerConfig,
    CartesiaSynthesizerConfig,
    ElevenLabsSynthesizerConfig,
    StreamElementsSynthesizerConfig,
)
from vocode.streaming.models.transcriber import (
    DeepgramTranscriberConfig,
    PunctuationEndpointingConfig,
)
from vocode.streaming.synthesizer.azure_synthesizer import AzureSynthesizer
from vocode.streaming.synthesizer.base_synthesizer import BaseSynthesizer
from vocode.streaming.synthesizer.cartesia_synthesizer import CartesiaSynthesizer
from vocode.streaming.synthesizer.eleven_labs_synthesizer import ElevenLabsSynthesizer
from vocode.streaming.transcriber.base_transcriber import BaseTranscriber
from vocode.streaming.transcriber.deepgram_transcriber import (
    DeepgramTranscriber,
    DeepgramEndpointingConfig,
)

from .config import settings
from .tools import check_availability, book_appointment, get_company_info
from .agent_registry import agent_registry


GOODBYE_PHRASES = [
    "goodbye",
    "bye",
    "have a great day",
    "have a wonderful day",
    "take care",
    "talk to you soon",
    "have a good one",
    "see you",
    "farewell",
]

CLOSURE_INSTRUCTION = (
    "Conversation Ending Protocol: When the caller says thank you, indicates their inquiry is complete, "
    "or says goodbye (e.g., 'Thank you, that's all', 'Thanks, bye', 'I'm good, thanks'), warmly acknowledge them "
    "and conclude with a polite farewell containing 'Goodbye' or 'Have a wonderful day' so the call ends gracefully."
)


PERSONA_PROMPTS = {
    "concierge": (
        "You are Nova, an ultra-responsive, friendly AI voice assistant. "
        "Keep your responses concise, conversational, and direct (1 to 2 sentences max) "
        "because your responses are spoken out loud. Avoid bullet points or lists. "
        "You can help schedule appointments, answer questions about NovaVoice systems, "
        "and provide polite assistance."
    ),
    "receptionist": (
        "You are Chloe, the front-desk voice receptionist for Nova Medical & Wellness Clinic. "
        "Your tone is warm, professional, and empathetic. "
        "Speak naturally in short sentences. Inquire about how you can help, offer available "
        "appointment times, and confirm patient bookings efficiently."
    ),
    "tech_screener": (
        "You are Alex, an engineering interviewer assistant. "
        "You ask crisp, relevant software engineering questions, evaluate candidate reasoning, "
        "and converse naturally with audio brevity."
    ),
    "school_receptionist": (
        "You are the school receptionist. "
        "Your tone is warm, professional, and empathetic. "
        "Speak naturally in short sentences. Inquire about how you can help, offer available "
        "appointment times, and confirm patient bookings efficiently."
    )
}

PERSONA_INITIAL_MESSAGE = {
    "concierge": "Hello! I'm Nova, your real-time voice copilot. How can I assist you today?",
    "receptionist": "Hello! I'm Chloe, your voice receptionist. How can I help you today?",
    "tech_screener": "Hello! I'm Alex, your engineering interviewer assistant. How can I help you today?",
    "school_receptionist": "Hello! I'm the school receptionist. How can I help you today?"
}

PERSONA_IDLE_MESSAGES = {
    "concierge": [
        "I'm here whenever you're ready. What can I help you with today?",
        "Just checking in—are you still with me? Let me know if you can hear me.",
    ],
    "receptionist": [
        "Take your time. Were you looking to book an appointment or check clinic hours?",
        "Are you still on the line? Just let me know if you can hear me okay.",
    ],
    "tech_screener": [
        "Feel free to think aloud as you work through that technical question.",
        "Still there? Let me know if you'd like me to clarify anything.",
    ],
    "school_receptionist": [
        "I'm still here. How may I assist you or your student today?",
        "Hello, are you still there? Please let me know if you can hear me.",
    ],
}

PERSONA_IDLE_GOODBYE = {
    "concierge": "It seems we might be disconnected. I'll hang up for now. Feel free to reach out anytime. Goodbye!",
    "receptionist": "I haven't heard back for a while, so I will end this call. Please call Nova Medical Clinic back anytime. Take care!",
    "tech_screener": "Looks like we lost connection. Your responses so far have been saved. Thanks for your time today!",
    "school_receptionist": "Thank you for calling St. Jude School. I will disconnect now. Have a wonderful day!",
}


class MockAgentConfig(AgentConfig, type="agent_mock"):  # type: ignore
    pass


class SmartFallbackAgent(RespondAgent[MockAgentConfig]):
    """
    Persona-aware fallback agent used when external LLM API (OpenAI/Groq) is unavailable or rate-limited.
    Provides contextually accurate and distinct character responses across all personas.
    """
    def __init__(
        self,
        persona: str = "concierge",
        initial_message: Optional[str] = None,
    ):
        self.persona = persona
        init_text = initial_message or PERSONA_INITIAL_MESSAGE.get(persona, PERSONA_INITIAL_MESSAGE["concierge"])
        idle_msgs = PERSONA_IDLE_MESSAGES.get(persona, PERSONA_IDLE_MESSAGES["concierge"])
        idle_bye = PERSONA_IDLE_GOODBYE.get(persona, PERSONA_IDLE_GOODBYE["concierge"])
        config = MockAgentConfig(
            initial_message=BaseMessage(text=init_text),
            allowed_idle_time_seconds=settings.allowed_idle_time_seconds,
            num_check_human_present_times=settings.num_check_human_present_times,
            idle_messages=idle_msgs,
            idle_goodbye_message=idle_bye,
            end_conversation_on_goodbye=True,
            goodbye_phrases=GOODBYE_PHRASES,
        )
        super().__init__(agent_config=config)

    async def respond(
        self,
        human_input: str,
        conversation_id: str,
        is_interrupt: bool = False,
    ) -> Tuple[str, bool]:
        logger.info(
            f"[VOICE_PIPELINE: 3. SMART_FALLBACK_QUERY_RECEIVED] SmartFallbackAgent received query: '{human_input}' "
            f"(persona='{self.persona}', is_interrupt={is_interrupt})"
        )
        text_lower = human_input.lower()
        is_closing = False

        if self.persona == "receptionist":
            if any(w in text_lower for w in ["hello", "hi", "hey"]):
                response = "Hello! Chloe here at Nova Medical & Wellness Clinic. How can I help with your care today?"
            elif any(w in text_lower for w in ["book", "schedule", "appointment", "slot", "slots", "doctor"]):
                slots = check_availability()["available_slots"]
                response = f"We have clinic appointment slots open today at {slots[0]} and {slots[1]}. Which time would you prefer?"
            elif any(w in text_lower for w in ["who are you", "what are you", "your name"]):
                response = "I am Chloe, the front-desk medical receptionist for Nova Medical & Wellness Clinic."
            elif any(w in text_lower for w in ["hours", "open", "time", "location", "address"]):
                response = "Our clinic is open Monday through Saturday from 8 AM to 6 PM on Medical Center Boulevard."
            elif any(w in text_lower for w in ["thank", "bye", "goodbye", "that's all", "thats all"]):
                response = "You're very welcome. Take good care, and goodbye!"
                is_closing = True
            else:
                response = f"I've noted that for your clinic records: {human_input}. Would you like to confirm an appointment or speak with our nursing staff?"

        elif self.persona == "school_receptionist":
            if any(w in text_lower for w in ["hello", "hi", "hey"]):
                response = "Good day! St. Jude School front desk, Mary speaking. How may I assist you or your student today?"
            elif any(w in text_lower for w in ["tour", "admission", "enroll", "visit", "appointment", "slot"]):
                response = "We hold admissions tours on Tuesdays and Thursdays at 10 AM. Would you like to reserve a visit?"
            elif any(w in text_lower for w in ["absence", "sick", "leave", "attendance"]):
                response = "I can record that student absence for you today. Could you please provide the student's full name and grade?"
            elif any(w in text_lower for w in ["who are you", "what are you", "your name"]):
                response = "I am Mary, the school receptionist at St. Jude School."
            elif any(w in text_lower for w in ["thank", "bye", "goodbye", "that's all", "thats all"]):
                response = "Thank you for reaching out to St. Jude School. Have a wonderful day, goodbye!"
                is_closing = True
            else:
                response = f"Thank you for contacting the school office regarding: {human_input}. How else may I direct your inquiry?"

        elif self.persona == "tech_screener":
            if any(w in text_lower for w in ["hello", "hi", "hey"]):
                response = "Hey there! Alex here. Ready to dive into a few quick software engineering questions?"
            elif any(w in text_lower for w in ["python", "async", "asyncio", "threading", "gil"]):
                response = "Great! In Python, how do you manage high-concurrency I/O workloads without blocking the asyncio event loop?"
            elif any(w in text_lower for w in ["who are you", "what are you", "your name"]):
                response = "I'm Alex, an AI technical interviewer assistant specializing in software engineering screeners."
            elif any(w in text_lower for w in ["ready", "start", "next", "question"]):
                response = "Let's begin: Can you explain how you design for low latency in a real-time streaming WebSocket architecture?"
            elif any(w in text_lower for w in ["thank", "bye", "goodbye", "that's all", "thats all"]):
                response = "Thanks for your time today! Your technical responses have been recorded. Have a great day, goodbye!"
                is_closing = True
            else:
                response = f"Got it, regarding {human_input}: what are the key trade-offs and latency considerations with that design?"

        else:  # concierge (Nova)
            if any(w in text_lower for w in ["hello", "hi", "hey"]):
                response = "Hello there! Nova here, your voice copilot. How can I assist you today?"
            elif any(w in text_lower for w in ["book", "schedule", "appointment", "slot", "slots"]):
                slots = check_availability()["available_slots"]
                response = f"I can certainly help with that. We have slots open today at {slots[0]} and {slots[1]}. Would either of those work for you?"
            elif any(w in text_lower for w in ["info", "service", "company", "about"]):
                info = get_company_info()
                response = f"We are {info['name']}. We specialize in real-time AI voice copilot solutions."
            elif any(w in text_lower for w in ["who are you", "what are you", "your name"]):
                response = "I am Nova, your executive AI voice copilot. I stream speech back and forth with low latency."
            elif any(w in text_lower for w in ["thank", "bye", "goodbye", "that's all", "thats all"]):
                response = "You're very welcome! Have a wonderful day, goodbye!"
                is_closing = True
            else:
                response = f"You said: {human_input}. How else can I assist your team today?"

        return response, is_closing

    async def generate_response(
        self,
        human_input: str,
        conversation_id: str,
        is_interrupt: bool = False,
        bot_was_in_medias_res: bool = False,
    ) -> AsyncGenerator[GeneratedResponse, None]:
        text, should_stop = await self.respond(human_input, conversation_id, is_interrupt)
        yield GeneratedResponse(message=BaseMessage(text=text), is_interruptible=True)

    def update_last_bot_message_on_cut_off(self, message: str):
        pass


class ResilientChatGPTAgent(ChatGPTAgent):
    """
    Production resilient ChatGPTAgent that catches OpenAI RateLimitError (quota exhausted),
    connection errors, or auth failures, and automatically fails over to SmartFallbackAgent
    so the voice session never crashes or goes silent.
    """

    def __init__(self, config: ChatGPTAgentConfig, fallback_agent: Optional[SmartFallbackAgent] = None):
        super().__init__(config)
        self.fallback_agent = fallback_agent or SmartFallbackAgent()
        self.fallback_active = False

    async def generate_response(
        self,
        human_input: str,
        conversation_id: str,
        is_interrupt: bool = False,
        bot_was_in_medias_res: bool = False,
    ) -> AsyncGenerator[GeneratedResponse, None]:
        logger.info(
            f"[VOICE_PIPELINE: 3. AGENT_FACTORY_INGRESS] ResilientChatGPTAgent processing query: '{human_input}' "
            f"(persona='{self.fallback_agent.persona}', fallback_active={self.fallback_active})"
        )
        if self.fallback_active:
            logger.info(f"ResilientChatGPTAgent: Routing '{human_input}' directly to SmartFallbackAgent ({self.fallback_agent.persona}).")
            async for resp in self.fallback_agent.generate_response(
                human_input, conversation_id, is_interrupt, bot_was_in_medias_res
            ):
                yield resp
            return

        try:
            async for resp in super().generate_response(
                human_input, conversation_id, is_interrupt, bot_was_in_medias_res
            ):
                yield resp
        except Exception as exc:
            logger.error(
                f"[VOICE_PIPELINE: LLM_ERROR] ResilientChatGPTAgent primary LLM call failed ({type(exc).__name__}: {exc}). "
                f"Engaging SmartFallbackAgent failover for persona '{self.fallback_agent.persona}' so user receives immediate voice response."
            )
            self.fallback_active = True
            async for resp in self.fallback_agent.generate_response(
                human_input, conversation_id, is_interrupt, bot_was_in_medias_res
            ):
                yield resp


def create_agent(persona_key: Optional[str] = None) -> BaseAgent:
    """Factory to create an LLM agent (Gemini 1.5 Flash, ChatGPTAgent, or SmartFallbackAgent) with persona awareness."""
    persona = persona_key or settings.default_persona
    persona_obj = agent_registry.get_persona(persona) or agent_registry.get_persona("concierge")
    prompt_preamble = persona_obj.system_prompt if persona_obj else PERSONA_PROMPTS.get(persona, PERSONA_PROMPTS["concierge"])
    if CLOSURE_INSTRUCTION not in prompt_preamble:
        prompt_preamble = f"{prompt_preamble}\n\n{CLOSURE_INSTRUCTION}"
    initial_text = persona_obj.initial_message if persona_obj else PERSONA_INITIAL_MESSAGE.get(persona, PERSONA_INITIAL_MESSAGE["concierge"])
    fallback_agent = SmartFallbackAgent(persona=persona, initial_message=initial_text)

    idle_msgs = persona_obj.idle_messages if persona_obj else PERSONA_IDLE_MESSAGES.get(persona, PERSONA_IDLE_MESSAGES["concierge"])
    idle_bye = persona_obj.idle_goodbye_message if persona_obj else PERSONA_IDLE_GOODBYE.get(persona, PERSONA_IDLE_GOODBYE["concierge"])
    allowed_idle = persona_obj.idle_nudge_timeout if persona_obj else settings.allowed_idle_time_seconds
    num_retries = settings.num_check_human_present_times

    # 1. Check for dedicated Gemini API key (Free Tier: 1,500 requests/day, fast sub-200ms TTFT)
    gemini_key = settings.gemini_api_key or os.getenv("GEMINI_API_KEY")
    if gemini_key:
        model_name = settings.openai_model_name or "gemini-3.5-flash-lite"
        # Auto-upgrade deprecated Google Gemini model endpoints
        if any(deprecated in model_name for deprecated in ["gemini-1.5", "gemini-2.0", "gemini-2.5", "gemini-1.0"]):
            model_name = "gemini-3.5-flash-lite"
        logger.info(f"Initializing ResilientChatGPTAgent with Google {model_name} for persona '{persona}' (idle_nudge={allowed_idle}s)...")
        config = ChatGPTAgentConfig(
            initial_message=BaseMessage(text=initial_text),
            prompt_preamble=prompt_preamble,
            model_name=model_name,
            openai_api_key=gemini_key,
            base_url_override="https://generativelanguage.googleapis.com/v1beta/openai/",
            allowed_idle_time_seconds=allowed_idle,
            num_check_human_present_times=num_retries,
            idle_messages=idle_msgs,
            idle_goodbye_message=idle_bye,
            max_tokens=150,
            end_conversation_on_goodbye=True,
            goodbye_phrases=GOODBYE_PHRASES,
        )
        return ResilientChatGPTAgent(config, fallback_agent=fallback_agent)

    # 2. Check for OpenAI or Groq API credentials
    openai_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if openai_key:
        model_name = settings.openai_model_name
        base_url = settings.openai_base_url or os.getenv("OPENAI_BASE_URL")
        # If model is configured as gemini and key passed under openai_key:
        if "gemini" in model_name.lower() and not base_url:
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

        logger.info(f"Initializing ResilientChatGPTAgent (Model: {model_name}) for persona '{persona}' (idle_nudge={allowed_idle}s)...")
        config = ChatGPTAgentConfig(
            initial_message=BaseMessage(text=initial_text),
            prompt_preamble=prompt_preamble,
            model_name=model_name,
            openai_api_key=openai_key,
            base_url_override=base_url,
            allowed_idle_time_seconds=allowed_idle,
            num_check_human_present_times=num_retries,
            idle_messages=idle_msgs,
            idle_goodbye_message=idle_bye,
            max_tokens=150,
            end_conversation_on_goodbye=True,
            goodbye_phrases=GOODBYE_PHRASES,
        )
        return ResilientChatGPTAgent(config, fallback_agent=fallback_agent)

    logger.warning(
        f"No LLM API key detected. Starting with SmartFallbackAgent for persona '{persona}'."
    )
    return fallback_agent


def create_transcriber(input_audio_config: InputAudioConfig) -> BaseTranscriber:
    """Factory to create the streaming STT transcriber with Nova-2 and Neural VAD."""
    api_key = settings.deepgram_api_key or os.getenv("DEEPGRAM_API_KEY")
    endpointing_cfg = DeepgramEndpointingConfig(
        vad_threshold_ms=300,
        utterance_cutoff_ms=800,
    )
    if api_key:
        logger.info("Configuring DeepgramTranscriber with Nova-2 model and Neural VAD.")
        config = DeepgramTranscriberConfig.from_input_audio_config(
            input_audio_config=input_audio_config,
            model="nova-2",
            language="en-US",
            endpointing_config=endpointing_cfg,
            api_key=api_key,
            mute_during_speech=False,  # Allow barge-in and ensure human audio is captured continuously
            min_interrupt_confidence=0.7,
        )
        return DeepgramTranscriber(config)
    else:
        logger.warning(
            "No DEEPGRAM_API_KEY detected. Setting up DeepgramTranscriber with default env check."
        )
        config = DeepgramTranscriberConfig.from_input_audio_config(
            input_audio_config=input_audio_config,
            model="nova-2",
            language="en-US",
            endpointing_config=endpointing_cfg,
            mute_during_speech=True,
        )
        return DeepgramTranscriber(config)


PERSONA_ELEVEN_LABS_VOICE_IDS = {
    "concierge": "cgSgspJ2msm6clMCkdW9",        # Jessica - Playful, Bright, Warm, Female
    "receptionist": "EXAVITQu4vr4xnSDxMaL",     # Sarah - Reassuring, Confident, Empathetic, Female
    "tech_screener": "cjVigY5qzO86Huf0OWal",    # Eric - Smooth, Trustworthy, Technical, Male
    "school_receptionist": "XrExE9yKIg1WjnnlVkGX", # Matilda - Professional, Articulate, Patient, Female
}


def create_synthesizer(
    output_audio_config: OutputAudioConfig,
    persona_key: Optional[str] = None,
) -> BaseSynthesizer:
    """Factory to create the streaming TTS synthesizer with ElevenLabs as primary studio provider."""
    provider = settings.tts_provider.lower().strip()
    eleven_labs_key = settings.eleven_labs_api_key or os.getenv("ELEVEN_LABS_API_KEY")

    # 1. ElevenLabs Studio Quality Streaming TTS (Turbo v2.5, Linear16 PCM 16kHz)
    if provider == "eleven_labs" or (eleven_labs_key and provider not in ("cartesia", "azure", "edge_tts", "stream_elements")):
        # Resolve persona-specific voice ID if available
        voice_id = None
        persona_obj = agent_registry.get_persona(persona_key)
        if persona_obj and persona_obj.voice_id:
            voice_id = persona_obj.voice_id
        elif persona_key and persona_key in PERSONA_ELEVEN_LABS_VOICE_IDS:
            voice_id = PERSONA_ELEVEN_LABS_VOICE_IDS[persona_key]
        if not voice_id:
            voice_id = settings.eleven_labs_voice_id or "cgSgspJ2msm6clMCkdW9"

        logger.info(
            f"Using ElevenLabs Turbo v2.5 Synthesizer (Voice ID: {voice_id}, Persona: '{persona_key or 'default'}', Model: {settings.eleven_labs_model_id})."
        )
        config = ElevenLabsSynthesizerConfig.from_output_audio_config(
            output_audio_config=output_audio_config,
            api_key=eleven_labs_key,
            voice_id=voice_id,
            model_id=settings.eleven_labs_model_id,
            optimize_streaming_latency=settings.eleven_labs_optimize_streaming_latency,
        )
        return ElevenLabsSynthesizer(config)

    elif provider == "cartesia" and (settings.cartesia_api_key or os.getenv("CARTESIA_API_KEY")):
        logger.info("Using Cartesia Synthesizer.")
        config = CartesiaSynthesizerConfig.from_output_audio_config(
            output_audio_config=output_audio_config,
            api_key=settings.cartesia_api_key or os.getenv("CARTESIA_API_KEY"),
        )
        return CartesiaSynthesizer(config)

    elif provider in ("edge_tts", "edge", "stream_elements"):
        voice = getattr(settings, "edge_tts_voice", None) or settings.streamelements_voice or "en-US-AriaNeural"
        logger.info(f"Using Edge-TTS Neural Synthesizer (Voice: {voice}).")
        config = StreamElementsSynthesizerConfig.from_output_audio_config(
            output_audio_config=output_audio_config,
            voice=voice,
            api_key=settings.streamelements_api_key or os.getenv("STREAMELEMENTS_API_KEY"),
        )
        return StreamElementsSynthesizer(config)

    elif provider == "azure" and (settings.azure_speech_key or os.getenv("AZURE_SPEECH_KEY")):
        logger.info("Using Azure Synthesizer.")
        config = AzureSynthesizerConfig.from_output_audio_config(
            output_audio_config=output_audio_config,
        )
        return AzureSynthesizer(config)

    else:
        # Fallback to StreamElements
        logger.info(f"Using StreamElements Synthesizer (Voice: {settings.streamelements_voice}).")
        config = StreamElementsSynthesizerConfig.from_output_audio_config(
            output_audio_config=output_audio_config,
            voice=settings.streamelements_voice,
            api_key=settings.streamelements_api_key or os.getenv("STREAMELEMENTS_API_KEY"),
        )
        return StreamElementsSynthesizer(config)
