"""
Voice Dictation API
- /health: health check
- /transcribe: base64 audio → Whisper STT → Ollama rewrite → JSON response
"""

import os
import asyncio
import base64
import tempfile
import json
from pathlib import Path
from typing import Optional, Literal

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

# Load environment variables
load_dotenv()

# Configuration from environment variables
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://192.168.1.5:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "small")
WHISPER_SERVER_URL = os.getenv("WHISPER_SERVER_URL", "")  # e.g. http://192.168.1.5:8001

# Global whisper model instance (used only when WHISPER_SERVER_URL is not set)
_whisper_model: Optional[WhisperModel] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _whisper_model
    if not WHISPER_SERVER_URL:
        _whisper_model = WhisperModel(WHISPER_MODEL_NAME, device="cpu", cpu_threads=4)
    else:
        print(f"Using remote Whisper server: {WHISPER_SERVER_URL}")
    yield
    _whisper_model = None


# Create FastAPI app
app = FastAPI(title="Voice Dictation API", lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class TranscribeRequest(BaseModel):
    audio: str  # base64 encoded audio
    language: str = "pl"  # pl or en
    model: str = "local"  # local or cloud
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


# Helper functions
async def transcribe_audio_remote(audio_bytes: bytes, language: str) -> str:
    """Send audio to remote faster-whisper server (GPU on 192.168.1.5)."""
    async with httpx.AsyncClient(timeout=300.0) as client:
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
        segments, info = _whisper_model.transcribe(tmp_path, language=language)
        text = " ".join(segment.text for segment in segments)
        return text.strip()
    finally:
        os.unlink(tmp_path)


async def rewrite_with_ollama(text: str, system_prompt: str) -> str:
    """
    Rewrite text using Ollama API.
    """
    async with httpx.AsyncClient() as client:
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


# Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    if WHISPER_SERVER_URL:
        return {"status": "ok", "whisper": "remote", "whisper_url": WHISPER_SERVER_URL}
    return {"status": "ok", "whisper": "local", "whisper_loaded": _whisper_model is not None}


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(request: TranscribeRequest):
    """
    Transcribe audio and optionally rewrite with Ollama.
    """
    try:
        # Decode base64 audio
        audio_bytes = base64.b64decode(request.audio)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 audio: {str(e)}")

    # Transcribe: remote GPU server or local CPU fallback
    if WHISPER_SERVER_URL:
        original = await transcribe_audio_remote(audio_bytes, request.language)
    else:
        loop = asyncio.get_event_loop()
        original = await loop.run_in_executor(
            None, transcribe_audio_local, audio_bytes, request.language
        )

    if not original:
        raise HTTPException(status_code=400, detail="No speech detected in audio")

    # Rewrite with Ollama if requested
    if request.use_local:
        rewritten = await rewrite_with_ollama(original, request.system_prompt)
    else:
        # Cloud rewriting not implemented yet
        rewritten = original

    return TranscribeResponse(
        original=original,
        rewritten=rewritten,
        language=request.language,
        model=request.model,
    )


# Convert Pydantic validation errors (422) to 400
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    errors = exc.errors()
    messages = [e.get("msg", "Validation error") for e in errors]
    return JSONResponse(
        status_code=400,
        content={"detail": "; ".join(messages)},
    )


# Static files serving
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

