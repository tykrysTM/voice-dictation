/**
 * Voice Dictation — Frontend MVP
 * Nagrywacz + API integration + clipboard
 */

// Configuration
const CONFIG = {
  backendUrl: "/transcribe",
  hotkey: "Control+Shift+D",
  apiTimeout: 30000
};

// DOM Elements
const elements = {
  startRec: document.getElementById("start-rec"),
  stopRec: document.getElementById("stop-rec"),
  recStatus: document.getElementById("rec-status"),
  transcribedText: document.getElementById("transcribed-text"),
  rewrittenText: document.getElementById("rewritten-text"),
  backendUrl: document.getElementById("backend-url"),
  language: document.getElementById("language"),
  model: document.getElementById("model"),
  systemPrompt: document.getElementById("system-prompt"),
  translateEn: document.getElementById("translate-en"),
  copyBtn: document.getElementById("copy-btn"),
  pasteBtn: document.getElementById("paste-btn"),
  liveModeBtn: document.getElementById("live-mode-btn"),
  gpuLiveBtn: document.getElementById("gpu-live-btn")
};

// Audio recorder
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

// Live Mode (Web Speech API)
let recognition = null;
let isLiveMode = false;
let liveInterimText = "";

// Processing timer
let _processingTimer = null;
let _processingStart = null;

function startProcessingTimer() {
  _processingStart = Date.now();
  elements.recStatus.classList.add("processing");
  _processingTimer = setInterval(() => {
    const elapsed = ((Date.now() - _processingStart) / 1000).toFixed(1);
    elements.recStatus.textContent = `Processing… ${elapsed}s`;
  }, 100);
}

function stopProcessingTimer() {
  if (_processingTimer) {
    clearInterval(_processingTimer);
    _processingTimer = null;
    _processingStart = null;
  }
  elements.recStatus.classList.remove("processing");
}

// Init
init();

async function init() {
  // Hotkey listener
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === "D") {
      e.preventDefault();
      if (!isRecording) {
        startRecording();
      } else {
        stopRecording();
      }
    }
  });

  // UI buttons
  elements.startRec.addEventListener("click", startRecording);
  elements.stopRec.addEventListener("click", stopRecording);
  elements.copyBtn.addEventListener("click", copyToClipboard);
  elements.pasteBtn.addEventListener("click", pasteFromClipboard);
  elements.liveModeBtn.addEventListener("click", toggleLiveMode);
  elements.gpuLiveBtn.addEventListener("click", toggleGpuLive);

  // Hide Live Mode button if browser doesn't support it
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    elements.liveModeBtn.style.display = "none";
  }

  // Default prompt
  if (elements.systemPrompt) {
    elements.systemPrompt.value = "Przekształć to na profesjonalną, formalną wiadomość. Usuń błędy, popraw styl, formatuj jeśli potrzeba.";
  }

  console.log("Voice Dictation initialized");
}

async function startRecording() {
  try {
    // Request microphone access
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });

    // MediaRecorder setup
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      audioChunks.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      if (audioChunks.length === 0) return;

      const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
      const audioBase64 = await blobToBase64(audioBlob);

      // Stop recording
      stopRecordingUI();
      isRecording = false;

      // Start processing timer
      startProcessingTimer();

      // Send to API
      await transcribe(audioBase64);
    };

    // Start recording
    mediaRecorder.start();
    isRecording = true;
    updateUI("Recording...");
    elements.startRec.disabled = true;
    elements.stopRec.disabled = false;

  } catch (error) {
    console.error("Mic access error:", error);
    alert("Could not access microphone: " + error.message);
    updateUI("Microphone access error");
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    updateUI("Processing...");
  }
}

function stopRecordingUI() {
  mediaRecorder?.stream.getTracks().forEach(track => track.stop());
  elements.startRec.disabled = false;
  elements.stopRec.disabled = true;
  elements.recStatus.textContent = "Ready";
  elements.recStatus.classList.remove("recording");
  elements.recStatus.classList.remove("error");
}

function updateUI(status) {
  elements.recStatus.textContent = status;
  if (status.includes("Recording")) {
    elements.recStatus.classList.add("recording");
  }
}

async function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

async function transcribe(audioBase64) {
  try {
    const translateToEnglish = elements.translateEn?.checked;

    const requestBody = {
      audio: audioBase64,
      language: elements.language.value,
      model: elements.model.value,
      use_local: elements.model.value === "local",
      system_prompt: elements.systemPrompt.value,
      translate_to: translateToEnglish ? "English" : ""
    };

    console.log("Sending to API:", requestBody);

    // Use backend URL from input field or fall back to CONFIG
    const url = (elements.backendUrl?.value?.trim() || CONFIG.backendUrl);

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(requestBody)
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    const result = await response.json();

    stopProcessingTimer();

    if (result.success) {
      // Transcription
      elements.transcribedText.value = result.original;

      // Professional version
      elements.rewrittenText.textContent = result.rewritten;
      elements.rewrittenText.classList.remove("error");

      elements.recStatus.textContent = result.rewrite_skipped
        ? "Done (rewrite unavailable — showing original)"
        : "Done";

      // Auto-focus
      elements.rewrittenText.focus();

      console.log("Transcription complete:", result);
    } else {
      const errorMsg = "API Error: " + JSON.stringify(result);
      elements.rewrittenText.textContent = errorMsg;
      elements.rewrittenText.classList.add("error");
      elements.recStatus.textContent = "Error";
    }

  } catch (error) {
    stopProcessingTimer();
    console.error("Transcribe error:", error);
    const errorMsg = "Error: " + error.message;
    elements.rewrittenText.textContent = errorMsg;
    elements.rewrittenText.classList.add("error");
    elements.recStatus.classList.add("error");
  }
}

function toggleLiveMode() {
  if (!isLiveMode) {
    startLiveMode();
  } else {
    stopLiveMode();
  }
}

function startLiveMode() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = elements.language.value === "pl" ? "pl-PL" : "en-US";

  recognition.onstart = () => {
    isLiveMode = true;
    elements.liveModeBtn.classList.add("active");
    elements.liveModeBtn.textContent = "⏹ Stop Live";
    elements.startRec.disabled = true;
    elements.stopRec.disabled = true;
    elements.recStatus.textContent = "Live — słucham…";
    elements.recStatus.classList.add("recording");
    elements.transcribedText.value = "";
    elements.rewrittenText.textContent = "";
    liveInterimText = "";
  };

  recognition.onresult = (event) => {
    let interim = "";
    let final = "";

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        final += transcript;
      } else {
        interim += transcript;
      }
    }

    // Show confirmed text + grayed interim
    const confirmed = elements.transcribedText.value.replace(/\n\[…\].*$/, "").trimEnd();
    if (interim) {
      elements.transcribedText.value = confirmed + (confirmed ? "\n" : "") + "[…] " + interim;
    }

    if (final) {
      const updated = confirmed + (confirmed ? " " : "") + final;
      elements.transcribedText.value = updated;
      liveInterimText = "";
      // Trigger rewrite for the final sentence
      sendLiveRewrite(final.trim());
    }
  };

  recognition.onerror = (event) => {
    if (event.error === "not-allowed") {
      alert("Microphone access denied.");
    }
    stopLiveMode();
  };

  recognition.onend = () => {
    if (isLiveMode) {
      // Auto-restart if still in live mode (browser stops after silence)
      recognition.start();
    }
  };

  recognition.start();
}

function stopLiveMode() {
  isLiveMode = false;
  if (recognition) {
    recognition.onend = null;
    recognition.stop();
    recognition = null;
  }
  elements.liveModeBtn.classList.remove("active");
  elements.liveModeBtn.textContent = "🎙 Live Mode";
  elements.startRec.disabled = false;
  elements.stopRec.disabled = true;
  elements.recStatus.textContent = "Ready";
  elements.recStatus.classList.remove("recording");
}

async function sendLiveRewrite(text) {
  if (!text || elements.model.value !== "local") return;

  const translateToEnglish = elements.translateEn?.checked;
  const url = (elements.backendUrl?.value?.trim() || "/rewrite").replace("/transcribe", "/rewrite");

  try {
    const response = await fetch("/rewrite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        language: elements.language.value,
        system_prompt: elements.systemPrompt.value,
        translate_to: translateToEnglish ? "English" : ""
      })
    });

    if (!response.ok) return;
    const result = await response.json();

    if (result.success && !result.rewrite_skipped) {
      const current = elements.rewrittenText.textContent;
      elements.rewrittenText.textContent = current
        ? current + " " + result.rewritten
        : result.rewritten;
    }
  } catch (e) {
    console.warn("Live rewrite error:", e);
  }
}

async function copyToClipboard() {
  const text = elements.rewrittenText.textContent;
  if (!text) return;

  try {
    await navigator.clipboard.writeText(text);
    alert("Copied to clipboard!");
  } catch (error) {
    console.error("Clipboard error:", error);
    fallbackCopy(text);
  }
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    if (text) {
      elements.transcribedText.value = text;
    }
  } catch (error) {
    console.error("Paste error:", error);
  }
}

function fallbackCopy(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
  alert("Copied to clipboard!");
}

// ─── GPU Live Mode (WebSocket + Whisper GPU + Ollama) ───────────────────────

let gpuLiveWs = null;
let gpuAudioContext = null;
let gpuAudioSource = null;
let gpuAudioProcessor = null;
let gpuMicStream = null;
let isGpuLive = false;

function toggleGpuLive() {
  if (!isGpuLive) {
    startGpuLive();
  } else {
    stopGpuLive();
  }
}

async function startGpuLive() {
  // Stop other modes first
  if (isRecording) stopRecording();
  if (isLiveMode) stopLiveMode();

  try {
    gpuMicStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  } catch (e) {
    alert("Microphone access denied: " + e.message);
    return;
  }

  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${proto}//${window.location.host}/ws/live`;

  gpuLiveWs = new WebSocket(wsUrl);
  gpuLiveWs.binaryType = "arraybuffer";

  gpuLiveWs.onopen = () => {
    gpuLiveWs.send(JSON.stringify({
      language: elements.language.value,
      system_prompt: elements.systemPrompt?.value || "",
      translate_to: elements.translateEn?.checked ? "English" : "",
      use_rewrite: elements.model.value === "local"
    }));
  };

  gpuLiveWs.onmessage = async (event) => {
    const data = JSON.parse(event.data);

    if (data.type === "ready") {
      await setupGpuAudio();
      isGpuLive = true;
      elements.gpuLiveBtn.classList.add("active");
      elements.gpuLiveBtn.textContent = "⏹ Stop GPU";
      elements.startRec.disabled = true;
      elements.stopRec.disabled = true;
      elements.recStatus.textContent = "GPU Live — słucham…";
      elements.recStatus.classList.add("recording");
      elements.transcribedText.value = "";
      elements.rewrittenText.textContent = "";

    } else if (data.type === "transcript") {
      const cur = elements.transcribedText.value;
      elements.transcribedText.value = cur ? cur + " " + data.text : data.text;

    } else if (data.type === "rewritten") {
      const cur = elements.rewrittenText.textContent;
      elements.rewrittenText.textContent = cur ? cur + " " + data.text : data.text;

    } else if (data.type === "error") {
      alert("GPU Live error: " + data.message);
      stopGpuLive();
    }
  };

  gpuLiveWs.onerror = () => {
    alert("Cannot connect to GPU Live backend.");
    stopGpuLive();
  };

  gpuLiveWs.onclose = () => {
    if (isGpuLive) stopGpuLive();
  };
}

async function setupGpuAudio() {
  gpuAudioContext = new AudioContext({ sampleRate: 16000 });
  await gpuAudioContext.audioWorklet.addModule("/audio-processor.js");
  gpuAudioSource = gpuAudioContext.createMediaStreamSource(gpuMicStream);
  gpuAudioProcessor = new AudioWorkletNode(gpuAudioContext, "pcm-processor");
  gpuAudioProcessor.port.onmessage = (e) => {
    if (gpuLiveWs?.readyState === WebSocket.OPEN) {
      gpuLiveWs.send(e.data);
    }
  };
  gpuAudioSource.connect(gpuAudioProcessor);
}

function stopGpuLive() {
  if (gpuLiveWs?.readyState === WebSocket.OPEN) {
    try { gpuLiveWs.send(JSON.stringify({ action: "stop" })); } catch (_) {}
    gpuLiveWs.close();
  }
  gpuLiveWs = null;

  gpuAudioProcessor?.disconnect();
  gpuAudioSource?.disconnect();
  gpuMicStream?.getTracks().forEach(t => t.stop());
  if (gpuAudioContext?.state !== "closed") gpuAudioContext?.close();
  gpuAudioProcessor = null;
  gpuAudioSource = null;
  gpuAudioContext = null;
  gpuMicStream = null;

  isGpuLive = false;
  elements.gpuLiveBtn.classList.remove("active");
  elements.gpuLiveBtn.textContent = "⚡ GPU Live";
  elements.startRec.disabled = false;
  elements.stopRec.disabled = true;
  elements.recStatus.textContent = "Ready";
  elements.recStatus.classList.remove("recording");
}

// ─── Expose for debugging ────────────────────────────────────────────────────

// Expose for debugging
window.voiceDictation = {
  transcribe,
  blobToBase64
};
