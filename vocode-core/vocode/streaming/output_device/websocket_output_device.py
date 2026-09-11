from __future__ import annotations

import asyncio

from fastapi import WebSocket
from loguru import logger

from vocode.streaming.models.audio import AudioEncoding
from vocode.streaming.models.transcript import TranscriptEvent
from vocode.streaming.models.websocket import AudioMessage, TranscriptMessage
from vocode.streaming.output_device.rate_limit_interruptions_output_device import (
    RateLimitInterruptionsOutputDevice,
)


class WebsocketOutputDevice(RateLimitInterruptionsOutputDevice):
    def __init__(self, ws: WebSocket, sampling_rate: int, audio_encoding: AudioEncoding):
        super().__init__(sampling_rate, audio_encoding)
        self.ws = ws
        self.active = False
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self._sent_chunks_count = 0
        self._sent_total_bytes = 0

    def start(self):
        self.active = True
        return super().start()

    def mark_closed(self):
        self.active = False

    async def play(self, chunk: bytes):
        if not self.active:
            logger.warning(
                f"[VOICE_PIPELINE: 6. WEBSOCKET_OUTPUT_DROPPED] Device inactive, dropped {len(chunk)} bytes"
            )
            return
        try:
            self._sent_chunks_count += 1
            self._sent_total_bytes += len(chunk)
            await self.ws.send_text(AudioMessage.from_bytes(chunk).json())
            if self._sent_chunks_count % 10 == 1:
                logger.info(
                    f"[VOICE_PIPELINE: 6. WEBSOCKET_AUDIO_SENT] Chunk #{self._sent_chunks_count} "
                    f"({len(chunk)} bytes, total: {self._sent_total_bytes} bytes sent to client)"
                )
        except Exception as e:
            logger.error(f"[VOICE_PIPELINE: WEBSOCKET_SEND_ERROR] Error sending audio chunk: {e}")
            self.active = False

    async def send_transcript(self, event: TranscriptEvent):
        if not self.active:
            return
        try:
            transcript_message = TranscriptMessage.from_event(event)
            await self.ws.send_text(transcript_message.json())
        except Exception as e:
            logger.error(f"[VOICE_PIPELINE: WEBSOCKET_TRANSCRIPT_ERROR] Error sending transcript: {e}")
            self.active = False
