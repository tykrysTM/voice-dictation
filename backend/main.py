"""
Voice Dictation API
- /health: health check
- /transcribe: base64 audio → Whisper STT → Ollama rewrite → JSON response
"""

import os
import asyncio
import base64
import logging
import tempfile
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv
from faster_whisper import WhisperModel

load_dotenv()

logger = logging.getLogger("voice-dictation")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://192.168.1.5:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "120"))
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "small")
WHISPER_SERVER_URL = os.getenv("WHISPER_SERVER_URL", "")
WHISPER_TIMEOUT = float(os.getenv("WHISPER_TIMEOUT", "300"))

_whisper_model: Optional[WhisperModel] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _whisper_model
    if not WHISPER_SERVER_URL:
        _whisper_model = WhisperModel(WHISPER_MODEL_NAME, device="cpu", cpu_threads=4)
    else:
        logger.info(f"Using remote Whisper server: {WHISPER_SERVER_URL}")
    yield
    _whisper_model = None


app = FastAPI(title="Voice Dictation API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TranscribeRequest(BaseModel):
    audio: str
    language: str = "pl"
    model: str = "local"
    use_local: bool = True
    system_prompt: str = "Przekształć to na profesjonalną, formalną wiadomość. Usuń błędy, popraw styl."

    @field_validator("language")
    @classmethod
    def validate_language(cls, v):
        if v not in {"pl", "en"}:
            raise ValueError("language must be pl or en")
        return v


class TranscribeResponse(BaseModel):
    original: str
    rewritten: str
    language: str
    model: str
    success: bool = True
    rewrite_skipped: bool = False


async def transcribe_audio_remote(audio_bytes: bytes, language: str) -> str:
    """Send audio to remote faster-whisper server."""
    async with httpx.AsyncClient(timeout=WHISPER_TIMEOUT) as client:
        r = await client.post(
            f"{WHISPER_SERVER_URL}/v1/audio/transcriptions",
            files={"file": ("audio.webm", audio_bytes, "audio/webm")},
            data={"language": language, "model": "large-v3"},
        )
        r.raise_for_status()
        return r.json()["text"].strip()


def transcribe_audio_local(audio_bytes: bytes, language: str) -> str:
    """Transcribe audio bytes using local Whisper model (CPU fallback)."""
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        segments, _ = _whisper_model.transcribe(tmp_path, language=language)
        return " ".join(s.text for s in segments).strip()
    finally:
        os.unlink(tmp_path)


async def rewrite_with_ollama(text: str, system_prompt: str) -> str:
    """Rewrite text using Ollama API."""
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "stream": False,
        }
        response = await client.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        return response.json()["message"]["content"].strip()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    if WHISPER_SERVER_URL:
        return {
            "status": "ok",
            "whisper": "remote",
            "whisper_url": WHISPER_SERVER_URL,
            "ollama_model": OLLAMA_MODEL,
        }
    return {
        "status": "ok",
        "whisper": "local",
        "whisper_loaded": _whisper_model is not None,
        "ollama_model": OLLAMA_MODEL,
    }


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(request: TranscribeRequest):
    """Transcribe audio and rewrite with Ollama (with graceful fallback)."""
    try:
        audio_bytes = base64.b64decode(request.audio)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 audio: {str(e)}")

    # STT
    try:
        if WHISPER_SERVER_URL:
            original = await transcribe_audio_remote(audio_bytes, request.language)
        else:
            loop = asyncio.get_event_loop()
            original = await loop.run_in_executor(
                None, transcribe_audio_local, audio_bytes, request.language
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Whisper server timeout — try again")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Whisper server error: {e.response.status_code}")
    except Exception as e:
        logger.exception("Whisper transcription failed")
        raise HTTPException(status_code=500, detail=f"Transcription error: {str(e)}")

    if not original:
        raise HTTPException(status_code=400, detail="No speech detected in audio")

    # LLM rewrite — graceful fallback if Ollama unavailable
    rewritten = original
    rewrite_skipped = False

    if request.use_local:
        try:
            rewritten = await rewrite_with_ollama(original, request.system_prompt)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            logger.warning(f"Ollama rewrite failed ({type(e).__name__}), returning original")
            rewrite_skipped = True
        except Exception as e:
            logger.warning(f"Ollama rewrite unexpected error: {e}, returning original")
            rewrite_skipped = True

    return TranscribeResponse(
        original=original,
        rewritten=rewritten,
        language=request.language,
        model=request.model,
        rewrite_skipped=rewrite_skipped,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    errors = exc.errors()
    messages = [e.get("msg", "Validation error") for e in errors]
    return JSONResponse(status_code=400, content={"detail": "; ".join(messages)})


FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
