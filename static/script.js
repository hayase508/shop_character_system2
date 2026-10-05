"use strict";

const State = Object.freeze({ IDLE: "IDLE", GREETING: "GREETING" });
const elements = {
  video: document.getElementById("characterVideo"),
  videoFrame: document.getElementById("videoFrame"),
  title: document.getElementById("dialogueTitle"),
  message: document.getElementById("dialogueMessage"),
  kicker: document.getElementById("dialogueKicker"),
  connection: document.getElementById("connectionStatus"),
  connectionLabel: document.getElementById("connectionLabel"),
  audioButton: document.getElementById("audioButton"),
};
const runtime = {
  state: State.IDLE, socket: null, activeGreetingId: null,
  enabled: false, displayActive: false, abort: null, utterance: null,
  reconnectDelayMs: 1000, reconnectTimer: null, config: null,
};

function send(payload) {
  if (runtime.socket?.readyState === WebSocket.OPEN) {
    runtime.socket.send(JSON.stringify(payload));
  }
}
function connectionStatus(connected, label) {
  elements.connection.dataset.connected = String(connected);
  elements.connectionLabel.textContent = label;
}
function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(protocol + "//" + location.host + "/ws");
  runtime.socket = socket;
  socket.addEventListener("open", () => {
    runtime.reconnectDelayMs = 1000;
    connectionStatus(true, "準備完了");
    if (runtime.enabled) send({ type: "display_ready" });
  });
  socket.addEventListener("message", event => {
    try { handleServerMessage(JSON.parse(event.data)); }
    catch (error) { console.error("[WEBSOCKET]", error); }
  });
  socket.addEventListener("close", () => {
    runtime.displayActive = false;
    returnToIdle();
    connectionStatus(false, "再接続中");
    if (!runtime.reconnectTimer) {
      runtime.reconnectTimer = setTimeout(() => {
        runtime.reconnectTimer = null;
        connectWebSocket();
      }, runtime.reconnectDelayMs);
      runtime.reconnectDelayMs = Math.min(runtime.reconnectDelayMs * 2, 15000);
    }
  });
  socket.addEventListener("error", () => socket.close());
}
function handleServerMessage(payload) {
  if (payload.type === "display_role") {
    runtime.displayActive = payload.active;
    elements.audioButton.dataset.enabled = String(payload.active);
    connectionStatus(true, payload.active ? "お迎えしています" : "別の画面で接客中");
  } else if (payload.type === "customer_detected" && runtime.displayActive) {
    // Duplicate delivery must not restart speech.
    if (runtime.state === State.IDLE && typeof payload.message === "string") {
      void beginGreeting(payload);
    }
  } else if (payload.type === "state_changed" && payload.state === State.IDLE) {
    returnToIdle();
  }
}

async function beginGreeting(payload) {
  if (runtime.state !== State.IDLE) return;
  runtime.state = State.GREETING;
  runtime.activeGreetingId = payload.greeting_id;
  runtime.abort = new AbortController();
  const signal = runtime.abort.signal;
  document.body.dataset.state = State.GREETING;
  elements.kicker.textContent = payload.customer_type === "new" ? "FIRST VISIT" : "WELCOME BACK";
  elements.title.textContent = payload.customer_type === "new" ? "はじめまして" : "おかえりなさい";
  let watchdog;
  try {
    await Promise.race([
      Promise.allSettled([
        playGreetingVideo(runtime.config.videos[payload.customer_type], signal),
        speak(payload.message, signal),
      ]),
      new Promise(resolve => {
        watchdog = setTimeout(() => {
          console.warn("[GREETING] Playback timeout");
          resolve();
        }, runtime.config.greeting_timeout_seconds * 1000);
      }),
    ]);
    if (!signal.aborted && runtime.activeGreetingId === payload.greeting_id) {
      send({ type: "greeting_finished", greeting_id: payload.greeting_id });
      returnToIdle();
    }
  } finally {
    clearTimeout(watchdog);
  }
}

function setVideoSource(url) {
  if (!url) { markVideoError(true); return; }
  if (elements.video.getAttribute("src") !== url) {
    elements.video.src = url;
    elements.video.load();
  }
}
function markVideoError(failed) {
  elements.videoFrame.dataset.videoError = String(failed);
}
function playGreetingVideo(url, signal) {
  return new Promise(resolve => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      elements.video.removeEventListener("ended", finish);
      elements.video.removeEventListener("error", fail);
      signal.removeEventListener("abort", finish);
      resolve();
    };
    const fail = () => {
      console.warn("[VIDEO] 動画を再生できません");
      markVideoError(true);
      finish();
    };
    if (!url || signal.aborted) { finish(); return; }
    elements.video.addEventListener("ended", finish);
    elements.video.addEventListener("error", fail);
    signal.addEventListener("abort", finish, { once: true });
    try {
      elements.video.loop = false;
      setVideoSource(url);
      elements.video.currentTime = 0;
      elements.video.play()?.catch(fail);
    } catch (error) { fail(); }
  });
}

function waitForReading(text, signal) {
  return new Promise(resolve => {
    if (signal.aborted) { resolve(); return; }
    const done = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", done);
      resolve();
    };
    const timer = setTimeout(done, Math.min(8000, Math.max(3000, text.length * 110)));
    signal.addEventListener("abort", done, { once: true });
  });
}
function speakSentence(text, signal) {
  return new Promise(resolve => {
    if (signal.aborted || !("speechSynthesis" in window)) { resolve(false); return; }
    let settled = false;
    let timeout;
    let utterance;
    const finish = successful => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      signal.removeEventListener("abort", abort);
      if (utterance) { utterance.onend = null; utterance.onerror = null; }
      runtime.utterance = null;
      resolve(successful);
    };
    const abort = () => { window.speechSynthesis.cancel(); finish(false); };
    try {
      utterance = new SpeechSynthesisUtterance(text);
      runtime.utterance = utterance;
      utterance.lang = "ja-JP";
      utterance.rate = 0.95;
      utterance.pitch = 0.92;
      const voice = window.speechSynthesis.getVoices().find(v => /^ja/i.test(v.lang));
      if (voice) utterance.voice = voice;
      utterance.onend = () => finish(true);
      utterance.onerror = event => {
        console.warn("[SPEECH]", event.error);
        finish(false);
      };
      signal.addEventListener("abort", abort, { once: true });
      timeout = setTimeout(() => {
        console.warn("[SPEECH] 読み上げの応答がありません");
        abort();
      }, Math.max(15000, text.length * 500));
      window.speechSynthesis.speak(utterance);
    } catch (error) {
      console.warn("[SPEECH]", error);
      finish(false);
    }
  });
}
// Replace this adapter to integrate VOICEVOX later.
async function speak(text, signal = new AbortController().signal) {
  window.speechSynthesis?.cancel();
  const sentences = text.match(/[^。！？!?]+[。！？!?]?/gu) || [text];
  for (const sentence of sentences) {
    if (signal.aborted) break;
    elements.message.textContent = sentence;
    const spoken = await speakSentence(sentence, signal);
    if (!spoken && !signal.aborted) await waitForReading(sentence, signal);
  }
}
function returnToIdle() {
  runtime.abort?.abort();
  runtime.abort = null;
  window.speechSynthesis?.cancel();
  runtime.state = State.IDLE;
  runtime.activeGreetingId = null;
  document.body.dataset.state = State.IDLE;
  if (!runtime.config) return;
  elements.kicker.textContent = "WELCOME";
  elements.title.textContent = runtime.config.idle_title;
  elements.message.textContent = runtime.config.idle_message;
  elements.video.loop = true;
  setVideoSource(runtime.config.videos.idle);
  try { elements.video.play()?.catch(() => markVideoError(true)); }
  catch (error) { markVideoError(true); }
}
async function enableAudio() {
  elements.audioButton.disabled = true;
  runtime.enabled = true;
  send({ type: "display_ready" });
  // Start a non-empty utterance synchronously in the click handler to unlock
  // browser audio, but never delay display registration while waiting for it.
  void speakSentence("いらっしゃいませ。", new AbortController().signal)
    .finally(() => { elements.audioButton.disabled = false; });
}
elements.audioButton.addEventListener("click", () => void enableAudio());
elements.video.addEventListener("canplay", () => markVideoError(false));
elements.video.addEventListener("error", () => markVideoError(true));
document.getElementById("fullscreenButton").addEventListener("click", () => {
  if (document.fullscreenElement) document.exitFullscreen()?.catch(console.warn);
  else document.documentElement.requestFullscreen()?.catch(console.warn);
});
async function initialize() {
  elements.audioButton.disabled = true;
  try {
    const response = await fetch("/api/config", { cache: "no-store" });
    if (!response.ok) throw new Error("Configuration request failed");
    runtime.config = await response.json();
    returnToIdle();
    connectWebSocket();
    elements.audioButton.disabled = false;
  } catch (error) {
    console.error("[CONFIG]", error);
    connectionStatus(false, "準備中です");
    setTimeout(initialize, 5000);
  }
}
void initialize();
