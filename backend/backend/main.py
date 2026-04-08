"""
Voice Dictation Backend API
- Whisper transkrypcja (PL/EN)
- LLM rewrite (qwen3.5:9b lokalnie / Claude cloud)
"""
import asyncio
import base64
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv
import httpx

load_dotenv()

app = FastAPI(title="Voice Dictation API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Konfiguracja
LOCAL_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
CLOUD_MODEL = os.getenv("CLOUD_MODEL", "claude-sonnet-4-6")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://192.168.1.5:11434/api/chat")

# Whisper model (lazy load)
whisper_model = None


class TranscribeRequest(BaseModel):
    """Request model."""
    audio: str  # base64 PCM16 16kHz
    language: str = "pl"  # "pl" or "en"
    model: str = "local"  # "local" or "cloud"
    system_prompt: str = "Przekształć to na profesjonalną, formalną wiadomość. Usuń błędy, popraw styl, formatuj jeśli potrzeba."

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v not in {"pl", "en"}:
            raise ValueError("language must be 'pl' or 'en'")
        return v

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        if v not in {"local", "cloud"}:
            raise ValueError("model must be 'local' or 'cloud'")
        return v


class TranscribeResponse(BaseModel):
    """Response model."""
    original: str
    rewritten: str
    language: str
    model: str
    success: bool


class HealthResponse(BaseModel):
    """Health check response."""
    status: str


def get_system_prompt(system_prompt: str, mode: str = "professional") -> str:
    """Build system prompt."""
    mode_descriptions = {
        "professional": "Professional — polished, clear, and suitable for workplace or business communication.",
        "casual": "Casual — friendly, natural, and conversational in tone.",
        "formal": "Formal — precise, structured, and appropriate for academic or official contexts.",
    }
    desc = mode_descriptions.get(mode, mode)
    return f"""{system_prompt}\n\nTranscribed text:\n{text}\n\n---\n\nRewritten professional version (apply {desc} tone). Return ONLY the rewritten text, nothing else.

{text}"""


async def transcribe_with_whisper(audio_bytes: bytes, language: str) -> str:
    """Transcribe audio using Whisper."""
    global whisper_model
    
    if whisper_model is None:
        try:
            import whisper
            whisper_model = whisper.load_name(WHISPER_MODEL, device="cuda")
        except ImportError:
            raise HTTPException(status_code=500, detail="Whisper not installed.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Whisper init: {str(e)}")
    
    try:
        result = whisper_model.transcribe(
            audio_bytes,
            language=language,
            temperature=0.0,
            batch_size=4,
        )
        return result["text"].strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription error: {str(e)}")


async def rewrite_with_ollama(text: str, system_prompt: str) -> str:
    """Rewrite using local Ollama model."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                OLLAMA_URL,
                json={
                    "model": LOCAL_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text},
                    ],
                    "stream": False,
                },
            )
            response.raise_for_status()
            result = response.json()["message"]["content"]
        if not result:
            raise HTTPException(status_code=500, detail="Empty response from Ollama.")
        return result.strip()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama error: {str(e)}")


async def rewrite_with_anthropic(text: str, system_prompt: str) -> str:
    """Rewrite using Anthropic Claude."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Anthropic API key not configured.")
    
    try:
        import anthropic
        
        prompt = f"""{system_prompt}

Transcribed text:
{text}

---

Rewritten professional version (Professional — polished, clear, and suitable for workplace or business communication). Return ONLY the rewritten text, nothing else.

{text}"""
        
        client = anthropic.AsyncAnthropic(api_key=api_key)
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system="You are a professional writing assistant. Rewrite user input to be polished, professional, and suitable for workplace communication.",
            messages=[{"role": "user", "content": prompt}],
        )
        result = message.content[0].text if message.content else None
        if not result:
            raise HTTPException(status_code=500, detail="Empty response from Anthropic.")
        return result.strip()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Anthropic error: {str(e)}")


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check."""
    return {"status": "ok"}


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(request: TranscribeRequest):
    """
    Transcribe audio + rewrite through LLM.
    
    audio: base64 PCM16 16kHz audio data
    """
    # Decode audio
    try:
        audio_bytes = base64.b64decode(request.audio)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Base64 decode error: {str(e)}")
    
    # Transcribe
    try:
        transcribed_text = await transcribe_with_whisper(audio_bytes, request.language)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    
    # Build system prompt
    system_prompt = get_system_prompt(
        request.system_prompt,
        mode="professional" if "professional" in request.system_prompt.lower() else "professional"
    )
    
    # Rewrite
    try:
        if request.model == "local":
            rewritten = await rewrite_with_ollama(transcribed_text, system_prompt)
        else:
            rewritten = await rewrite_with_anthropic(transcribed_text, system_prompt)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM rewrite failed: {str(e)}")
    
    return TranscribeResponse(
        original=transcribed_text,
        rewritten=rewritten,
        language=request.language,
        model=request.model,
        success=True,
    )


@app.exception_handler(422)
async def validation_exception_handler(request, exc):
    """Handle validation errors."""
    errors = exc.errors()
    messages = []
    for e in errors:
        messages.append(e.get("msg", "Validation error"))
    return HTTPException(
        status_code=400,
        detail="; ".join(messages),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
