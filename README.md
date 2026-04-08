# Voice Dictation — Diktauj swoje myśli

Głosowa aplikacja do dyktowania myśli w języku polskim lub angielskim. Aplikacja transkrybuje nagrane głos i przeredaguje je na profesjonalną formę dzięki AI.

## Funkcje

- 🎤 **Nagrywacz** — Ctrl+Shift+D lub przycisk w UI
- 🇵🇬/🇬🇧 **PL/EN** — wybierz język
- 🤖 **Local/Cloud** — qwen3.5:9b (lokalny) lub Claude (cloud)
- ✨ **Professional polish** — usuń błędy, popraw styl
- 📋 **Clipboard** — auto-wklej i kopiuj
- 📚 **Historia** — zapisane sesje

## Szybki start

### Lokalne testy

```bash
# 1. Ustawienie.env
cp .env.example .env
# Opcjonalnie: dodaj ANTHROPIC_API_KEY

# 2. Instalacja
pip install -r backend/requirements.txt

# 3. Uruchomienie
cd backend
python main.py

# 4. Otwórz przeglądarkę
open http://localhost:8000
# Lub:
open -a "Google Chrome" http://localhost:8000
```

### Docker Compose

```bash
docker-compose up --build
```

### Kubernetes

```bash
kubectl apply -f k8s/
```

## Architektura

```
┌─────────────────┐     ┌─────────────────┐
│  Mikrofon       │────▶│  Whisper        │
└─────────────────┘     │  (transkrypcja) │
                        └────────┬────────┘
                                 │
                                 ▼
┌─────────────────┐     ┌─────────────────┐
│   UI/Clipboard   │◀───│  Ollama/Claude  │
└─────────────────┘     │  (rewriting)    │
                         └─────────────────┘
```

## API

### `/health`
```bash
curl http://localhost:8000/health
# { "status": "ok" }
```

### `/transcribe`
```bash
curl -X POST http://localhost:8000/transcribe \
  -H "Content-Type: application/json" \
  -d '{
    "audio": "base64_audio_data",
    "language": "pl",
    "model": "local",
    "system_prompt": "Przekształć to na profesjonalną wiadomość."
  }'
```

Odpowiedź:
```json
{
  "original": "hmm... chce napisać maila...",
  "rewritten": "Chciałbym napsać wiadomość e-mail.",
  "language": "pl",
  "model": "local",
  "success": true
}
```

## Deployment

### CI/CD

GitHub Actions automatycznie buduje obraz i wpycha do GHCR na push do `main`.

### ArgoCD

Manifesty w `k8s/` są synchronizowane przez ArgoCD z GitHub repo.

### Domain

`dictation.lab.tmforge.pl` — wildcard `*.lab.tmforge.pl`

## Konfiguracja

`.env`:
- `OLLAMA_URL` — URL do Ollamy (domyślnie: `http://192.168.1.5:11434`)
- `OLLAMA_MODEL` — model lokalny (`qwen3.5:9b`)
- `CLOUD_MODEL` — model cloud (`claude-sonnet-4-6`)
- `WHISPER_MODEL` — model Whisper (`large-v3`)
- `ANTHROPIC_API_KEY` — opcjonalnie

## Wdrożenie na K8s

```bash
# 1. Apply manifesty
kubectl apply -f k8s/

# 2. Dodaj secret (jeśli używasz cloud)
kubectl create secret generic voice-dictation-secrets \
  --from-literal=ANTHROPIC_API_KEY=... \
  -n voice-dictation

# 3. Zastosuj
kubectl apply -f k8s/deployment.yaml
```

## Licencja

MIT — © 2026 TMForge
