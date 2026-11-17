"use strict";

const State = Object.freeze({
  IDLE: "IDLE", GREETING: "GREETING", READY: "READY", LISTENING: "LISTENING",
  TRANSCRIBING: "TRANSCRIBING", THINKING: "THINKING", SPEAKING: "SPEAKING",
});
const elements = {
  video: document.getElementById("characterVideo"),
  videoFrame: document.getElementById("videoFrame"),
  menuBoard: document.getElementById("menuBoard"),
  checkoutBoard: document.getElementById("checkoutBoard"),
  checkoutImage: document.getElementById("checkoutImage"),
  greetingAudio: document.getElementById("greetingAudio"),
  title: document.getElementById("dialogueTitle"),
  message: document.getElementById("dialogueMessage"),
  question: document.getElementById("questionText"),
  kicker: document.getElementById("dialogueKicker"),
  connection: document.getElementById("connectionStatus"),
  connectionLabel: document.getElementById("connectionLabel"),
  audioButton: document.getElementById("audioButton"),
  fullscreenButton: document.getElementById("fullscreenButton"),
};
const runtime = {
  state: State.IDLE, socket: null, activeGreetingId: null,
  enabled: false, displayActive: false, abort: null, answerAbort: null,
  utterance: null, reconnectDelayMs: 1000, reconnectTimer: null,
  config: null, subtitleCues: {}, microphoneGranted: null, microphone: null,
  microphoneConstraints: null, microphoneDeviceLabel: "",
  audioContext: null,
  questionSessionId: null, activeQuestionId: null, lastCustomerType: "returning",
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
    if (runtime.enabled) {
      send({ type: "display_ready" });
      if (runtime.microphoneGranted !== null) {
        send({
          type: "question_capability",
          available: runtime.microphoneGranted,
          microphone_label: runtime.microphoneDeviceLabel || null,
        });
      }
    }
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
    if (runtime.state === State.IDLE && typeof payload.message === "string") {
      void beginGreeting(payload);
    }
  } else if (payload.type === "question_recognized") {
    if (questionIdsMatch(payload)) {
      renderQuestionState(State.THINKING, payload.question);
    }
  } else if (payload.type === "answer_text_ready") {
    if (questionIdsMatch(payload)) {
      renderAnswerPreview(payload.question, payload.answer);
    }
  } else if (payload.type === "answer_started") {
    if (questionIdsMatch(payload)) {
      renderAnswer(payload.question, payload.answer);
    }
  } else if (payload.type === "touch_question_started" && runtime.displayActive) {
    stopQuestionMonitoring();
    runtime.questionSessionId = payload.question_session_id;
    runtime.activeQuestionId = payload.question_id;
    runtime.state = State.THINKING;
    document.body.dataset.state = State.THINKING;
    renderQuestionState(State.THINKING, payload.question);
  } else if (payload.type === "touch_answer_started") {
    if (questionIdsMatch(payload)) void playQuestionAnswer(payload);
  } else if (payload.type === "state_changed") {
    handleStateChanged(payload);
  }
}

function handleStateChanged(payload) {
  if (payload.state === State.IDLE) {
    returnToIdle();
  } else if (payload.state === State.READY && runtime.displayActive) {
    void enterReady(payload);
  } else if (payload.state === State.LISTENING && questionIdsMatch(payload)) {
    renderQuestionState(State.LISTENING);
  } else if (payload.state === State.TRANSCRIBING && questionIdsMatch(payload)) {
    renderQuestionState(State.TRANSCRIBING);
  } else if (payload.state === State.THINKING && questionIdsMatch(payload)) {
    renderQuestionState(State.THINKING);
  } else if (payload.state === State.SPEAKING && questionIdsMatch(payload)) {
    runtime.state = State.SPEAKING;
    document.body.dataset.state = State.SPEAKING;
    stopQuestionMonitoring();
  }
}

async function beginGreeting(payload) {
  if (runtime.state !== State.IDLE) return;
  stopQuestionMonitoring();
  runtime.state = State.GREETING;
  runtime.activeGreetingId = payload.greeting_id;
  runtime.lastCustomerType = payload.customer_type;
  runtime.abort = new AbortController();
  const signal = runtime.abort.signal;
  const isNewCustomer = payload.customer_type === "new";
  document.body.dataset.state = State.GREETING;
  document.body.dataset.customerType = payload.customer_type;
  elements.menuBoard.hidden = !isNewCustomer;
  elements.checkoutBoard.hidden = !isNewCustomer;
  showQuestionText("");
  elements.kicker.textContent = isNewCustomer ? "初めてのご来店" : "またのご来店";
  elements.title.textContent = isNewCustomer ? "はじめまして" : "おかえりなさい";
  let watchdog;
  const speakingVideo = startSpeakingVideo(
    runtime.config.videos.speaking_intro,
    runtime.config.videos.speaking_loop || runtime.config.videos[payload.customer_type],
    signal,
  );
  try {
    await Promise.race([
      (async () => {
        await speakingVideo.ready;
        if (!signal.aborted) await playGreetingVoice(payload, signal);
      })(),
      new Promise(resolve => {
        watchdog = setTimeout(() => {
          console.warn("[GREETING] Playback timeout");
          runtime.abort?.abort();
          resolve();
        }, runtime.config.greeting_timeout_seconds * 1000);
      }),
    ]);
    if (!signal.aborted && runtime.activeGreetingId === payload.greeting_id) {
      send({ type: "greeting_finished", greeting_id: payload.greeting_id });
      // Older/test configurations without questions keep the original behavior.
      if (!runtime.config.questions?.enabled) returnToIdle();
    }
  } finally {
    clearTimeout(watchdog);
    speakingVideo.stop();
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
    const aborted = () => { audio.pause(); finish(false); };
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

async function preloadCharacterVideos(videos = {}) {
  const urls = [...new Set([
    videos.speaking_intro,
    videos.speaking_loop,
    videos.new,
    videos.returning,
  ].filter(url => typeof url === "string" && url.startsWith("/static/videos/")))];
  await Promise.allSettled(urls.map(async url => {
    const response = await fetch(url, { cache: "force-cache" });
    if (!response.ok) throw new Error(`Video preload failed: ${response.status}`);
    await response.arrayBuffer();
  }));
}
function markVideoError(failed) {
  elements.videoFrame.dataset.videoError = String(failed);
}
function startSpeakingVideo(introUrl, loopUrl, signal) {
  let stopped = false;
  let introSettled = false;
  let readySettled = false;
  let resolveReady;
  const ready = new Promise(resolve => { resolveReady = resolve; });
  const markReady = () => {
    if (readySettled) return;
    readySettled = true;
    resolveReady();
  };
  const removeIntroListeners = () => {
    elements.video.removeEventListener("ended", finishIntro);
    elements.video.removeEventListener("error", failIntro);
  };
  const stop = () => {
    if (stopped) return;
    stopped = true;
    removeIntroListeners();
    elements.video.removeEventListener("error", failLoop);
    signal.removeEventListener("abort", stop);
    elements.video.loop = false;
    elements.video.pause();
    markReady();
  };
  const failLoop = () => {
    console.warn("[VIDEO] 動画を再生できません");
    markVideoError(true);
    stop();
  };
  const playLoop = () => {
    if (stopped || signal.aborted) { markReady(); return; }
    removeIntroListeners();
    const url = loopUrl || introUrl;
    if (!url) { failLoop(); return; }
    markVideoError(false);
    elements.video.loop = true;
    setVideoSource(url);
    elements.video.currentTime = 0;
    elements.video.addEventListener("error", failLoop, { once: true });
    try { elements.video.play()?.catch(failLoop); }
    catch (error) { failLoop(); }
    markReady();
  };
  const finishIntro = () => {
    if (introSettled || stopped) return;
    introSettled = true;
    playLoop();
  };
  const failIntro = () => {
    if (introSettled || stopped) return;
    console.warn("[VIDEO] 話し始めの動画を再生できません。会話動画へ切り替えます");
    markVideoError(true);
    finishIntro();
  };
  if (signal.aborted) {
    stop();
    return { ready, stop };
  }
  signal.addEventListener("abort", stop, { once: true });
  if (!introUrl) {
    playLoop();
    return { ready, stop };
  }
  elements.video.loop = false;
  markVideoError(false);
  elements.video.addEventListener("ended", finishIntro, { once: true });
  elements.video.addEventListener("error", failIntro, { once: true });
  try {
    setVideoSource(introUrl);
    elements.video.currentTime = 0;
    elements.video.play()?.catch(failIntro);
  } catch (error) { failIntro(); }
  return { ready, stop };
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

function createVadTracker(config, now = 0) {
  const calibrationMs = Math.max(0, Number(config.vad_calibration_ms) || 0);
  return {
    config, candidateSince: null, speaking: false, speechStartedAt: null,
    lastVoiceAt: null, startedAt: now, completed: false,
    calibrated: calibrationMs === 0, calibrationMs, calibrationSamples: [],
    noiseFloor: 0, effectiveThreshold: Number(config.vad_start_threshold) || 0.02,
    currentLevel: 0,
  };
}

function finishVadCalibration(tracker) {
  const samples = tracker.calibrationSamples
    .filter(Number.isFinite)
    .sort((left, right) => left - right);
  // Use the quieter part of the calibration window so a fading speaker echo
  // cannot leave the microphone permanently insensitive.
  const percentileIndex = Math.max(0, Math.ceil(samples.length * 0.20) - 1);
  tracker.noiseFloor = samples[percentileIndex] || 0;
  tracker.effectiveThreshold = calculateVadThreshold(tracker.config, tracker.noiseFloor);
  tracker.calibrationSamples = [];
  tracker.calibrated = true;
}

function calculateVadThreshold(config, noiseFloor) {
  const baseThreshold = Number(config.vad_start_threshold) || 0.02;
  const multiplier = Math.max(1, Number(config.vad_noise_multiplier) || 1);
  const margin = Math.max(0, Number(config.vad_noise_margin) || 0);
  return Math.max(
    baseThreshold,
    noiseFloor * multiplier,
    noiseFloor + margin,
  );
}

function updateVadTracker(tracker, level, now) {
  if (tracker.completed) return null;
  tracker.currentLevel = level;
  if (!tracker.calibrated) {
    tracker.calibrationSamples.push(level);
    if (now - tracker.startedAt < tracker.calibrationMs) return null;
    finishVadCalibration(tracker);
    tracker.candidateSince = null;
    return null;
  }
  if (!tracker.speaking && tracker.candidateSince === null && level < tracker.noiseFloor) {
    tracker.noiseFloor = tracker.noiseFloor * 0.95 + level * 0.05;
    tracker.effectiveThreshold = calculateVadThreshold(tracker.config, tracker.noiseFloor);
  }
  const above = level >= tracker.effectiveThreshold;
  if (!tracker.speaking) {
    if (!above) { tracker.candidateSince = null; return null; }
    if (tracker.candidateSince === null) tracker.candidateSince = now;
    if (now - tracker.candidateSince >= tracker.config.vad_start_duration_ms) {
      tracker.speaking = true;
      tracker.speechStartedAt = tracker.candidateSince;
      tracker.lastVoiceAt = now;
      return { type: "start" };
    }
    return null;
  }

  if (above) tracker.lastVoiceAt = now;
  const elapsed = now - tracker.speechStartedAt;
  if (elapsed >= tracker.config.recording_max_seconds * 1000) {
    tracker.completed = true;
    return { type: "max", durationMs: elapsed };
  }
  if (!above && now - tracker.lastVoiceAt >= tracker.config.vad_end_silence_ms) {
    tracker.completed = true;
    const voicedDuration = Math.max(0, tracker.lastVoiceAt - tracker.speechStartedAt);
    return {
      type: voicedDuration < tracker.config.vad_min_speech_ms ? "discard" : "end",
      durationMs: elapsed,
      voicedDurationMs: voicedDuration,
    };
  }
  return null;
}

async function requestMicrophoneCapability() {
  const questions = runtime.config?.questions;
  const microphoneEnabled = ["microphone", "both"].includes(questions?.input_mode);
  if (!questions?.enabled || !questions.vad_enabled || !microphoneEnabled) {
    runtime.microphoneGranted = false;
    send({ type: "question_capability", available: false });
    return;
  }
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined") {
    runtime.microphoneGranted = false;
    send({ type: "question_capability", available: false });
    return;
  }
  try {
    // Device labels become available only after the first permission grant.
    const permissionStream = await navigator.mediaDevices.getUserMedia({
      audio: microphoneConstraints(),
    });
    permissionStream.getTracks().forEach(track => track.stop());
    runtime.microphoneConstraints = await resolveMicrophoneConstraints();
    const stream = await openMicrophoneStream();
    rememberMicrophoneDevice(stream);
    stream.getTracks().forEach(track => track.stop());
    runtime.microphoneGranted = true;
    send({
      type: "question_capability",
      available: true,
      microphone_label: runtime.microphoneDeviceLabel || null,
    });
  } catch (error) {
    console.warn("[MICROPHONE] Permission unavailable", error);
    runtime.microphoneGranted = false;
    send({ type: "question_capability", available: false });
  }
}

function microphoneConstraints(deviceId = "") {
  const constraints = {
    echoCancellation: true,
    noiseSuppression: true,
    // Automatic gain raises quiet room noise until it looks like speech.
    // Keep the real microphone level so the calibrated VAD remains stable.
    autoGainControl: false,
    channelCount: 1,
    sampleRate: { ideal: 48000 },
    sampleSize: { ideal: 16 },
  };
  if (deviceId) constraints.deviceId = { exact: deviceId };
  return constraints;
}

async function resolveMicrophoneConstraints() {
  const preferred = String(
    runtime.config?.questions?.microphone_device_label || "",
  ).trim().toLowerCase();
  if (!preferred || !navigator.mediaDevices?.enumerateDevices) {
    return microphoneConstraints();
  }
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const match = devices.find(device =>
      device.kind === "audioinput" && device.label.toLowerCase().includes(preferred)
    );
    if (match?.deviceId) return microphoneConstraints(match.deviceId);
    console.warn(`[MICROPHONE] Preferred input was not found: ${preferred}`);
  } catch (error) {
    console.warn("[MICROPHONE] Could not enumerate inputs", error);
  }
  return microphoneConstraints();
}

async function openMicrophoneStream() {
  const constraints = runtime.microphoneConstraints || microphoneConstraints();
  try {
    return await navigator.mediaDevices.getUserMedia({ audio: constraints });
  } catch (error) {
    if (!constraints.deviceId) throw error;
    console.warn("[MICROPHONE] Preferred input unavailable; using default", error);
    runtime.microphoneConstraints = microphoneConstraints();
    return navigator.mediaDevices.getUserMedia({ audio: runtime.microphoneConstraints });
  }
}

function rememberMicrophoneDevice(stream) {
  const track = stream.getAudioTracks?.()[0];
  runtime.microphoneDeviceLabel = track?.label || "default";
  document.body.dataset.microphoneDevice = runtime.microphoneDeviceLabel;
  console.info(`[MICROPHONE] Using input: ${runtime.microphoneDeviceLabel}`);
}

async function prepareAudioContext() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return null;
  if (!runtime.audioContext || runtime.audioContext.state === "closed") {
    runtime.audioContext = new AudioContextClass();
  }
  if (runtime.audioContext.state === "suspended") {
    try { await runtime.audioContext.resume(); }
    catch (error) { console.warn("[MICROPHONE] AudioContext could not resume", error); }
  }
  document.body.dataset.audioContextState = runtime.audioContext.state;
  return runtime.audioContext;
}

async function enterReady(payload) {
  if (!payload.question_session_id) return;
  const inputMode = runtime.config?.questions?.input_mode || "microphone";
  const touchEnabled = ["touch", "both"].includes(inputMode);
  const microphoneEnabled = ["microphone", "both"].includes(inputMode);
  if (!touchEnabled && (!microphoneEnabled || runtime.microphoneGranted !== true)) {
    send({ type: "question_capability", available: false });
    return;
  }
  runtime.abort?.abort();
  runtime.abort = null;
  runtime.answerAbort?.abort();
  runtime.answerAbort = null;
  runtime.activeGreetingId = null;
  runtime.questionSessionId = payload.question_session_id;
  runtime.activeQuestionId = null;
  runtime.state = State.READY;
  document.body.dataset.state = State.READY;
  delete document.body.dataset.customerType;
  elements.menuBoard.hidden = true;
  elements.checkoutBoard.hidden = true;
  elements.kicker.textContent = "ご質問をどうぞ";
  if (touchEnabled && runtime.microphoneGranted !== true) {
    elements.title.textContent = "タッチパネルからお選びください";
    elements.message.textContent = "選んだ質問に鬼店員がお答えします";
  } else if (touchEnabled) {
    elements.title.textContent = "話すか、タッチパネルからお選びください";
    elements.message.textContent = "ご希望の方法で質問できます";
  } else {
    elements.title.textContent = "何でもお尋ねください";
    elements.message.textContent = "質問があれば、そのままお話しください";
  }
  showQuestionText("");
  if (microphoneEnabled && runtime.microphoneGranted === true) {
    await startQuestionMonitoring();
  } else {
    stopQuestionMonitoring();
  }
}

async function startQuestionMonitoring() {
  stopQuestionMonitoring();
  if (runtime.state !== State.READY || runtime.microphoneGranted !== true) return;
  try {
    const stream = await openMicrophoneStream();
    rememberMicrophoneDevice(stream);
    if (runtime.state !== State.READY) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    const audioContext = await prepareAudioContext();
    if (!audioContext || audioContext.state !== "running") {
      throw new Error("Web Audio API is not running");
    }
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    const config = runtime.config.questions;
    const microphone = {
      stream, audioContext, source, analyser, config,
      tracker: createVadTracker(config, Date.now()), capture: null,
      raf: null, finishing: false, lastLevelReportAt: 0,
    };
    runtime.microphone = microphone;
    if (!microphone.tracker.calibrated) {
      elements.title.textContent = "周囲の音を確認しています…";
      elements.message.textContent = "少々お待ちください";
    }
    vadFrame(microphone);
  } catch (error) {
    console.warn("[MICROPHONE] Could not start question monitoring", error);
    runtime.microphoneGranted = false;
    stopQuestionMonitoring();
    send({ type: "question_capability", available: false });
  }
}

function preferredRecorderOptions(config = {}) {
  const audioBitsPerSecond = Number(config.audio_bitrate);
  const bitrate = Number.isFinite(audioBitsPerSecond) && audioBitsPerSecond > 0
    ? { audioBitsPerSecond }
    : {};
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return {};
  for (const mimeType of ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"] ) {
    if (MediaRecorder.isTypeSupported(mimeType)) return { mimeType, ...bitrate };
  }
  return bitrate;
}

function vadFrame(microphone) {
  if (runtime.microphone !== microphone || microphone.finishing ||
      ![State.READY, State.LISTENING].includes(runtime.state)) return;
  const samples = new Float32Array(microphone.analyser.fftSize);
  microphone.analyser.getFloatTimeDomainData(samples);
  let sum = 0;
  for (const sample of samples) sum += sample * sample;
  const rms = Math.sqrt(sum / samples.length);
  const now = Date.now();
  if (now - microphone.lastLevelReportAt >= 200) {
    microphone.lastLevelReportAt = now;
    document.body.dataset.micLevel = rms.toFixed(4);
  }
  const wasCalibrated = microphone.tracker.calibrated;
  const wasCandidate = microphone.tracker.candidateSince !== null && !microphone.tracker.speaking;
  const event = updateVadTracker(microphone.tracker, rms, now);
  document.body.dataset.micThreshold = microphone.tracker.effectiveThreshold.toFixed(4);
  document.body.dataset.micNoiseFloor = microphone.tracker.noiseFloor.toFixed(4);
  if (!wasCalibrated && microphone.tracker.calibrated && runtime.state === State.READY) {
    elements.title.textContent = "何でもお尋ねください";
    elements.message.textContent = "質問があれば、そのままお話しください";
  }
  const isCandidate = microphone.tracker.candidateSince !== null && !microphone.tracker.speaking;
  if (isCandidate && !microphone.capture) {
    const captureDelay = Math.max(
      0,
      microphone.config.vad_start_duration_ms - microphone.config.vad_preroll_ms,
    );
    if (now - microphone.tracker.candidateSince >= captureDelay) {
      startCandidateCapture(microphone);
    }
  } else if (wasCandidate && !isCandidate && !event) {
    discardCandidateCapture(microphone);
  }
  if (event?.type === "start") beginDetectedSpeech(microphone);
  else if (event) void completeDetectedSpeech(microphone, event);
  if (!microphone.finishing && runtime.microphone === microphone) {
    microphone.raf = requestAnimationFrame(() => vadFrame(microphone));
  }
}

function startCandidateCapture(microphone) {
  if (microphone.capture || microphone.finishing || runtime.state !== State.READY) return;
  try {
    const recorder = new MediaRecorder(
      microphone.stream,
      preferredRecorderOptions(microphone.config),
    );
    const capture = { recorder, chunks: [] };
    microphone.capture = capture;
    recorder.addEventListener("dataavailable", event => {
      if (event.data?.size) capture.chunks.push(event.data);
    });
    recorder.start(100);
  } catch (error) {
    microphone.capture = null;
    console.warn("[MICROPHONE] Could not start speech capture", error);
  }
}

function discardCandidateCapture(microphone) {
  const capture = microphone.capture;
  microphone.capture = null;
  if (capture?.recorder?.state !== "inactive") {
    try { capture.recorder.stop(); } catch (error) { console.debug(error); }
  }
}

function beginDetectedSpeech(microphone) {
  if (runtime.state !== State.READY || microphone.finishing) return;
  if (!microphone.capture) startCandidateCapture(microphone);
  runtime.activeQuestionId = createQuestionId();
  runtime.state = State.LISTENING;
  document.body.dataset.state = State.LISTENING;
  elements.kicker.textContent = "ご質問を聞いています";
  elements.title.textContent = "お話を聞いています…";
  elements.message.textContent = "そのままお話しください";
  showQuestionText("");
  send({
    type: "speech_started",
    question_session_id: runtime.questionSessionId,
    question_id: runtime.activeQuestionId,
    vad_level: microphone.tracker.currentLevel,
    vad_threshold: microphone.tracker.effectiveThreshold,
    vad_noise_floor: microphone.tracker.noiseFloor,
  });
}

async function completeDetectedSpeech(microphone, event) {
  if (microphone.finishing) return;
  microphone.finishing = true;
  if (microphone.raf !== null && typeof cancelAnimationFrame === "function") {
    cancelAnimationFrame(microphone.raf);
  }
  const capture = microphone.capture;
  await stopRecorder(capture?.recorder);
  closeMicrophone(microphone);
  if (runtime.microphone === microphone) runtime.microphone = null;
  const sessionId = runtime.questionSessionId;
  const questionId = runtime.activeQuestionId;
  if (!sessionId || !questionId) return;

  if (event.type === "discard") {
    send({ type: "speech_discarded", question_session_id: sessionId, question_id: questionId });
    return;
  }

  runtime.state = State.TRANSCRIBING;
  renderQuestionState(State.TRANSCRIBING);
  const mimeType = capture?.recorder?.mimeType || "audio/webm";
  const audio = new Blob(capture?.chunks || [], { type: mimeType });
  if (!audio.size) {
    send({ type: "question_error", question_session_id: sessionId, question_id: questionId });
    return;
  }
  try {
    const response = await fetch(
      `/api/questions/${encodeURIComponent(sessionId)}/${encodeURIComponent(questionId)}` +
      `?duration_ms=${Math.round(event.durationMs)}`,
      { method: "POST", headers: { "Content-Type": mimeType }, body: audio },
    );
    if (!response.ok) throw new Error(`Question request failed: ${response.status}`);
    const answer = await response.json();
    if (answer.discarded) return;
    if (runtime.questionSessionId !== sessionId || runtime.activeQuestionId !== questionId) return;
    await playQuestionAnswer(answer);
  } catch (error) {
    console.warn("[QUESTION]", error);
    send({ type: "question_error", question_session_id: sessionId, question_id: questionId });
  }
}

async function playQuestionAnswer(payload) {
  if (!questionIdsMatch(payload)) return;
  const sessionId = payload.question_session_id || payload.session_id;
  stopQuestionMonitoring();
  runtime.state = State.SPEAKING;
  document.body.dataset.state = State.SPEAKING;
  runtime.answerAbort?.abort();
  runtime.answerAbort = new AbortController();
  const signal = runtime.answerAbort.signal;
  renderAnswer(payload.question, payload.answer);
  const displayImageUrl = typeof payload.display_image_url === "string"
    && payload.display_image_url.startsWith("/static/images/")
    ? payload.display_image_url
    : null;
  elements.menuBoard.hidden = true;
  elements.checkoutBoard.hidden = !displayImageUrl;
  if (displayImageUrl) {
    elements.checkoutImage.src = displayImageUrl;
    elements.checkoutImage.alt = typeof payload.display_image_alt === "string"
      ? payload.display_image_alt
      : "ご案内画像";
    document.body.dataset.answerImage = ["landscape", "portrait"].includes(
      payload.display_image_layout,
    ) ? payload.display_image_layout : "landscape";
  } else {
    delete document.body.dataset.answerImage;
  }
  const audioUrl = payload.audio_url || (payload.audio_base64
    ? `data:${payload.audio_mime_type || "audio/wav"};base64,${payload.audio_base64}`
    : null);
  let watchdog;
  let timedOut = false;
  const speakingVideo = startSpeakingVideo(
    runtime.config.videos.speaking_intro,
    runtime.config.videos.speaking_loop ||
      runtime.config.videos[runtime.lastCustomerType] ||
      runtime.config.videos.returning,
    signal,
  );
  try {
    await Promise.race([
      (async () => {
        await speakingVideo.ready;
        if (!signal.aborted) await playAnswerVoice(audioUrl, payload.answer, signal);
      })(),
      new Promise(resolve => {
        watchdog = setTimeout(() => {
          timedOut = true;
          runtime.answerAbort?.abort();
          resolve();
        }, runtime.config.questions.speaking_timeout_seconds * 1000);
      }),
    ]);
    if (timedOut && questionIdsMatch(payload)) {
      await new Promise(resolve => setTimeout(
        resolve,
        runtime.config.questions.vad_resume_delay_ms,
      ));
      send({
        type: "question_error",
        question_session_id: sessionId,
        question_id: payload.question_id,
      });
    } else if (!signal.aborted && questionIdsMatch(payload)) {
      send({
        type: "answer_finished",
        question_session_id: sessionId,
        question_id: payload.question_id,
      });
    }
  } finally {
    clearTimeout(watchdog);
    speakingVideo.stop();
    elements.checkoutBoard.hidden = true;
    delete document.body.dataset.answerImage;
  }
}

async function playAnswerVoice(audioUrl, answer, signal) {
  if (audioUrl) {
    elements.message.textContent = answer;
    const played = await playRecordedAudio(audioUrl, signal);
    if (played || signal.aborted) return;
  }
  await speak(answer, signal);
}

function renderQuestionState(state, question = "") {
  runtime.state = state;
  document.body.dataset.state = state;
  if (state !== State.LISTENING) stopQuestionMonitoring();
  elements.kicker.textContent = "ご質問を受け付けました";
  if (state === State.LISTENING) {
    elements.title.textContent = "お話を聞いています…";
    elements.message.textContent = "そのままお話しください";
  } else if (state === State.TRANSCRIBING) {
    elements.title.textContent = "聞き取っています…";
    elements.message.textContent = "少々お待ちください";
  } else {
    elements.title.textContent = "回答を考えています…";
    elements.message.textContent = "もう少々お待ちください";
  }
  if (question) showQuestionText(`お客さま「${question}」`);
}

function renderAnswer(question, answer) {
  runtime.state = State.SPEAKING;
  document.body.dataset.state = State.SPEAKING;
  elements.kicker.textContent = "鬼からの回答";
  elements.title.textContent = "お答えします";
  elements.message.textContent = answer || "少々お待ちください";
  showQuestionText(question ? `お客さま「${question}」` : "");
}

function renderAnswerPreview(question, answer) {
  runtime.state = State.THINKING;
  document.body.dataset.state = State.THINKING;
  elements.kicker.textContent = "鬼からの回答";
  elements.title.textContent = "回答をお伝えします";
  elements.message.textContent = answer || "音声を準備しています…";
  showQuestionText(question ? `お客さま「${question}」` : "");
}

function showQuestionText(text) {
  if (!elements.question) return;
  elements.question.textContent = text;
  elements.question.hidden = !text;
}

function questionIdsMatch(payload) {
  const sessionId = payload.question_session_id || payload.session_id;
  return sessionId === runtime.questionSessionId && payload.question_id === runtime.activeQuestionId;
}

function createQuestionId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function stopRecorder(recorder) {
  return new Promise(resolve => {
    if (!recorder || recorder.state === "inactive") { resolve(); return; }
    recorder.addEventListener("stop", resolve, { once: true });
    try { recorder.stop(); } catch (error) { resolve(); }
  });
}

function closeMicrophone(microphone) {
  try { microphone.source?.disconnect(); } catch (error) { console.debug(error); }
  microphone.stream?.getTracks().forEach(track => track.stop());
  delete document.body.dataset.micLevel;
  delete document.body.dataset.micThreshold;
  delete document.body.dataset.micNoiseFloor;
}

function stopQuestionMonitoring() {
  const microphone = runtime.microphone;
  if (!microphone) return;
  microphone.finishing = true;
  if (microphone.raf !== null && typeof cancelAnimationFrame === "function") {
    cancelAnimationFrame(microphone.raf);
  }
  if (microphone.capture?.recorder?.state !== "inactive") {
    try { microphone.capture.recorder.stop(); } catch (error) { console.debug(error); }
  }
  closeMicrophone(microphone);
  runtime.microphone = null;
}

function returnToIdle() {
  stopQuestionMonitoring();
  runtime.abort?.abort();
  runtime.abort = null;
  runtime.answerAbort?.abort();
  runtime.answerAbort = null;
  elements.greetingAudio.pause();
  elements.greetingAudio.currentTime = 0;
  window.speechSynthesis?.cancel();
  runtime.state = State.IDLE;
  runtime.activeGreetingId = null;
  runtime.questionSessionId = null;
  runtime.activeQuestionId = null;
  document.body.dataset.state = State.IDLE;
  delete document.body.dataset.customerType;
  delete document.body.dataset.answerImage;
  elements.menuBoard.hidden = true;
  elements.checkoutBoard.hidden = true;
  showQuestionText("");
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
  // The start button is a user gesture, so it can also enter browser fullscreen.
  // This hides the Chrome controls and the Windows taskbar on the shop display.
  void enterFullscreen();
  // Unlock Web Audio while this click still counts as a user gesture.
  void prepareAudioContext();
  send({ type: "display_ready" });
  void requestMicrophoneCapability();
  void speakSentence("いらっしゃいませ。", new AbortController().signal)
    .finally(() => { elements.audioButton.disabled = false; });
}
elements.audioButton.addEventListener("click", () => void enableAudio());
elements.video.addEventListener("canplay", () => markVideoError(false));
elements.video.addEventListener("error", () => markVideoError(true));
elements.fullscreenButton.addEventListener("click", () => void toggleFullscreen());

async function enterFullscreen() {
  if (document.fullscreenElement) return true;
  const request = document.documentElement?.requestFullscreen;
  if (typeof request !== "function") return false;
  try {
    await request.call(document.documentElement);
    return true;
  } catch (error) {
    console.warn("[FULLSCREEN]", error);
    return false;
  }
}

async function toggleFullscreen() {
  if (!document.fullscreenElement) {
    await enterFullscreen();
    return;
  }
  if (typeof document.exitFullscreen === "function") {
    try { await document.exitFullscreen(); }
    catch (error) { console.warn("[FULLSCREEN]", error); }
  }
}

async function initialize() {
  elements.audioButton.disabled = true;
  try {
    const response = await fetch("/api/config", { cache: "no-store" });
    if (!response.ok) throw new Error("Configuration request failed");
    runtime.config = await response.json();
    void preloadCharacterVideos(runtime.config.videos);
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
