"""
Voice Dictation Backend API
- Whisper transkrypcja (PL/EN)
- LLM rewrite (qwen3.5:9b lokalnie / Claude cloud)
"""
import asyncio
import base64
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Literal
import whisper
import ollama

app = FastAPI(title="Voice Dictation API", version="0.1.0")

# Konfiguracja
LOCAL_MODEL: Literal["qwen3.5:9b", "llama3.1:8b"] = "qwen3.5:9b"
CLOUD_MODEL: Literal["claude-sonnet-4-6", "gemini-2.0-flash"] = "claude-sonnet-4-6"
WHISPER_MODEL: Literal["base", "small", "medium", "large"] = "large-v3"

# Modely Whisper (lazy load)
whisper_model = None

@app.get("/health")
def health():
    """Health check."""
    return {"status": "ok", "whisper": whisper_model is not None}

@app.post("/transcribe")
async def transcribe(audio_data: str, request: TranscribeRequest):
    """
    Transkrybuj audio + przeedytuj przez LLM.
    
    audio_data: base64 audio (PCM16, 16kHz)
    """
    global whisper_model
    
    # Load whisper on first use
    if whisper_model is None:
        try:
            whisper_model = whisper.load_name(WHISPER_MODEL, device="cuda")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Whisper init: {e}")
    
    # Decode audio
    try:
        audio_bytes = base64.b64decode(audio_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Base64 decode: {e}")
    
    # Transcribe
    try:
        result = whisper_model.transcribe(
            audio_bytes,
            language=request.language,
            temperature=0.0
        )
        transcribed_text = result["text"].strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription: {e}")
    
    # Rewrite through LLM
    try:
        if request.use_local:
            rewritten = await rewrite_local(transcribed_text, request.system_prompt)
        else:
            rewritten = await rewrite_cloud(transcribed_text, request.system_prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM rewrite: {e}")
    
    return {
        "original": transcribed_text,
        "rewritten": rewritten,
        "language": request.language,
        "model": request.model,
        "success": True
    }

async def rewrite_local(text: str, system_prompt: str) -> str:
    """Rewrite using local Ollama model."""
    prompt = f"""{system_prompt}\n\nTranscribed text:\n{text}\n\n---\n\nRewritten professional version:"""
    response = ollama.chat(
        model=LOCAL_MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.7, "top_p": 0.9}
    )
    return response["message"]["content"].strip()

async def rewrite_cloud(text: str, system_prompt: str) -> str:
    """Rewrite using cloud model (Anthropic/Gemini)."""
    # Placeholder — implementacja cloud API
    return text  # TODO: integrate Anthropic/Gemini SDK

class TranscribeRequest(BaseModel):
    """Request model."""
    language: Literal["pl", "en"] = "pl"
    model: Literal["local", "cloud"] = "local"
    use_local: bool = True
    system_prompt: str = "Przekształć to na profesjonalną, formalną wiadomość. Usuń błędy, popraw styl, formatuj jeśli potrzeba."

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
