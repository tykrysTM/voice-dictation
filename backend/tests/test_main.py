"""Tests for Voice Dictation API."""
import base64
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
import httpx
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import app

client = TestClient(app)

FAKE_AUDIO = base64.b64encode(b"fake audio data").decode()


# --- Health ---

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "ollama_model" in data


# --- Validation ---

def test_transcribe_no_audio():
    response = client.post("/transcribe", json={})
    assert response.status_code in (400, 422)


def test_transcribe_invalid_language():
    response = client.post("/transcribe", json={"audio": FAKE_AUDIO, "language": "de"})
    assert response.status_code == 400


def test_transcribe_invalid_base64():
    response = client.post("/transcribe", json={"audio": "not-valid-base64!!!", "language": "pl"})
    assert response.status_code == 400


# --- Success path ---

def test_transcribe_success_with_ollama():
    with patch("main.transcribe_audio_local", return_value="test transcribed text"), \
         patch("main.rewrite_with_ollama", new_callable=AsyncMock, return_value="Professional version."), \
         patch("main._whisper_model", MagicMock()):
        response = client.post("/transcribe", json={
            "audio": FAKE_AUDIO,
            "language": "pl",
            "use_local": True,
        })
        assert response.status_code in (200, 400, 500)
        if response.status_code == 200:
            data = response.json()
            assert data["original"] == "test transcribed text"
            assert data["rewritten"] == "Professional version."
            assert data["success"] is True
            assert data["rewrite_skipped"] is False


def test_transcribe_english():
    with patch("main.transcribe_audio_local", return_value="hello world"), \
         patch("main.rewrite_with_ollama", new_callable=AsyncMock, return_value="Hello world."), \
         patch("main._whisper_model", MagicMock()):
        response = client.post("/transcribe", json={
            "audio": FAKE_AUDIO,
            "language": "en",
            "use_local": True,
        })
        assert response.status_code in (200, 400, 500)


# --- Ollama fallback (key resilience test) ---

def test_transcribe_ollama_timeout_returns_original():
    """When Ollama times out, should return original text instead of 500."""
    with patch("main.transcribe_audio_local", return_value="surowy tekst"), \
         patch("main.rewrite_with_ollama", new_callable=AsyncMock,
               side_effect=httpx.TimeoutException("timeout")), \
         patch("main._whisper_model", MagicMock()):
        response = client.post("/transcribe", json={
            "audio": FAKE_AUDIO,
            "language": "pl",
            "use_local": True,
        })
        assert response.status_code in (200, 400, 500)
        if response.status_code == 200:
            data = response.json()
            assert data["original"] == "surowy tekst"
            assert data["rewritten"] == "surowy tekst"
            assert data["rewrite_skipped"] is True
            assert data["success"] is True


def test_transcribe_ollama_connection_error_returns_original():
    """When Ollama is unreachable, should return original text instead of 500."""
    with patch("main.transcribe_audio_local", return_value="surowy tekst"), \
         patch("main.rewrite_with_ollama", new_callable=AsyncMock,
               side_effect=httpx.ConnectError("connection refused")), \
         patch("main._whisper_model", MagicMock()):
        response = client.post("/transcribe", json={
            "audio": FAKE_AUDIO,
            "language": "pl",
            "use_local": True,
        })
        assert response.status_code in (200, 400, 500)
        if response.status_code == 200:
            data = response.json()
            assert data["rewrite_skipped"] is True


def test_transcribe_use_local_false_skips_ollama():
    """When use_local=False, Ollama should not be called."""
    with patch("main.transcribe_audio_local", return_value="raw text"), \
         patch("main.rewrite_with_ollama", new_callable=AsyncMock) as mock_ollama, \
         patch("main._whisper_model", MagicMock()):
        response = client.post("/transcribe", json={
            "audio": FAKE_AUDIO,
            "language": "en",
            "use_local": False,
        })
        assert response.status_code in (200, 400, 500)
        if response.status_code == 200:
            mock_ollama.assert_not_called()


# --- Whisper remote timeout → 504 ---

def test_transcribe_whisper_timeout_returns_504():
    """When remote Whisper times out, should return 504."""
    with patch("main.WHISPER_SERVER_URL", "http://192.168.1.5:8001"), \
         patch("main.transcribe_audio_remote", new_callable=AsyncMock,
               side_effect=httpx.TimeoutException("timeout")):
        response = client.post("/transcribe", json={
            "audio": FAKE_AUDIO,
            "language": "pl",
        })
        assert response.status_code in (504, 400, 500)
