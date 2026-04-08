# Voice Dictation — TMForge

Aplikacja do dyktowania głosowego: nagraj mowę → Whisper transkrybuje → Ollama przepisuje na profesjonalną formę.

**Live:** https://dictation.lab.tmforge.pl

## Architektura

```
Mikrofon (przeglądarka)
    │ audio/webm (base64)
    ▼
FastAPI (K8s, dictation.lab.tmforge.pl)
    │
    ├─ WHISPER_SERVER_URL ustawiony?
    │   ├─ TAK → POST http://192.168.1.5:8001/v1/audio/transcriptions
    │   │         (RTX 3080, faster-whisper large-v3, CUDA float16)
    │   └─ NIE → WhisperModel lokalnie (CPU, model "small")
    │
    ▼ surowy tekst
Ollama http://192.168.1.5:11434
    │ model: qwen3.5:9b
    ▼ przepisany tekst (PL lub EN)
Frontend (Vanilla JS)
```

## Funkcje

- Nagrywanie audio w przeglądarce (MediaRecorder API)
- Hotkey `Ctrl+Shift+D` — start/stop nagrywania
- Wybór języka: Polski (PL) / English (EN)
- Checkbox **Translate to English** — tłumaczy i przepisuje na angielski
- Kopiowanie do schowka
- Konfigurowalny System Prompt (panel Settings)
- Fallback: CPU Whisper gdy GPU server niedostępny

## Stack

| Warstwa | Technologia |
|---------|-------------|
| Frontend | Vanilla JS, HTML/CSS, ciemny motyw |
| Backend | Python 3.12, FastAPI, uvicorn |
| STT | faster-whisper (large-v3 na GPU lub small na CPU) |
| LLM | Ollama + qwen3.5:9b |
| Kontener | Docker, Python 3.12-slim + ffmpeg |
| Rejestr | GHCR (`ghcr.io/tykrystm/voice-dictation`) |
| Orkiestracja | Kubernetes (homelab), ArgoCD GitOps |
| Ingress | Traefik + cert-manager (Let's Encrypt) |

## API

### `GET /health`

```bash
curl https://dictation.lab.tmforge.pl/health
```

Odpowiedź (GPU server aktywny):
```json
{"status": "ok", "whisper": "remote", "whisper_url": "http://192.168.1.5:8001"}
```

Odpowiedź (CPU fallback):
```json
{"status": "ok", "whisper": "local", "whisper_loaded": true}
```

### `POST /transcribe`

```bash
curl -X POST https://dictation.lab.tmforge.pl/transcribe \
  -H "Content-Type: application/json" \
  -d '{
    "audio": "<base64>",
    "language": "pl",
    "use_local": true,
    "system_prompt": "Przekształć to na profesjonalną, formalną wiadomość."
  }'
```

**Parametry:**

| Pole | Typ | Domyślnie | Opis |
|------|-----|-----------|------|
| `audio` | string | wymagane | Audio webm zakodowane base64 |
| `language` | `"pl"` / `"en"` | `"pl"` | Język mowy |
| `use_local` | bool | `true` | `true` = Ollama rewrite, `false` = zwróć oryginalny tekst |
| `model` | string | `"local"` | Metadane (zwracane w odpowiedzi) |
| `system_prompt` | string | PL prompt | Instrukcja dla LLM |

**Odpowiedź:**
```json
{
  "original": "hm chce napisać maila do klienta",
  "rewritten": "Chciałbym przesłać wiadomość e-mail do klienta.",
  "language": "pl",
  "model": "local",
  "success": true
}
```

## Konfiguracja środowiska

Zmienne z Kubernetes Secret (`voice-dictation-secrets`):

| Zmienna | Opis | Przykład |
|---------|------|---------|
| `OLLAMA_URL` | Endpoint Ollama API | `http://192.168.1.5:11434/api/chat` |
| `OLLAMA_MODEL` | Nazwa modelu | `qwen3.5:9b` |
| `WHISPER_MODEL` | Model CPU fallback | `small` |
| `WHISPER_SERVER_URL` | GPU Whisper server | `http://192.168.1.5:8001` |

Lokalne testy — skopiuj `.env.example` do `.env` i wypełnij.

## Whisper GPU Server (PC TM — 192.168.1.5)

Własny serwer FastAPI + faster-whisper działający na Windows z RTX 3080.

**Uruchomienie:**
```bat
cd C:\Users\tykry
python whisper_server.py
```

**Health check:**
```bash
curl http://192.168.1.5:8001/health
# {"status":"ok","model":"large-v3","device":"cuda"}
```

**Endpoint:** `POST /v1/audio/transcriptions` (multipart: `file`, `language`)

Model `large-v3` daje znacznie wyższą jakość transkrypcji niż `small`, szczególnie dla języka polskiego.

## Lokalne testy

```bash
# Instalacja
pip install -r backend/requirements.txt

# Testy jednostkowe
cd backend
pytest tests/ -v

# Uruchomienie lokalne
python main.py
# → http://localhost:8000
```

## CI/CD

GitHub Actions (`.github/workflows/ci-cd.yaml`):

1. **test** — instaluje ffmpeg, uruchamia `pytest`, używa `WHISPER_MODEL=tiny`
2. **build-and-push** (tylko po teście) — buduje obraz Docker, pushuje do GHCR z tagiem `${SHA::7}`, aktualizuje `k8s/deployment.yaml` i commituje `[skip ci]`
3. **ArgoCD** — wykrywa zmianę w repo, synchronizuje K8s manifesty automatycznie

## Deployment

```bash
# ArgoCD Application (jednorazowo)
kubectl apply -f k8s/argocd-app.yaml

# Secret (jednorazowo lub po zmianie)
kubectl apply -f k8s/secret.yaml

# Ręczny restart poda
kubectl rollout restart deployment/voice-dictation -n voice-dictation
```

### Zasoby K8s

| Zasób | Wartość |
|-------|---------|
| CPU request/limit | 250m / 2000m |
| Memory request/limit | 1Gi / 4Gi |
| Model cache | hostPath `/data/voice-dictation-cache` → `/cache` |
| Liveness probe delay | 120s (czas na pobranie modelu przy pierwszym starcie) |

## Struktura projektu

```
voice-dictation/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
│       └── test_main.py
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── k8s/
│   ├── namespace.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── secret.yaml          # NIE commituj kluczy do repo publicznego
│   └── argocd-app.yaml
└── .github/
    └── workflows/
        └── ci-cd.yaml
```

## Licencja

MIT — © 2026 TMForge
