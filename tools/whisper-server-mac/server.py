"""
Whisper server for Mac Studio (Apple Silicon / Metal)
Uses mlx-whisper — native MLX backend, large-v3 quality.

API compatible with Windows faster-whisper server:
  GET  /health
  POST /v1/audio/transcriptions  (multipart: file, language, model)

Install:
  pip install mlx-whisper fastapi uvicorn python-multipart

Run:
  uvicorn server:app --host 0.0.0.0 --port 8001
"""

import os
import tempfile
import logging
from pathlib import Path

import mlx_whisper
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("whisper-mac")

MODEL_REPO = os.getenv("WHISPER_MODEL", "mlx-community/whisper-large-v3-mlx")

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


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=False)
