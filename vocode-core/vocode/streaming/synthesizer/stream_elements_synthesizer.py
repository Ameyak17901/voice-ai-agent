import io
import wave

import aiohttp
import edge_tts
try:
    import miniaudio
except (ImportError, OSError):
    miniaudio = None
from loguru import logger

from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.synthesizer import StreamElementsSynthesizerConfig
from vocode.streaming.synthesizer.base_synthesizer import BaseSynthesizer, SynthesisResult


class StreamElementsSynthesizer(BaseSynthesizer[StreamElementsSynthesizerConfig]):
    TTS_ENDPOINT = "https://api.streamelements.com/kappa/v2/speech"

    def __init__(
        self,
        synthesizer_config: StreamElementsSynthesizerConfig,
    ):
        super().__init__(synthesizer_config)
        self.voice = synthesizer_config.voice
        self.api_key = synthesizer_config.api_key

    async def _synthesize_edge_fallback(self, text: str) -> bytes:
        """Zero-cost fallback to Microsoft Edge Neural TTS when StreamElements is unauthenticated."""
        communicate = edge_tts.Communicate(text, voice="en-US-AriaNeural")
        audio_data = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])
        return bytes(audio_data)

    async def create_speech(
        self,
        message: BaseMessage,
        chunk_size: int,
        is_first_text_chunk: bool = False,
        is_sole_text_chunk: bool = False,
    ) -> SynthesisResult:
        url_params = {
            "voice": self.voice,
            "text": message.text,
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        raw_mp3_data = None
        try:
            async with self.async_requestor.get_session().get(
                self.TTS_ENDPOINT,
                params=url_params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    raw_mp3_data = await response.read()
                else:
                    logger.warning(
                        f"StreamElements TTS returned HTTP {response.status}. Automatically engaging free Neural Edge-TTS fallback."
                    )
        except Exception as e:
            logger.warning(f"StreamElements request failed ({e}). Falling back to Neural Edge-TTS.")

        if not raw_mp3_data:
            # Fallback to high-quality zero-cost neural TTS
            raw_mp3_data = await self._synthesize_edge_fallback(message.text)

        if miniaudio is not None:
            # In-memory pure C MP3 decoding via miniaudio
            sound = miniaudio.decode(raw_mp3_data)
            output_bytes_io = io.BytesIO()
            with wave.open(output_bytes_io, "wb") as wav_file:
                wav_file.setnchannels(sound.nchannels)
                wav_file.setsampwidth(sound.sample_width)
                wav_file.setframerate(sound.sample_rate)
                wav_file.writeframes(sound.samples)
            output_bytes_io.seek(0)
        else:
            # Fallback when miniaudio is blocked by Windows Application Control
            from pydub import AudioSegment
            seg = AudioSegment.from_file(io.BytesIO(raw_mp3_data), format="mp3")
            output_bytes_io = io.BytesIO()
            seg.export(output_bytes_io, format="wav")
            output_bytes_io.seek(0)

        result = self.create_synthesis_result_from_wav(
            synthesizer_config=self.synthesizer_config,
            file=output_bytes_io,
            message=message,
            chunk_size=chunk_size,
        )

        return result
