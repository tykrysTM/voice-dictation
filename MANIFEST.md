# Voice Dictation Project — Plan

_Cel: Dyktuj myśli w PL/EN → lokalny LLM zamienia na profesjonalny tekst do Teams/mail/prompów._

## MVP (Week 1-2)

### 1. Backend API (FastAPI) — Priority
- **Plik:** `backend/main.py`
- **Endpoints:**
  - `POST /transcribe` → audio (base64) + options (lang, model, systemPrompt) → transcribed+rewritten text
  - `GET /health` → status (models ready?)
- **Stack:**
  - Whisper (whisper.cpp) → transkrypcja
  - Ollama (qwen3.5:9b) → polish/rewriting
  - Config: model choice (local/cloud), lang, systemPrompt
- **Tech:** Python 3.12 + FastAPI + uvicorn

### 2. Frontend (React/TypeScript) — Priority
- **Plik:** `frontend/src/App.tsx`
- **Funkcje:**
  - Audio recorder (MediaRecorder)
  - Hotkey trigger (Ctrl+Shift+D)
  - Preview transcribed text
  - Copy to clipboard
  - Model toggle (local/cloud)
- **Hosting:** K8s deployment (jak grammar-service)

### 3. System Integration
- **Clipboard integration:** Auto-paste po kliknięciu
- **Hotkey:** Ctrl+Shift+D → nagrywaj

### 4. Deployment
- **K8s manifests:** namespace, deployment, service, ingress
- **ArgoCD:** Auto-sync z GitHub
- **Domain:** `dictation.lab.tmforge.pl`

### 5. Test
- **Lokalne testy:** qwen3.5:9b na GPU
- **Jakość:** Sprawdź polskich/angielskich transkrypcji
- **Optimize:** VRAM, kontekst

## Phase 2 (Month 2-3)

### 6. Real-time Streaming
- **WebSocket:** `ws://backend/stream` → fragmenty audio → live transkrypcja
- **Backend:** WebSockets + streaming inference

### 7. Advanced Editing
- **LLM prompts:** Tone, brevity, bullet points, formatting
- **History:** Sesje z edycją

### 8. Multi-user (Phase 3)
- **Auth:** JWT/session tokens
- **DB:** PostgreSQL (opcjonalnie)

### 9. UI Polish
- **Hotkey menu:** Dropdown z historią
- **Voice selection:** Microphone test

### 10. Production Hardening
- **Load balancing:** Traefik + K8s HPA
- **Monitoring:** Uptime Kuma
- **Backups:** K8s Secrets + DB

## Timeline

| Week | Task | Deliverable |
|---|---|---|
| 1 | Backend API + test | `/transcribe` endpoint |
| 2 | Frontend + recorder | MVP w przeglądarce |
| 3 | Hotkey + integration | End-to-end flow |
| 4 | Deployment + monitoring | LIVE na K8s |
| 5+ | Phase 2: streaming | Real-time mode |

## Notes

- **Model:** qwen3.5:9b:q4_k_m (lokalny), Claude (fallback)
- **VRAM:** qwen3.5:9b ~6-7GB (FP16: ~18GB, ale Q4_K_M)
- **Lang:** PL + EN (whisper + LLM)

---

_Koniec planu._