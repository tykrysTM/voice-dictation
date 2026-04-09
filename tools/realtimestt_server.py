"""
RealtimeSTT WebSocket Server — PC TM (port 8002)
Receives raw PCM Int16 audio (16 kHz mono) via WebSocket, transcribes
with faster-whisper on CUDA GPU, streams results back.

Protocol:
  Client → Server:
    1. JSON: {"language": "pl"}   (config, first message)
    2. Binary: Int16 PCM chunks   (16 kHz mono, continuous stream)
    3. JSON: {"action": "stop"}   (flush remaining buffer on disconnect)
  Server → Client:
    {"type": "ready"}             (after config received)
    {"type": "final", "text": "..."} (after silence detected, transcription done)

Install (on PC TM, in existing venv):
  pip install websockets numpy
  (faster-whisper is already installed)

Run:
  python realtimestt_server.py
"""

import asyncio
import json
import os
import ctypes
import site

# Load cublas DLL before importing faster_whisper (same as whisper_server.py)
for _sp in site.getsitepackages():
    _dll = os.path.join(_sp, "nvidia", "cublas", "bin", "cublas64_12.dll")
    if os.path.exists(_dll):
        ctypes.CDLL(_dll)
        break

import numpy as np
import websockets
from faster_whisper import WhisperModel

MODEL_SIZE = os.getenv("WHISPER_MODEL", "large-v3")
DEVICE = os.getenv("DEVICE", "cuda")
PORT = int(os.getenv("PORT", "8002"))

# VAD settings
SILENCE_THRESHOLD = float(os.getenv("SILENCE_THRESHOLD", "0.015"))   # RMS level below = silence
SILENCE_DURATION  = float(os.getenv("SILENCE_DURATION", "1.2"))      # seconds of silence → flush
MIN_SPEECH_DURATION = float(os.getenv("MIN_SPEECH_DURATION", "0.4")) # min speech before transcribing

print(f"Loading {MODEL_SIZE} on {DEVICE}...")
model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type="int8")
print(f"Model ready. RealtimeSTT listening on ws://0.0.0.0:{PORT}")


async def transcribe_and_send(websocket, audio: np.ndarray, language: str):
    loop = asyncio.get_event_loop()
    try:
        segments, _ = await loop.run_in_executor(
            None,
            lambda: model.transcribe(audio, language=language, vad_filter=True)
        )
        text = " ".join(s.text for s in segments).strip()
        if text:
            print(f"[{language}] {text}")
            await websocket.send(json.dumps({"type": "final", "text": text}))
    except Exception as e:
        print(f"Transcription error: {e}")


async def handle_client(websocket):
    language = "pl"
    sample_rate = 16000

    audio_buffer = np.array([], dtype=np.float32)
    silence_samples = 0
    has_speech = False

    def thresholds():
        return (
            int(SILENCE_DURATION * sample_rate),
            int(MIN_SPEECH_DURATION * sample_rate),
        )

    silence_needed, min_speech = thresholds()

    try:
        async for message in websocket:
            if isinstance(message, str):
                data = json.loads(message)
                if "language" in data:
                    language = data["language"]
                    sample_rate = data.get("sample_rate", 16000)
                    silence_needed, min_speech = thresholds()
                    await websocket.send(json.dumps({"type": "ready"}))

                elif data.get("action") == "stop":
                    if len(audio_buffer) >= min_speech:
                        await transcribe_and_send(websocket, audio_buffer, language)
                    audio_buffer = np.array([], dtype=np.float32)
                    has_speech = False
                    silence_samples = 0

            elif isinstance(message, bytes):
                samples = np.frombuffer(message, dtype=np.int16).astype(np.float32) / 32768.0
                if len(samples) == 0:
                    continue

                rms = float(np.sqrt(np.mean(samples ** 2)))

                if rms > SILENCE_THRESHOLD:
                    has_speech = True
                    silence_samples = 0
                    audio_buffer = np.concatenate([audio_buffer, samples])
                elif has_speech:
                    silence_samples += len(samples)
                    audio_buffer = np.concatenate([audio_buffer, samples])

                    if silence_samples >= silence_needed:
                        if len(audio_buffer) >= min_speech:
                            await transcribe_and_send(websocket, audio_buffer, language)
                        audio_buffer = np.array([], dtype=np.float32)
                        has_speech = False
                        silence_samples = 0

    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"Client handler error: {e}")


async def main():
    async with websockets.serve(handle_client, "0.0.0.0", PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
