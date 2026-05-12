# Voice Dictation — Architecture Reference

_Ostatnia aktualizacja: 2026-05-12_

## Serwis

- **URL:** https://dictation.lab.tmforge.pl
- **Repo:** https://github.com/tykrysTM/voice-dictation
- **Namespace K8s:** `voice-dictation`
- **CI/CD:** GitHub Actions → GHCR → ArgoCD auto-sync (gałąź `main`)

---

## Architektura przepływu danych

```
Browser (webm audio)
    │
    ▼
POST /transcribe  (FastAPI backend w K8s)
    │
    ├─► [ollama_backend == "mac"]  → WHISPER_SERVER_URL_MAC  → Mac Studio :8001 (mlx-whisper Metal)
    └─► [ollama_backend == "windows"] → WHISPER_SERVER_URL  → Windows PC  :8001 (faster-whisper CUDA)
                                              │
                                              ▼  tekst transkrypcji
                                   rewrite_with_ollama()
                                              │
    ├─► [ollama_backend == "mac"]  → OLLAMA_URL          → Mac Studio  :11434 (Ollama Metal)
    └─► [ollama_backend == "windows"] → OLLAMA_URL_WINDOWS → Windows PC :11434 (Ollama CUDA)
                                              │
                                              ▼
                               JSON { original, rewritten }  →  Browser
```

---

## Backendy

### STT (Speech-to-Text)

| Backend | Host | Port | Silnik | Model | Uwagi |
|---|---|---|---|---|---|
| Windows CUDA | 192.168.1.5 | 8001 | faster-whisper | large-v3 | domyślny, najlepsza jakość PL |
| Mac Studio Metal | 192.168.1.7 | 8001 | mlx-whisper | large-v3 | TODO: instalacja (patrz niżej) |
| Lokalny CPU (fallback) | pod K8s | — | faster-whisper | small | tylko gdy oba zewnętrzne niedostępne |

Serwer Windows: własny FastAPI (`whisper_server.py` na Windows), endpointy `/health` i `/v1/audio/transcriptions`.
Serwer Mac: kod w `tools/whisper-server-mac/server.py` w tym repo.

### LLM (Ollama rewrite)

| Backend | Host | Port | Model | Prędkość |
|---|---|---|---|---|
| Mac Studio Metal | 192.168.1.7 | 11434 | qwen3.5:9b-chat | ~27.6 tok/s |
| Windows CUDA | 192.168.1.5 | 11434 | qwen3.5:9b-chat | ~15.4 tok/s |

**Ważne:** `think: false` w payloadzie Ollama — wyłącza tryb rozumowania Qwen3 (80s → ~1s).

### Modele Ollama na Mac Studio

Wszystkie warianty dzielą jeden blob GGUF (~6.5GB):

| Model | Kontekst | Temperatura | Przeznaczenie |
|---|---|---|---|
| qwen3.5:9b-chat | 65536 | 0.6 | voice dictation, ogólny asystent |
| qwen3.5:9b-code | 32768 | 0.2 | programowanie |
| qwen3.5:9b-research | 32768 | 0.4 | analiza, badania |
| qwen3.5:9b-32k | 32768 | 1.0 | bez system prompt |
| qwen3.5:9b | 262144 | domyślna | bazowy (nie używać w produkcji — za wolny) |

---

## Zmienne środowiskowe (K8s secret `voice-dictation-secrets`)

| Zmienna | Wartość | Opis |
|---|---|---|
| `OLLAMA_URL` | `http://192.168.1.7:11434/api/chat` | Ollama Mac Studio Metal |
| `OLLAMA_URL_WINDOWS` | `http://192.168.1.5:11434/api/chat` | Ollama Windows CUDA |
| `OLLAMA_MODEL` | `qwen3.5:9b-chat` | Model do rewrite |
| `WHISPER_SERVER_URL` | `http://192.168.1.5:8001` | STT Windows CUDA |
| `WHISPER_SERVER_URL_MAC` | `http://192.168.1.7:8001` | STT Mac Studio Metal |
| `WHISPER_MODEL` | `small` | Tylko fallback lokalny |
| `REALTIMESTT_URL` | `ws://192.168.1.5:8002` | Live Mode WebSocket |
| `SETTINGS_PASSWORD` | — | Hasło do panelu ustawień |

---

## Endpointy API

| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/health` | Status serwisu + info o Whisper/Ollama |
| POST | `/transcribe` | Audio (base64 webm) → STT → rewrite → JSON |
| POST | `/rewrite` | Tekst → rewrite przez Ollama → JSON |
| POST | `/auth` | Weryfikacja hasła ustawień |
| WS | `/ws/live` | Live Mode: audio PCM → RealtimeSTT → Ollama |

---

## CI/CD

```
git push → main
    │  (zmiany w backend/** lub frontend/**)
    ▼
GitHub Actions (.github/workflows/ci-cd.yaml)
    1. Testy (pytest)
    2. Docker build + push → ghcr.io/tykrystm/voice-dictation:<sha>
    3. Update k8s/deployment.yaml (nowy tag obrazu)
    4. git commit "[skip ci]" + push
    ▼
ArgoCD auto-sync
    → kubectl rollout restart deployment/voice-dictation
    ▼
Nowy pod z nowym obrazem
```

**Uwagi:**
- `[skip ci]` w tytule commita blokuje rebuild Docker — używać dla zmian tylko w `k8s/`
- Po zmianach w `k8s/secret.yaml` ArgoCD aktualizuje Secret, ale pod trzeba ręcznie zrestartować lub poczekać na kolejne wdrożenie
- ArgoCD czasem potrzebuje ręcznego odświeżenia: `kubectl annotate application voice-dictation -n argocd argocd.argoproj.io/refresh=hard --overwrite`

---

## Instalacja mlx-whisper na Mac Studio

Pliki serwera są w repozytorium: `tools/whisper-server-mac/` (server.py, requirements.txt, pl.tmforge.whisper.plist).

```bash
# 1. Zainstaluj zależności (na Mac Studio 192.168.1.7, user: tm)
pip3 install mlx-whisper fastapi "uvicorn[standard]" python-multipart

# 2. Skopiuj server
mkdir -p ~/whisper-server-mac
curl -o ~/whisper-server-mac/server.py \
  https://raw.githubusercontent.com/tykrysTM/voice-dictation/main/tools/whisper-server-mac/server.py

# 3. Uruchom testowo (pierwsze uruchomienie pobiera model ~3GB)
cd ~/whisper-server-mac
uvicorn server:app --host 0.0.0.0 --port 8001
# Weryfikacja: curl http://localhost:8001/health

# 4. Zainstaluj jako LaunchAgent (autostart przy boocie)
curl -o ~/Library/LaunchAgents/pl.tmforge.whisper.plist \
  https://raw.githubusercontent.com/tykrysTM/voice-dictation/main/tools/whisper-server-mac/pl.tmforge.whisper.plist
# WAŻNE: sprawdź ścieżkę uvicorn przed załadowaniem (Apple Silicon ≠ Intel):
#   which uvicorn  →  może być ~/Library/Python/3.x/bin/uvicorn lub /opt/homebrew/bin/uvicorn
# Zaktualizuj ProgramArguments[0] w plist jeśli inna niż /usr/local/bin/uvicorn
launchctl load ~/Library/LaunchAgents/pl.tmforge.whisper.plist

# Weryfikacja działania:
launchctl list | grep whisper   # powinno wyświetlić PID
curl http://192.168.1.7:8001/health  # {"status":"ok","model":"large-v3","device":"mlx"}
```

**Uwaga:** LaunchAgent ma `KeepAlive=true` — automatycznie restartuje się po crash. Logi: `~/whisper-server-mac/whisper.log`.

**Znany problem z ścieżką uvicorn:** na Apple Silicon Homebrew instaluje do `/opt/homebrew/bin/`, nie `/usr/local/bin/`. Jeśli `launchctl list` nie wyświetla PID, sprawdź log: `tail -20 ~/whisper-server-mac/whisper.log`.

---

## Znane problemy i rozwiązania

| Problem | Przyczyna | Rozwiązanie |
|---|---|---|
| Rewrite 80s timeout | Qwen3 thinking mode włączony | `"think": False` w payloadzie Ollama |
| HTTP 502 na /transcribe | Whisper server na Windows niedostępny | Restart serwisu na Windows; sprawdź logi `kubectl logs -n voice-dictation` |
| ArgoCD nie syncuje po push | Brak auto-refresh | `kubectl annotate application voice-dictation -n argocd argocd.argoproj.io/refresh=hard --overwrite` |
| git push rejected | CI commit wyprzedził lokalny branch | `git pull --rebase origin main && git push` |
| OLLAMA_MODEL=qwen3.5:9b zamiast chat | Bazowy model ma 262k ctx → eviction z VRAM | Zawsze używać `qwen3.5:9b-chat` (65k ctx) |
