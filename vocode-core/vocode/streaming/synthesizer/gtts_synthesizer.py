import asyncio
import wave
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from gtts import gTTS
try:
    import miniaudio
except (ImportError, OSError):
    miniaudio = None

from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.synthesizer import GTTSSynthesizerConfig
from vocode.streaming.synthesizer.base_synthesizer import BaseSynthesizer, SynthesisResult


class GTTSSynthesizer(BaseSynthesizer):
    def __init__(
        self,
        synthesizer_config: GTTSSynthesizerConfig,
    ):
        super().__init__(synthesizer_config)

        self.thread_pool_executor = ThreadPoolExecutor(max_workers=1)

    async def create_speech(
        self,
        message: BaseMessage,
        chunk_size: int,
        is_first_text_chunk: bool = False,
        is_sole_text_chunk: bool = False,
    ) -> SynthesisResult:
        audio_file = BytesIO()

        def thread():
            tts = gTTS(message.text)
            tts.write_to_fp(audio_file)

        await asyncio.get_event_loop().run_in_executor(self.thread_pool_executor, thread)
        audio_file.seek(0)
        sound = miniaudio.decode(audio_file.read())
        output_bytes_io = BytesIO()
        with wave.open(output_bytes_io, "wb") as wav_file:
            wav_file.setnchannels(sound.nchannels)
            wav_file.setsampwidth(sound.sample_width)
            wav_file.setframerate(sound.sample_rate)
            wav_file.writeframes(sound.samples)
        output_bytes_io.seek(0)

        result = self.create_synthesis_result_from_wav(
            synthesizer_config=self.synthesizer_config,
            file=output_bytes_io,
            message=message,
            chunk_size=chunk_size,
        )
        return result
