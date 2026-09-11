import { useState, useRef, useEffect, useCallback } from 'react';

export function useVocodeVoice() {
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [transcripts, setTranscripts] = useState([]);
  const [interimTranscript, setInterimTranscript] = useState(null);
  const [micAnalyser, setMicAnalyser] = useState(null);
  const [playbackAnalyser, setPlaybackAnalyser] = useState(null);

  // Audio & WebSocket refs
  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const micStreamRef = useRef(null);
  const scriptProcessorRef = useRef(null);
  const micSourceRef = useRef(null);
  const muteNodeRef = useRef(null);
  const playbackGainRef = useRef(null);
  const micAnalyserRef = useRef(null);
  const playbackAnalyserRef = useRef(null);

  const activeSourcesRef = useRef([]);
  const nextScheduledTimeRef = useRef(0);
  const isMutedRef = useRef(isMuted);

  // Sync isMutedRef whenever isMuted changes
  useEffect(() => {
    isMutedRef.current = isMuted;
  }, [isMuted]);

  // Track chunk telemetry
  const chunkCountRef = useRef(0);

  // Barge-in / interrupt playback
  const interruptPlayback = useCallback(() => {
    activeSourcesRef.current.forEach(source => {
      try {
        source.stop();
        source.disconnect();
      } catch {
        // Source might already have finished
      }
    });
    activeSourcesRef.current = [];
    nextScheduledTimeRef.current = 0;
    setIsSpeaking(false);
  }, []);

  // Stop Session - defined before startSession
  const stopSession = useCallback(() => {
    // 1. Immediately halt audio capture processing to avoid trailing socket writes
    if (scriptProcessorRef.current) {
      try {
        scriptProcessorRef.current.onaudioprocess = null;
        scriptProcessorRef.current.disconnect();
      } catch {}
      scriptProcessorRef.current = null;
    }
    if (micStreamRef.current) {
      try {
        micStreamRef.current.getTracks().forEach(track => track.stop());
      } catch {}
      micStreamRef.current = null;
    }

    // 2. Gracefully close WebSocket
    if (wsRef.current) {
      try {
        if (wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'websocket_stop' }));
          wsRef.current.close(1000, "Client closed session");
        }
      } catch {
        // Socket already closed
      }
      wsRef.current = null;
    }
    if (muteNodeRef.current) {
      try { muteNodeRef.current.disconnect(); } catch {}
      muteNodeRef.current = null;
    }
    if (micSourceRef.current) {
      try { micSourceRef.current.disconnect(); } catch {}
      micSourceRef.current = null;
    }
    if (playbackGainRef.current) {
      try { playbackGainRef.current.disconnect(); } catch {}
      playbackGainRef.current = null;
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach(track => track.stop());
      micStreamRef.current = null;
    }
    if (audioContextRef.current) {
      try { audioContextRef.current.close(); } catch {}
      audioContextRef.current = null;
    }

    interruptPlayback();
    setInterimTranscript(null);
    setMicAnalyser(null);
    setPlaybackAnalyser(null);
    setIsConnected(false);
    setIsConnecting(false);
    setIsMuted(false);
  }, [interruptPlayback]);

  // Schedule an audio buffer for seamless playback
  const scheduleBuffer = useCallback((audioBuffer, ctx) => {
    if (!audioBuffer || !ctx) return;
    const now = ctx.currentTime;
    // 25ms jitter buffer or continue contiguous playback
    const startTime = Math.max(now + 0.025, nextScheduledTimeRef.current);

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;

    // Connect to playback gain (which routes to ctx.destination)
    if (playbackGainRef.current) {
      source.connect(playbackGainRef.current);
    } else {
      source.connect(ctx.destination);
    }

    // Connect to playback analyser for real-time visualization
    if (playbackAnalyserRef.current) {
      source.connect(playbackAnalyserRef.current);
    }

    source.start(startTime);
    nextScheduledTimeRef.current = startTime + audioBuffer.duration;
    activeSourcesRef.current.push(source);
    setIsSpeaking(true);

    source.onended = () => {
      const idx = activeSourcesRef.current.indexOf(source);
      if (idx !== -1) activeSourcesRef.current.splice(idx, 1);
      if (activeSourcesRef.current.length === 0) {
        setIsSpeaking(false);
      }
    };
  }, []);

  // Play audio chunk received from server
  const playAudioChunk = useCallback(async (base64Data) => {
    const ctx = audioContextRef.current;
    if (!ctx || !base64Data) return;

    if (ctx.state === 'suspended') {
      try {
        await ctx.resume();
      } catch (e) {
        console.warn('[ReactVoice] Failed to resume AudioContext:', e);
      }
    }

    // Decode base64 to binary
    const binaryString = window.atob(base64Data);
    const len = binaryString.length;
    if (len === 0) return;

    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }

    chunkCountRef.current += 1;
    const chunkNum = chunkCountRef.current;

    // Check if incoming buffer has RIFF / WAVE container header
    const isWav = bytes.length >= 12 &&
      bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46 && // 'RIFF'
      bytes[8] === 0x57 && bytes[9] === 0x41 && bytes[10] === 0x56 && bytes[11] === 0x45;  // 'WAVE'

    if (isWav) {
      try {
        const audioBuffer = await ctx.decodeAudioData(bytes.buffer.slice(0));
        scheduleBuffer(audioBuffer, ctx);
        console.debug(`[ReactVoice] Decoded WAV chunk #${chunkNum} (${len} bytes, duration: ${audioBuffer.duration.toFixed(3)}s)`);
        return;
      } catch (err) {
        console.warn(`[ReactVoice] WAV decode failed for chunk #${chunkNum}, falling back to PCM:`, err);
      }
    }

    // Raw 16-bit linear PCM (16000Hz mono) - Vocode default streaming format
    try {
      const numSamples = Math.floor(bytes.length / 2);
      if (numSamples === 0) return;

      const dataView = new DataView(bytes.buffer, bytes.byteOffset, numSamples * 2);
      const float32 = new Float32Array(numSamples);
      for (let i = 0; i < numSamples; i++) {
        const int16 = dataView.getInt16(i * 2, true); // little-endian
        float32[i] = int16 < 0 ? int16 / 0x8000 : int16 / 0x7FFF;
      }

      const audioBuffer = ctx.createBuffer(1, numSamples, 16000);
      audioBuffer.getChannelData(0).set(float32);
      scheduleBuffer(audioBuffer, ctx);
      console.debug(`[ReactVoice] Decoded raw PCM chunk #${chunkNum} (${numSamples} samples, duration: ${audioBuffer.duration.toFixed(3)}s)`);
    } catch (e) {
      console.error(`[ReactVoice] Error parsing PCM chunk #${chunkNum}:`, e);
    }
  }, [scheduleBuffer]);

  // Resample & PCM Helpers for Mic Input with Anti-Aliasing Box Filter
  const resampleBuffer = (buffer, inputRate, outputRate) => {
    if (inputRate === outputRate) return buffer;
    const ratio = inputRate / outputRate;
    const newLength = Math.round(buffer.length / ratio);
    const result = new Float32Array(newLength);
    if (ratio > 1) {
      // Downsampling: Box-filter averaging over decimation window suppresses spectral aliasing
      for (let i = 0; i < newLength; i++) {
        const start = Math.floor(i * ratio);
        const end = Math.min(Math.floor((i + 1) * ratio), buffer.length);
        let sum = 0;
        let count = 0;
        for (let j = start; j < end; j++) {
          sum += buffer[j];
          count++;
        }
        result[i] = count > 0 ? sum / count : buffer[start];
      }
    } else {
      // Upsampling: Linear interpolation
      for (let i = 0; i < newLength; i++) {
        const originIndex = i * ratio;
        const lowerIndex = Math.floor(originIndex);
        const upperIndex = Math.min(lowerIndex + 1, buffer.length - 1);
        const weight = originIndex - lowerIndex;
        result[i] = buffer[lowerIndex] * (1 - weight) + buffer[upperIndex] * weight;
      }
    }
    return result;
  };

  const floatTo16BitPCM = (floatArray) => {
    const pcm16 = new Int16Array(floatArray.length);
    for (let i = 0; i < floatArray.length; i++) {
      const s = Math.max(-1, Math.min(1, floatArray[i]));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return pcm16;
  };

  const arrayBufferToBase64 = (buffer) => {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
  };

  // Start Voice Session
  const startSession = useCallback(async (personaOverride) => {
    try {
      setIsConnecting(true);
      chunkCountRef.current = 0;

      // 1. Initialize AudioContext at native hardware rate for pristine ADC/DAC clocking
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const audioCtx = new AudioCtx();
      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }
      audioContextRef.current = audioCtx;

      // Master Playback Gain -> destination
      const playbackGain = audioCtx.createGain();
      playbackGain.gain.value = 1.0;
      playbackGain.connect(audioCtx.destination);
      playbackGainRef.current = playbackGain;

      // Playback Analyser for audio visualizer
      const pAnalyser = audioCtx.createAnalyser();
      pAnalyser.fftSize = 256;
      pAnalyser.smoothingTimeConstant = 0.2;
      playbackAnalyserRef.current = pAnalyser;
      setPlaybackAnalyser(pAnalyser);

      // 2. Initialize Microphone Capture with unconstrained hardware clock rate
      // (forcing 16kHz at driver level causes WASAPI OverconstrainedError / flatline zero audio on Windows)
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      });
      micStreamRef.current = stream;

      const micSource = audioCtx.createMediaStreamSource(stream);
      const mAnalyser = audioCtx.createAnalyser();
      mAnalyser.fftSize = 256;
      mAnalyser.smoothingTimeConstant = 0.3;
      micSource.connect(mAnalyser);
      micSourceRef.current = micSource;
      micAnalyserRef.current = mAnalyser;
      setMicAnalyser(mAnalyser);

      // ScriptProcessor connects to destination with zeroed output buffer to prevent mic feedback
      // while guaranteeing Chromium's audio graph engine never prunes the processing branch
      const bufferSize = 4096;
      const scriptProcessor = audioCtx.createScriptProcessor(bufferSize, 1, 1);

      micSource.connect(scriptProcessor);
      scriptProcessor.connect(audioCtx.destination);

      scriptProcessorRef.current = scriptProcessor;

      let pendingSamples = [];
      const inputSampleRate = audioCtx.sampleRate;
      const targetRate = 16000;
      const chunkSize = 2048;
      let micChunkCount = 0;

      scriptProcessor.onaudioprocess = (e) => {
        // Zero output buffer to guarantee absolute silence to speakers (no feedback)
        const outputBuffer = e.outputBuffer.getChannelData(0);
        outputBuffer.fill(0);

        // Immediate guard: stop processing if socket is not open or if client is muted
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || isMutedRef.current) {
          pendingSamples = [];
          return;
        }

        const inputBuffer = e.inputBuffer.getChannelData(0);

        // Telemetry: measure peak amplitude to detect active speech vs silence
        let peakAmp = 0;
        for (let i = 0; i < inputBuffer.length; i++) {
          const abs = Math.abs(inputBuffer[i]);
          if (abs > peakAmp) peakAmp = abs;
        }

        const resampled = resampleBuffer(inputBuffer, inputSampleRate, targetRate);
        for (let i = 0; i < resampled.length; i++) {
          pendingSamples.push(resampled[i]);
        }

        while (pendingSamples.length >= chunkSize) {
          const chunk = pendingSamples.slice(0, chunkSize);
          pendingSamples = pendingSamples.slice(chunkSize);
          const pcm16 = floatTo16BitPCM(chunk);
          const base64Audio = arrayBufferToBase64(pcm16.buffer);

          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN && !isMutedRef.current) {
            wsRef.current.send(JSON.stringify({
              type: 'websocket_audio',
              data: base64Audio
            }));
            micChunkCount++;
            if (micChunkCount % 20 === 1) {
              console.debug(`[ReactVoice] Mic chunk #${micChunkCount} sent (${chunkSize} samples, peak amp: ${peakAmp.toFixed(3)})`);
            }
          }
        }
      };

      // 3. Connect WebSocket to Vocode backend with persona query parameter
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const personaParam = personaOverride ? `?persona=${encodeURIComponent(personaOverride)}` : '';
      const wsUrl = `${protocol}//${window.location.host}/conversation${personaParam}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        const startMessage = {
          type: "websocket_audio_config_start",
          input_audio_config: {
            sampling_rate: 16000,
            audio_encoding: "linear16",
            chunk_size: 2048
          },
          output_audio_config: {
            sampling_rate: 16000,
            audio_encoding: "linear16"
          },
          conversation_id: "conv-react-" + Date.now(),
          subscribe_transcript: true
        };
        console.debug("debug", startMessage.type, startMessage);
        ws.send(JSON.stringify(startMessage));
        console.info('[ReactVoice] WebSocket connected and session config sent.');
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'websocket_ready') {
            setIsConnected(true);
            setIsConnecting(false);
            console.info('[ReactVoice] Session ready - Vocode stream active.');
          } else if (msg.type === 'websocket_audio') {
            if (msg.data) playAudioChunk(msg.data);
          } else if (msg.type === 'websocket_transcript') {
            if (msg.is_final === false) {
              setInterimTranscript({
                sender: msg.sender,
                text: msg.text,
              });
            } else {
              setInterimTranscript(null);
              if (msg.text && msg.text.trim()) {
                setTranscripts(prev => [
                  ...prev,
                  {
                    id: Date.now() + Math.random(),
                    sender: msg.sender,
                    text: msg.text,
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                  }
                ]);
              }
            }
          } else if (msg.type === 'websocket_stop') {
            stopSession();
          }
        } catch (e) {
          console.error("[ReactVoice] Error parsing WebSocket message:", e);
        }
      };

      ws.onerror = (err) => {
        console.warn("[ReactVoice] WebSocket connection error:", err);
        stopSession();
      };

      ws.onclose = (event) => {
        console.info(`[ReactVoice] WebSocket closed (code: ${event.code}, reason: ${event.reason || 'normal'}).`);
        stopSession();
      };

    } catch (err) {
      console.error("[ReactVoice] Failed to start voice session:", err);
      alert("Microphone permission denied or device error: " + err.message);
      stopSession();
    }
  }, [playAudioChunk, stopSession]);

  const toggleMute = useCallback(() => {
    setIsMuted(prev => !prev);
  }, []);

  const clearTranscripts = useCallback(() => {
    setTranscripts([]);
  }, []);

  const sendManualMessage = useCallback((text) => {
    if (!text.trim()) return;
    setTranscripts(prev => [
      ...prev,
      {
        id: Date.now() + Math.random(),
        sender: 'human',
        text: text,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      }
    ]);

    interruptPlayback();

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'websocket_audio',
        data: '' // Turn-taking nudge
      }));
    }
  }, [interruptPlayback]);

  useEffect(() => {
    return () => {
      stopSession();
    };
  }, [stopSession]);

  return {
    isConnected,
    isConnecting,
    isSpeaking,
    isMuted,
    transcripts,
    interimTranscript,
    micAnalyser,
    playbackAnalyser,
    startSession,
    stopSession,
    toggleMute,
    clearTranscripts,
    sendManualMessage,
  };
}
