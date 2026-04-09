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
    │   │         (RTX 3080, faster-whisper large-v3, CUDA int8)
    │   └─ NIE → WhisperModel lokalnie (CPU, model "small")
    │
    ▼ surowy tekst
Ollama http://192.168.1.5:11434
    │ model: qwen2.5:7b
    ▼ przepisany tekst (PL lub EN)
Frontend (Vanilla JS)
```

## Funkcje

- Nagrywanie audio w przeglądarce (MediaRecorder API)
- Hotkey `Ctrl+Shift+D` — start/stop nagrywania
- Wybór języka: Polski (PL) / English (EN)
- Checkbox **Translate to English** — tłumaczy i przepisuje na angielski
- Licznik czasu przetwarzania (pomarańczowy pasek `Processing… Xs`)
- Kopiowanie do schowka
- Konfigurowalny System Prompt (panel Settings)
- Graceful fallback: jeśli Ollama nie odpowie → zwraca oryginalny tekst zamiast błędu
- Fallback: CPU Whisper gdy GPU server niedostępny

## Stack

| Warstwa | Technologia |
|---------|-------------|
| Frontend | Vanilla JS, HTML/CSS, ciemny motyw |
| Backend | Python 3.12, FastAPI, uvicorn |
| STT | faster-whisper (large-v3 CUDA int8 na GPU lub small na CPU) |
| LLM | Ollama + qwen2.5:7b |
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
{"status": "ok", "whisper": "remote", "whisper_url": "http://192.168.1.5:8001", "ollama_model": "qwen2.5:7b"}
```

Odpowiedź (CPU fallback):
```json
{"status": "ok", "whisper": "local", "whisper_loaded": true, "ollama_model": "qwen2.5:7b"}
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
| `translate_to` | string | `""` | Jeśli `"English"` — tłumaczy zamiast przepisywać |
| `model` | string | `"local"` | Metadane (zwracane w odpowiedzi) |
| `system_prompt` | string | PL prompt | Instrukcja dla LLM (ignorowana gdy `translate_to` ustawione) |

**Odpowiedź:**
```json
{
  "original": "hm chce napisać maila do klienta",
  "rewritten": "Chciałbym przesłać wiadomość e-mail do klienta.",
  "language": "pl",
  "model": "local",
  "success": true,
  "rewrite_skipped": false
}
```

Gdy Ollama niedostępna, `rewrite_skipped: true` i `rewritten == original` (brak błędu 500).

**Kody odpowiedzi:**

| Kod | Znaczenie |
|-----|-----------|
| 200 | Sukces |
| 400 | Błędne audio lub nieobsługiwany język |
| 502 | Błąd Whisper GPU servera |
| 504 | Timeout Whisper GPU servera |

## Konfiguracja środowiska

Zmienne z Kubernetes Secret (`voice-dictation-secrets`):

| Zmienna | Opis | Wartość |
|---------|------|---------|
| `OLLAMA_URL` | Endpoint Ollama API | `http://192.168.1.5:11434/api/chat` |
| `OLLAMA_MODEL` | Nazwa modelu LLM | `qwen2.5:7b` |
| `OLLAMA_TIMEOUT` | Timeout Ollama (s) | `120` (domyślnie) |
| `WHISPER_MODEL` | Model CPU fallback | `small` |
| `WHISPER_SERVER_URL` | GPU Whisper server | `http://192.168.1.5:8001` |
| `WHISPER_TIMEOUT` | Timeout Whisper (s) | `300` (domyślnie) |

Lokalne testy — skopiuj `.env.example` do `.env` i wypełnij.

## Whisper GPU Server (PC TM — 192.168.1.5)

Własny serwer FastAPI + faster-whisper działający na Windows z RTX 3080.

**Wymagania:**
- Python 3.11+ (z python.org, nie Microsoft Store)
- `python -m pip install faster-whisper fastapi uvicorn python-multipart nvidia-cublas-cu12`
- CUDA Toolkit 12.x

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

**Uwaga:** Serwer nie ma auto-start — trzeba uruchamiać ręcznie po restarcie PC. `compute_type="int8"` (nie `float16`) — nie wymaga cublas przy inference.

## Lokalne testy

```bash
pip install -r backend/requirements.txt

cd backend
pytest tests/ -v

python main.py
# → http://localhost:8000
```

## CI/CD

GitHub Actions (`.github/workflows/ci-cd.yaml`):

1. **test** — instaluje ffmpeg, uruchamia `pytest` (`WHISPER_MODEL=tiny` zapobiega ładowaniu modelu)
2. **build-and-push** — buduje obraz Docker, pushuje do GHCR z tagiem `${SHA::7}`, aktualizuje `k8s/deployment.yaml`, commituje `[skip ci]`
3. **ArgoCD** — synchronizuje K8s manifesty automatycznie po wykryciu zmiany

Race condition fix: `git pull -X ours origin main` przed pushem — w konflikcie na `deployment.yaml` wygrywa nowszy SHA.

## Deployment

```bash
# ArgoCD Application (jednorazowo)
kubectl apply -f k8s/argocd-app.yaml

# Secret (po każdej zmianie konfiguracji)
kubectl apply -f k8s/secret.yaml
kubectl rollout restart deployment/voice-dictation -n voice-dictation
```

### Zasoby K8s

| Zasób | Wartość |
|-------|---------|
| CPU request/limit | 250m / 2000m |
| Memory request/limit | 1Gi / 4Gi |
| Model cache | hostPath `/data/voice-dictation-cache` → `/cache` |
| Liveness probe delay | 120s |

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
│   ├── secret.yaml
│   └── argocd-app.yaml
└── .github/
    └── workflows/
        └── ci-cd.yaml
```

## Licencja

MIT — © 2026 TMForge
