"use strict";

const State = Object.freeze({ IDLE: "IDLE", GREETING: "GREETING" });
const elements = {
  video: document.getElementById("characterVideo"),
  videoFrame: document.getElementById("videoFrame"),
  menuBoard: document.getElementById("menuBoard"),
  greetingAudio: document.getElementById("greetingAudio"),
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
  reconnectDelayMs: 1000, reconnectTimer: null, config: null, subtitleCues: {},
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
  const isNewCustomer = payload.customer_type === "new";
  document.body.dataset.state = State.GREETING;
  document.body.dataset.customerType = payload.customer_type;
  elements.menuBoard.hidden = !isNewCustomer;
  elements.kicker.textContent = isNewCustomer ? "初めてのご来店" : "またのご来店";
  elements.title.textContent = isNewCustomer ? "はじめまして" : "おかえりなさい";
  let watchdog;
  try {
    await Promise.race([
      Promise.allSettled([
        playGreetingVideo(runtime.config.videos[payload.customer_type], signal),
        playGreetingVoice(payload, signal),
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

function playRecordedAudio(url, signal, cues = []) {
  return new Promise(resolve => {
    let done = false;
    let currentCueIndex = -1;
    const audio = elements.greetingAudio;
    const updateSubtitle = () => {
      if (!cues.length) return;
      const position = Number.isFinite(audio.currentTime) ? audio.currentTime : 0;
      let cueIndex = cues.findIndex(cue => position >= cue.start && position < cue.end);
      if (cueIndex < 0) cueIndex = position >= cues[cues.length - 1].end ? cues.length - 1 : 0;
      if (cueIndex !== currentCueIndex) {
        currentCueIndex = cueIndex;
        elements.message.textContent = cues[cueIndex].text;
      }
    };
    const finish = successful => {
      if (done) return;
      done = true;
      audio.removeEventListener("ended", ended);
      audio.removeEventListener("error", failed);
      audio.removeEventListener("timeupdate", updateSubtitle);
      signal.removeEventListener("abort", aborted);
      resolve(successful);
    };
    const ended = () => finish(true);
    const failed = () => {
      console.warn("[AUDIO] 録音音声を再生できません。音声合成へ切り替えます");
      audio.pause();
      finish(false);
    };
    const aborted = () => {
      audio.pause();
      finish(false);
    };
    if (!url || signal.aborted) { finish(false); return; }
    audio.addEventListener("ended", ended, { once: true });
    audio.addEventListener("error", failed, { once: true });
    audio.addEventListener("timeupdate", updateSubtitle);
    signal.addEventListener("abort", aborted, { once: true });
    try {
      if (audio.getAttribute("src") !== url) {
        audio.src = url;
        audio.load();
      }
      audio.currentTime = 0;
      updateSubtitle();
      audio.play()?.catch(failed);
    } catch (error) {
      console.warn("[AUDIO]", error);
      failed();
    }
  });
}

async function playGreetingVoice(payload, signal) {
  const audioConfig = runtime.config.audio || {};
  const configuredUrl = payload.customer_type === "returning" && payload.discount_eligible
    ? (audioConfig.returning_discount || audioConfig.returning)
    : audioConfig[payload.customer_type];
  const recordedUrl = withAssetVersion(configuredUrl, runtime.config.audio_asset_version);
  const cueKey = payload.customer_type === "returning" && payload.discount_eligible
    ? "returning_discount"
    : payload.customer_type;
  if (recordedUrl) {
    window.speechSynthesis?.cancel();
    elements.message.textContent = payload.message;
    const played = await playRecordedAudio(
      recordedUrl,
      signal,
      runtime.subtitleCues[cueKey] || [],
    );
    if (played || signal.aborted) return;
  }
  await speak(payload.message, signal);
}

function withAssetVersion(url, version) {
  if (!url || !version) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}v=${encodeURIComponent(version)}`;
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
// Browser speech is the fallback when a configured recorded voice cannot play.
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
  elements.greetingAudio.pause();
  elements.greetingAudio.currentTime = 0;
  window.speechSynthesis?.cancel();
  runtime.state = State.IDLE;
  runtime.activeGreetingId = null;
  document.body.dataset.state = State.IDLE;
  delete document.body.dataset.customerType;
  elements.menuBoard.hidden = true;
  if (!runtime.config) return;
  elements.kicker.textContent = "お客様をお待ちしています";
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
    runtime.subtitleCues = await loadSubtitleCues(runtime.config.subtitle_cues);
    returnToIdle();
    connectWebSocket();
    elements.audioButton.disabled = false;
  } catch (error) {
    console.error("[CONFIG]", error);
    connectionStatus(false, "準備中です");
    setTimeout(initialize, 5000);
  }
}

async function loadSubtitleCues(cueUrls = {}) {
  const cueEntries = await Promise.all(Object.entries(cueUrls).map(async ([name, url]) => {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) throw new Error(`Subtitle request failed: ${response.status}`);
      const cues = await response.json();
      if (!Array.isArray(cues)) throw new Error("Subtitle data is not an array");
      const validCues = cues.filter(cue =>
        cue && typeof cue.text === "string" &&
        Number.isFinite(cue.start) && Number.isFinite(cue.end) &&
        cue.start >= 0 && cue.end > cue.start
      );
      return [name, validCues];
    } catch (error) {
      console.warn("[SUBTITLE]", name, error);
      return [name, []];
    }
  }));
  return Object.fromEntries(cueEntries);
}
void initialize();
