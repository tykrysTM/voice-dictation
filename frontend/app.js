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
  pasteBtn: document.getElementById("paste-btn")
};

// Audio recorder
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

// Processing timer
let _processingTimer = null;
let _processingStart = null;

function startProcessingTimer() {
  _processingStart = Date.now();
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
    const systemPrompt = translateToEnglish
      ? "Translate the following text to English and rewrite it as a professional, formal message. Fix any errors and improve the style."
      : elements.systemPrompt.value;

    const requestBody = {
      audio: audioBase64,
      language: elements.language.value,
      model: elements.model.value,
      use_local: elements.model.value === "local",
      system_prompt: systemPrompt
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

// Expose for debugging
window.voiceDictation = {
  transcribe,
  blobToBase64
};
