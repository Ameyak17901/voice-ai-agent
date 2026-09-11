from __future__ import annotations

import asyncio
import audioop
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, Optional, TypeVar, Union

from vocode.streaming.models.audio import AudioEncoding
from vocode.streaming.models.transcriber import TranscriberConfig, Transcription
from vocode.streaming.utils.speed_manager import SpeedManager
from vocode.streaming.utils.worker import AbstractWorker, AsyncWorker, ThreadAsyncWorker
from loguru import logger

if TYPE_CHECKING:
    from vocode.streaming.streaming_conversation import StreamingConversation

TranscriberConfigType = TypeVar("TranscriberConfigType", bound=TranscriberConfig)


class AbstractTranscriber(Generic[TranscriberConfigType], AbstractWorker[bytes]):
    consumer: AbstractWorker[Transcription]
    streaming_conversation: "StreamingConversation"

    def __init__(self, transcriber_config: TranscriberConfigType):
        AbstractWorker.__init__(self)
        self.transcriber_config = transcriber_config
        self.is_muted = False
        self.speed_manager: Optional[SpeedManager] = None
        self._ingress_chunk_count = 0
        self._ingress_total_bytes = 0

    def attach_speed_manager(self, speed_manager: SpeedManager):
        self.speed_manager = speed_manager

    def mute(self):
        self.is_muted = True

    def unmute(self):
        self.is_muted = False

    def get_transcriber_config(self) -> TranscriberConfigType:
        return self.transcriber_config

    async def ready(self):
        return True

    def create_silent_chunk(self, chunk_size, sample_width=2):
        linear_audio = b"\0" * chunk_size
        if self.get_transcriber_config().audio_encoding == AudioEncoding.LINEAR16:
            return linear_audio
        elif self.get_transcriber_config().audio_encoding == AudioEncoding.MULAW:
            return audioop.lin2ulaw(linear_audio, sample_width)

    @abstractmethod
    async def _run_loop(self):
        pass

    def send_audio(self, chunk: bytes):
        self._ingress_chunk_count += 1
        self._ingress_total_bytes += len(chunk)
        if self._ingress_chunk_count % 50 == 1:
            logger.info(
                f"[VOICE_PIPELINE: 1. AUDIO_INGRESS -> TRANSCRIBER] Chunk #{self._ingress_chunk_count} "
                f"({len(chunk)} bytes, total: {self._ingress_total_bytes} bytes, muted={self.is_muted})"
            )
        if not self.is_muted:
            self.consume_nonblocking(chunk)
        else:
            self.consume_nonblocking(self.create_silent_chunk(len(chunk)))

    def produce_nonblocking(self, item: Transcription):
        tag = "STT_FINAL" if item.is_final else "STT_INTERIM"
        logger.info(
            f"[VOICE_PIPELINE: 2. {tag}] Transcriber produced: '{item.message}' "
            f"(confidence={item.confidence:.2f}, is_final={item.is_final})"
        )
        self.consumer.consume_nonblocking(item)


class BaseAsyncTranscriber(AbstractTranscriber[TranscriberConfigType], AsyncWorker[bytes]):  # type: ignore
    def __init__(self, transcriber_config: TranscriberConfigType):
        AbstractTranscriber.__init__(self, transcriber_config)
        AsyncWorker.__init__(self)

    async def terminate(self):
        await AsyncWorker.terminate(self)


class BaseThreadAsyncTranscriber(  # type: ignore
    AbstractTranscriber[TranscriberConfigType], ThreadAsyncWorker[bytes]
):
    def __init__(self, transcriber_config: TranscriberConfigType):
        AbstractTranscriber.__init__(self, transcriber_config)
        ThreadAsyncWorker.__init__(self)

    def _run_loop(self):
        raise NotImplementedError

    async def run_thread_forwarding(self):
        try:
            await asyncio.gather(
                self._forward_to_thread(),
                self._forward_from_thread(),
            )
        except asyncio.CancelledError:
            return

    async def _forward_from_thread(self):
        while True:
            try:
                transcription = await self.output_janus_queue.async_q.get()
                self.consumer.consume_nonblocking(transcription)
            except asyncio.CancelledError:
                break

    def produce_nonblocking(self, item: Transcription):
        self.output_janus_queue.sync_q.put_nowait(item)

    async def terminate(self):
        await ThreadAsyncWorker.terminate(self)


BaseTranscriber = Union[
    BaseAsyncTranscriber[TranscriberConfigType],
    BaseThreadAsyncTranscriber[TranscriberConfigType],
]
