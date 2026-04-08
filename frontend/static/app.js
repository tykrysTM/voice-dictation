/**
 * Voice Dictation — Frontend MVP
 * Nagrywacz + API integration + clipboard
 */

const CONFIG = {
  backendUrl: "http://dictation.lab.tmforge.pl/transcribe",
  hotkey: "Control+Shift+D",
  apiTimeout: 30000
};

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
  copyBtn: document.getElementById("copy-btn"),
  pasteBtn: document.getElementById("paste-btn"),
  historyList: document.getElementById("history-list"),
};

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

init();

async function init() {
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

  elements.startRec.addEventListener("click", startRecording);
  elements.stopRec.addEventListener("click", stopRecording);
  elements.copyBtn.addEventListener("click", copyToClipboard);
  elements.pasteBtn.addEventListener("click", pasteFromClipboard);

  console.log("Voice Dictation initialized");
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      audioChunks.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      if (audioChunks.length === 0) return;

      const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
      const audioBase64 = await blobToBase64(audioBlob);

      stopRecordingUI();
      isRecording = false;

      await transcribe(audioBase64);
    };

    mediaRecorder.start();
    updateUI("Nagrywanie...");
    elements.startRec.disabled = true;
    elements.stopRec.disabled = false;

  } catch (error) {
    console.error("Mic access error:", error);
    alert("Nie udało się uzyskać dostępu do mikrofonu: " + error.message);
    updateUI("Błąd dostępu do mikrofonu");
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    updateUI("Przetwarzanie...");
  }
}

function stopRecordingUI() {
  mediaRecorder?.stream.getTracks().forEach(track => track.stop());
  elements.startRec.disabled = false;
  elements.stopRec.disabled = true;
  elements.recStatus.textContent = "Gotowy do nagrywania";
  elements.recStatus.classList.remove("recording");
}

function updateUI(status) {
  elements.recStatus.textContent = status;
  if (status.includes("Nagrywanie")) {
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
    const requestBody = {
      audio: audioBase64,
      language: elements.language.value,
      model: elements.model.value,
      use_local: elements.model.value === "local",
      system_prompt: elements.systemPrompt.value
    };

    console.log("Sending to API:", requestBody);

    const response = await fetch(CONFIG.backendUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    const result = await response.json();

    if (result.success) {
      elements.transcribedText.value = result.original;
      elements.rewrittenText.textContent = result.rewritten;
      elements.rewrittenText.focus();
      saveToHistory(result.rewritten);
      console.log("Transcription complete:", result);
    } else {
      elements.rewrittenText.textContent = "❌ Błąd API: " + JSON.stringify(result);
    }

  } catch (error) {
    console.error("Transcribe error:", error);
    elements.rewrittenText.textContent = "❌ Błąd: " + error.message;
  }
}

async function copyToClipboard() {
  const text = elements.rewrittenText.textContent;
  if (!text) return;

  try {
    await navigator.clipboard.writeText(text);
    alert("✅ Skopiowano do schowka!");
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
      // TODO: Implement text→audio conversion or direct text processing
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
  alert("✅ Skopiowano do schowka!");
}

function saveToHistory(text) {
  const timestamp = new Date().toLocaleTimeString();
  const item = document.createElement("div");
  item.className = "history-item";
  item.innerHTML = `
    <h4>🕒 ${timestamp}</h4>
    <p>${text.substring(0, 200)}...</p>
  `;
  elements.historyList.prepend(item);
}

window.voiceDictation = {
  transcribe,
  blobToBase64
};
