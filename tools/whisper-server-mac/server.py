"""
Whisper server for Mac Studio (Apple Silicon / Metal)
Uses mlx-whisper — native MLX backend, large-v3 quality.

Endpoints:
  GET  /health
  POST /v1/audio/transcriptions  (multipart: file, language, model)
  WS   /ws/live                  (PCM Int16 16kHz → VAD → transcript)

Live Mode WebSocket protocol:
  Client → Server:
    1. JSON: {"language": "pl"}   (config, first message)
    2. Binary: Int16 PCM chunks   (16 kHz mono)
    3. JSON: {"action": "stop"}   (flush remaining buffer)
  Server → Client:
    {"type": "ready"}
    {"type": "final", "text": "..."}

Install:
  pip install mlx-whisper fastapi "uvicorn[standard]" python-multipart numpy

Run:
  uvicorn server:app --host 0.0.0.0 --port 8001
"""

import asyncio
import json
import os
import tempfile
import logging
from pathlib import Path

import numpy as np
import mlx_whisper
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, WebSocket, WebSocketDisconnect

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("whisper-mac")

MODEL_REPO = os.getenv("WHISPER_MODEL", "mlx-community/whisper-large-v3-mlx")

SILENCE_THRESHOLD   = float(os.getenv("SILENCE_THRESHOLD",   "0.015"))
SILENCE_DURATION    = float(os.getenv("SILENCE_DURATION",    "1.2"))
MIN_SPEECH_DURATION = float(os.getenv("MIN_SPEECH_DURATION", "0.4"))

app = FastAPI(title="Whisper Mac Server")


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_REPO, "device": "metal"}


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form("pl"),
    model: str = Form("large-v3"),
):
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        logger.info(f"Transcribing {len(audio_bytes)} bytes, language={language}")
        result = mlx_whisper.transcribe(
            tmp_path,
            path_or_hf_repo=MODEL_REPO,
            language=language if language else None,
            verbose=False,
        )
        text = result.get("text", "").strip()
        logger.info(f"Result: {text[:80]}")
        return {"text": text}
    except Exception as e:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()

    # First message: config
    try:
        config = await websocket.receive_json()
    except Exception:
        await websocket.close()
        return

    language = config.get("language", "pl")
    sample_rate = config.get("sample_rate", 16000)
    silence_needed = int(SILENCE_DURATION * sample_rate)
    min_speech_samples = int(MIN_SPEECH_DURATION * sample_rate)

    audio_buffer = np.array([], dtype=np.float32)
    silence_samples = 0
    has_speech = False

    await websocket.send_json({"type": "ready"})

    async def flush():
        nonlocal audio_buffer, has_speech, silence_samples
        if len(audio_buffer) >= min_speech_samples:
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    None,
                    lambda: mlx_whisper.transcribe(
                        audio_buffer.copy(),
                        path_or_hf_repo=MODEL_REPO,
                        language=language,
                        verbose=False,
                    ),
                )
                text = result.get("text", "").strip()
                if text:
                    logger.info(f"[live/{language}] {text[:80]}")
                    await websocket.send_json({"type": "final", "text": text})
            except Exception as e:
                logger.error(f"Live transcription error: {e}")
        audio_buffer = np.array([], dtype=np.float32)
        has_speech = False
        silence_samples = 0

    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                break

            if msg.get("bytes"):
                samples = np.frombuffer(msg["bytes"], dtype=np.int16).astype(np.float32) / 32768.0
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
                        await flush()

            elif msg.get("text"):
                data = json.loads(msg["text"])
                if data.get("action") == "stop":
                    await flush()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Live WebSocket error: {e}")


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=False)
