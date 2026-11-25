const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

function setup() {
  class Element extends EventTarget {
    constructor() {
      super(); this.dataset = {}; this.textContent = ""; this.src = "";
      this.playCount = 0; this.pauseCount = 0;
    }
    getAttribute(name) { return this[name]; }
    load() {}
    play() { this.playCount++; return Promise.resolve(); }
    pause() { this.pauseCount++; }
  }
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const speech = {
    spoken: [], current: null, cancelCount: 0,
    getVoices: () => [{ lang: "ja-JP" }],
    cancel() { this.cancelCount++; this.current = null; },
    speak(utterance) { this.spoken.push(utterance.text); this.current = utterance; },
  };
  const audioContexts = [];
  class AudioContext {
    constructor() { this.state = "suspended"; this.resumeCount = 0; audioContexts.push(this); }
    resume() { this.resumeCount++; this.state = "running"; return Promise.resolve(); }
  }
  class Socket extends EventTarget {
    static OPEN = 1;
    constructor() { super(); this.readyState = 1; this.sent = []; }
    send(message) { this.sent.push(JSON.parse(message)); }
    close() { this.dispatchEvent(new Event("close")); }
  }
  const config = { videos: {
    idle: "/i.mp4", new: "/n.mp4", returning: "/r.mp4",
    speaking_intro: "/turn.mp4", speaking_loop: "/talk.mp4",
  },
    idle_title: "いらっしゃいませ", idle_message: "お待ちください", greeting_timeout_seconds: 30 };
  const context = vm.createContext({
    window: { speechSynthesis: speech, AudioContext }, document: { getElementById: get, body: { dataset: {} } },
    location: { protocol: "http:", host: "localhost" },
    fetch: async () => ({ ok: true, json: async () => config }), WebSocket: Socket,
    SpeechSynthesisUtterance: class { constructor(text) { this.text = text; } },
    AbortController, setTimeout, clearTimeout, console,
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../static/script.js"), "utf8"), context);
  const run = code => vm.runInContext(code, context);
  return { run, get, speech, audioContexts };
}
const flush = () => new Promise(resolve => setImmediate(resolve));
const event = { type: "customer_detected", greeting_id: "g1", customer_type: "new", message: "こんにちは。ごゆっくり。" };

test("microphone constraints can pin a preferred USB input", async () => {
  const { run } = setup();
  await flush();
  assert.equal(run('microphoneConstraints("usb-device").deviceId.exact'), "usb-device");
  assert.equal(run('microphoneConstraints().deviceId'), undefined);
});

test("touch answer speech uses the selected language locale", async () => {
  const { run } = setup();
  await flush();
  assert.equal(run('speechLocale("ja")'), "ja-JP");
  assert.equal(run('speechLocale("en")'), "en-US");
  assert.equal(run('speechLocale("zh")'), "zh-CN");
  assert.equal(run('speechLocale("ko")'), "ko-KR");
  assert.equal(run('speechLocale("unknown")'), "ja-JP");
  assert.equal(run('answerDisplayText("en").title'), "Here is the answer");
  assert.equal(run('answerDisplayText("zh").customer'), "顾客");
  assert.equal(run('answerDisplayText("ko").kicker'), "도깨비 직원의 답변");
});

test("display language translates the customer-facing screen", async () => {
  const { run, get } = setup();
  await flush();
  run('applyDisplayLanguage("en")');
  assert.equal(get("shopMark").textContent, "Ichigo Cafe");
  assert.equal(get("shopSubmark").textContent, "Meals & Coffee");
  assert.equal(get("dialogueTitle").textContent, "Welcome");
  assert.equal(get("dialogueMessage").textContent, "Please wait briefly in front of the camera");
  assert.equal(get("audioButton").textContent, "Start service");
});

test("speaking video plays the turn intro once, then loops until speech finishes", async () => {
  const { run, get, speech } = setup();
  await flush();
  run('runtime.displayActive = true');
  run("handleServerMessage(" + JSON.stringify(event) + ")");
  assert.equal(get("menuBoard").hidden, false);
  assert.equal(get("checkoutBoard").hidden, false);
  assert.equal(get("characterVideo").loop, false);
  assert.equal(get("characterVideo").src, "/turn.mp4");
  assert.equal(speech.spoken.length, 0);
  get("characterVideo").dispatchEvent(new Event("ended"));
  await flush();
  assert.equal(get("dialogueMessage").textContent, "こんにちは。");
  assert.equal(get("characterVideo").loop, true);
  assert.equal(get("characterVideo").src, "/talk.mp4");
  run("handleServerMessage(" + JSON.stringify(event) + ")");
  run("handleServerMessage(" + JSON.stringify({ ...event, greeting_id: "g2" }) + ")");
  assert.equal(speech.spoken.length, 1);
  speech.current.onend();
  await flush();
  assert.equal(get("dialogueMessage").textContent, "ごゆっくり。");
  speech.current.onend();
  await flush();
  assert.equal(run("runtime.state"), "IDLE");
  assert.equal(get("menuBoard").hidden, true);
  assert.equal(get("checkoutBoard").hidden, true);
  assert.equal(get("characterVideo").src, "/i.mp4");
  assert.ok(get("characterVideo").pauseCount >= 1);
  assert.equal(run("runtime.socket.sent[0].greeting_id"), "g1");
});

test("first-visit guidance images stay hidden for returning customers", async () => {
  const { run, get } = setup();
  await flush();
  run('runtime.displayActive = true');
  run("handleServerMessage(" + JSON.stringify({ ...event, customer_type: "returning" }) + ")");
  assert.equal(get("menuBoard").hidden, true);
  assert.equal(get("checkoutBoard").hidden, true);
  run("returnToIdle()");
});

test("new customers use configured recorded audio", async () => {
  const { run, get, speech } = setup();
  await flush();
  run('runtime.config.audio = {new: "/first-visit.wav", returning: null}');
  run('runtime.subtitleCues = {new: [{start: 0, end: 1, text: "最初の字幕"}, {start: 1, end: 2, text: "次の字幕"}]}');
  run('runtime.displayActive = true');
  run("handleServerMessage(" + JSON.stringify({ ...event, message: "録音音声です。" }) + ")");
  assert.equal(get("greetingAudio").src, "");
  get("characterVideo").dispatchEvent(new Event("ended"));
  await flush();
  assert.equal(get("greetingAudio").src, "/first-visit.wav");
  assert.equal(get("dialogueMessage").textContent, "最初の字幕");
  get("greetingAudio").currentTime = 1.2;
  get("greetingAudio").dispatchEvent(new Event("timeupdate"));
  assert.equal(get("dialogueMessage").textContent, "次の字幕");
  assert.equal(speech.spoken.length, 0);
  get("greetingAudio").dispatchEvent(new Event("ended"));
  await flush();
  assert.equal(run("runtime.state"), "IDLE");
});

test("recorded audio URL uses the server asset version", async () => {
  const { run, get } = setup();
  await flush();
  run('runtime.config.audio = {new: "/first-visit.wav"}');
  run('runtime.config.audio_asset_version = "updated-audio"');
  run('runtime.displayActive = true');
  run("handleServerMessage(" + JSON.stringify({ ...event, message: "録音音声です。" }) + ")");
  get("characterVideo").dispatchEvent(new Event("ended"));
  await flush();
  assert.equal(get("greetingAudio").src, "/first-visit.wav?v=updated-audio");
  run("returnToIdle()");
});

test("returning customers select the correct recorded audio", async () => {
  const { run, get, speech } = setup();
  await flush();
  run('runtime.config.audio = {new: null, returning: "/returning.wav", returning_discount: "/returning-discount.wav"}');
  run('runtime.displayActive = true');
  run("handleServerMessage(" + JSON.stringify({
    ...event, greeting_id: "returning-1", customer_type: "returning", discount_eligible: false,
  }) + ")");
  get("characterVideo").dispatchEvent(new Event("ended"));
  await flush();
  assert.equal(get("greetingAudio").src, "/returning.wav");
  get("greetingAudio").dispatchEvent(new Event("ended"));
  await flush();

  run("handleServerMessage(" + JSON.stringify({
    ...event, greeting_id: "returning-2", customer_type: "returning", discount_eligible: true,
  }) + ")");
  get("characterVideo").dispatchEvent(new Event("ended"));
  await flush();
  assert.equal(get("greetingAudio").src, "/returning-discount.wav");
  assert.equal(speech.spoken.length, 0);
  run("returnToIdle()");
});

test("server cancellation removes stale callbacks and stops speech", async () => {
  const { run, get, speech } = setup();
  await flush();
  run("runtime.displayActive = true");
  run("handleServerMessage(" + JSON.stringify(event) + ")");
  get("characterVideo").dispatchEvent(new Event("ended"));
  await flush();
  const utterance = speech.current;
  run('handleServerMessage({type:"state_changed",state:"IDLE"})');
  await flush();
  assert.equal(run("runtime.state"), "IDLE");
  assert.equal(utterance.onend, null);
  assert.equal(run("runtime.socket.sent.length"), 0);
});

test("intro video failure falls back to the speaking loop and still finishes", async () => {
  const { run, get, speech } = setup();
  await flush();
  run("runtime.displayActive = true");
  run("handleServerMessage(" + JSON.stringify({ ...event, message: "こんにちは。" }) + ")");
  get("characterVideo").dispatchEvent(new Event("error"));
  await flush();
  assert.equal(get("characterVideo").src, "/talk.mp4");
  assert.equal(get("characterVideo").loop, true);
  assert.equal(get("videoFrame").dataset.videoError, "false");
  speech.current.onend();
  await flush();
  assert.equal(run("runtime.state"), "IDLE");
});

test("speech failure keeps readable subtitles and can be cancelled", async () => {
  const { run, get, speech } = setup();
  await flush();
  run("runtime.displayActive = true");
  run("handleServerMessage(" + JSON.stringify(event) + ")");
  get("characterVideo").dispatchEvent(new Event("ended"));
  await flush();
  speech.current.onerror({ error: "not-allowed" });
  await flush();
  assert.equal(run("runtime.state"), "GREETING");
  assert.equal(get("dialogueMessage").textContent, "こんにちは。");
  run("returnToIdle()");
  await flush();
  assert.equal(run("runtime.state"), "IDLE");
});

test("touch-only start registers display without creating Web Audio", async () => {
  const { run, get, speech, audioContexts } = setup();
  await flush();
  run('runtime.config.questions = {input_mode: "touch"}');
  get("audioButton").dispatchEvent(new Event("click"));
  await flush();
  assert.equal(run("runtime.enabled"), true);
  assert.equal(run("runtime.socket.sent[0].type"), "display_ready");
  assert.equal(audioContexts.length, 0);
  assert.equal(speech.spoken.at(-1), "いらっしゃいませ。");
  speech.current.onend();
});

test("microphone mode unlocks Web Audio on the start gesture", async () => {
  const { run, get, speech, audioContexts } = setup();
  await flush();
  run('runtime.config.questions = {input_mode: "microphone"}');
  get("audioButton").dispatchEvent(new Event("click"));
  await flush();
  assert.equal(audioContexts.length, 1);
  assert.equal(audioContexts[0].state, "running");
  assert.equal(audioContexts[0].resumeCount, 1);
  assert.equal(speech.spoken.at(-1), "いらっしゃいませ。");
  speech.current.onend();
});

test("ambient assistance unlocks Web Audio even in touch-only mode", async () => {
  const { run, get, speech, audioContexts } = setup();
  await flush();
  run('runtime.config.questions = {input_mode: "touch"}');
  run('runtime.config.assistance_voice = {enabled: true}');
  get("audioButton").dispatchEvent(new Event("click"));
  await flush();
  assert.equal(audioContexts.length, 1);
  assert.equal(audioContexts[0].state, "running");
  assert.equal(speech.spoken.at(-1), "いらっしゃいませ。");
  speech.current.onend();
  await flush();
  assert.equal(run("runtime.assistanceSuppressed"), false);
});

test("question answer plays the turn intro, then loops only while the voice is speaking", async () => {
  const { run, get, speech } = setup();
  await flush();
  run(`runtime.config.questions = {
    speaking_timeout_seconds: 30, vad_resume_delay_ms: 0
  }`);
  run('runtime.questionSessionId = "session-1"; runtime.activeQuestionId = "question-1"');
  const playback = run(`playQuestionAnswer({
    session_id: "session-1", question_session_id: "session-1",
    question_id: "question-1", question: "好きな色は？",
    answer: "赤が好きです。", audio_base64: null
  })`);
  await flush();
  assert.equal(get("characterVideo").loop, false);
  assert.equal(get("characterVideo").src, "/turn.mp4");
  assert.equal(speech.spoken.length, 0);
  get("characterVideo").dispatchEvent(new Event("ended"));
  await flush();
  assert.equal(get("characterVideo").loop, true);
  assert.equal(get("characterVideo").src, "/talk.mp4");
  speech.current.onend();
  await playback;
  assert.equal(get("characterVideo").loop, false);
  assert.ok(get("characterVideo").pauseCount >= 1);
  assert.equal(run("runtime.socket.sent.at(-1).type"), "answer_finished");
});

test("touch panel question is adopted by the main display and plays its answer", async () => {
  const { run, get } = setup();
  await flush();
  run(`runtime.config.questions = {
    input_mode: "touch", speaking_timeout_seconds: 30, vad_resume_delay_ms: 0
  }`);
  run("runtime.displayActive = true");
  run(`handleServerMessage({
    type: "touch_question_started", state: "THINKING",
    question_session_id: "touch-session", question_id: "touch-question",
    question: "定食はいくらですか？"
  })`);
  assert.equal(run("runtime.questionSessionId"), "touch-session");
  assert.equal(run("runtime.activeQuestionId"), "touch-question");
  assert.equal(get("questionText").textContent, "お客さま「定食はいくらですか？」");
  run(`handleServerMessage({
    type: "touch_answer_started", state: "SPEAKING",
    question_session_id: "touch-session", question_id: "touch-question",
    question: "定食はいくらですか？", answer: "豚汁たまご定食は1,200円です。",
    audio_url: "/static/audio/faq/meal-price.wav",
    display_image_url: "/static/images/checkout-machine.png",
    display_image_layout: "landscape",
    display_image_alt: "精算機の操作画面"
  })`);
  await flush();
  assert.equal(get("checkoutBoard").hidden, false);
  assert.equal(get("checkoutImage").src, "/static/images/checkout-machine.png");
  assert.equal(get("checkoutImage").alt, "精算機の操作画面");
  assert.equal(run("document.body.dataset.answerImage"), "landscape");
  assert.equal(get("greetingAudio").src, "");
  get("characterVideo").dispatchEvent(new Event("ended"));
  await flush();
  assert.equal(get("greetingAudio").src, "/static/audio/faq/meal-price.wav");
  get("greetingAudio").dispatchEvent(new Event("ended"));
  await flush();
  assert.equal(get("checkoutBoard").hidden, true);
  assert.equal(run("document.body.dataset.answerImage"), undefined);
  assert.equal(run("runtime.socket.sent.at(-1).type"), "answer_finished");
  assert.equal(run("runtime.socket.sent.at(-1).question_session_id"), "touch-session");
});

test("answer text is shown before VOICEVOX audio is ready", async () => {
  const { run, get } = setup();
  await flush();
  run('runtime.questionSessionId = "session-1"; runtime.activeQuestionId = "question-1"');
  run(`handleServerMessage({
    type: "answer_text_ready", question_session_id: "session-1",
    question_id: "question-1", question: "豚汁は？",
    answer: "豚汁はお代わり自由です。"
  })`);
  assert.equal(run("runtime.state"), "THINKING");
  assert.equal(get("dialogueTitle").textContent, "回答をお伝えします");
  assert.equal(get("dialogueMessage").textContent, "豚汁はお代わり自由です。");
});

test("question answers prefer a prerecorded audio URL", async () => {
  const { run, get } = setup();
  await flush();
  run(`runtime.config.questions = {
    speaking_timeout_seconds: 30, vad_resume_delay_ms: 0
  }`);
  run('runtime.questionSessionId = "session-1"; runtime.activeQuestionId = "question-1"');
  const playback = run(`playQuestionAnswer({
    session_id: "session-1", question_session_id: "session-1",
    question_id: "question-1", question: "定食はいくら？",
    answer: "1,200円です。", audio_url: "/static/audio/faq/meal-price.wav",
    audio_base64: null
  })`);
  await flush();
  assert.equal(get("greetingAudio").src, "");
  get("characterVideo").dispatchEvent(new Event("ended"));
  await flush();
  assert.equal(get("greetingAudio").src, "/static/audio/faq/meal-price.wav");
  get("greetingAudio").dispatchEvent(new Event("ended"));
  await playback;
  assert.equal(run("runtime.socket.sent.at(-1).type"), "answer_finished");
});

test("translated touch answer keeps Japanese speech", async () => {
  const { run, get, speech } = setup();
  await flush();
  run(`runtime.config.questions = {
    speaking_timeout_seconds: 30, vad_resume_delay_ms: 0
  }`);
  run('runtime.questionSessionId = "session-en"; runtime.activeQuestionId = "question-en"');
  const playback = run(`playQuestionAnswer({
    session_id: "session-en", question_session_id: "session-en",
    question_id: "question-en", question: "How do I pay?",
    answer: "Please insert cash into the payment machine.",
    spoken_answer: "精算機に現金を投入してください。",
    answer_language: "en", audio_url: null, audio_base64: null
  })`);
  get("characterVideo").dispatchEvent(new Event("ended"));
  await flush();
  assert.equal(speech.spoken.at(-1), "精算機に現金を投入してください。");
  assert.equal(get("dialogueMessage").textContent, "Please insert cash into the payment machine.");
  speech.current.onend();
  await playback;
});

test("VAD requires sustained sound and stops after silence", async () => {
  const { run } = setup();
  await flush();
  run(`tracker = createVadTracker({
    vad_start_threshold: 0.03, vad_start_duration_ms: 300,
    vad_end_silence_ms: 1000, vad_min_speech_ms: 400,
    recording_max_seconds: 15
  }, 0)`);
  assert.equal(run("updateVadTracker(tracker, 0.04, 0)"), null);
  assert.equal(run("updateVadTracker(tracker, 0.04, 299)"), null);
  assert.equal(run("updateVadTracker(tracker, 0.04, 300).type"), "start");
  assert.equal(run("updateVadTracker(tracker, 0.04, 900)"), null);
  assert.equal(run("updateVadTracker(tracker, 0.0, 1899)"), null);
  assert.equal(run("updateVadTracker(tracker, 0.0, 1900).type"), "end");
});

test("ambient assistance requires sustained speech-like sound", async () => {
  const { run } = setup();
  await flush();
  run(`assistanceTracker = createAssistanceVoiceTracker({
    start_threshold: 0.035, start_duration_ms: 700,
    calibration_ms: 0, noise_multiplier: 2, noise_margin: 0.008,
    speech_band_ratio: 0.5, zcr_min: 0.005, zcr_max: 0.30
  }, 0)`);
  assert.equal(run("updateAssistanceVoiceTracker(assistanceTracker, 0.05, 0.7, 0.08, 0)"), null);
  assert.equal(run("updateAssistanceVoiceTracker(assistanceTracker, 0.05, 0.7, 0.08, 699)"), null);
  assert.equal(
    run("updateAssistanceVoiceTracker(assistanceTracker, 0.05, 0.7, 0.08, 700).type"),
    "voice",
  );
});

test("ambient assistance rejects transient and non-speech-band noise", async () => {
  const { run } = setup();
  await flush();
  run(`assistanceTracker = createAssistanceVoiceTracker({
    start_threshold: 0.035, start_duration_ms: 700,
    calibration_ms: 0, noise_multiplier: 2, noise_margin: 0.008,
    speech_band_ratio: 0.5, zcr_min: 0.005, zcr_max: 0.30
  }, 0)`);
  assert.equal(run("updateAssistanceVoiceTracker(assistanceTracker, 0.08, 0.2, 0.08, 0)"), null);
  assert.equal(run("updateAssistanceVoiceTracker(assistanceTracker, 0.08, 0.2, 0.08, 1000)"), null);
  assert.equal(run("assistanceTracker.candidateSince"), null);
  assert.equal(run("updateAssistanceVoiceTracker(assistanceTracker, 0.05, 0.7, 0.08, 1100)"), null);
  assert.equal(run("updateAssistanceVoiceTracker(assistanceTracker, 0.0, 0, 0, 1200)"), null);
  assert.equal(run("updateAssistanceVoiceTracker(assistanceTracker, 0.05, 0.7, 0.08, 1900)"), null);
  assert.equal(run("assistanceTracker.triggered"), false);
});

test("ambient assistance pauses during the touch-panel READY window", async () => {
  const { run } = setup();
  await flush();
  run('runtime.config.questions = {input_mode: "touch"}; runtime.state = State.READY');
  assert.equal(run("assistanceMonitoringAllowed()"), false);
  run("runtime.state = State.IDLE");
  assert.equal(run("assistanceMonitoringAllowed()"), true);
  run("runtime.state = State.SPEAKING");
  assert.equal(run("assistanceMonitoringAllowed()"), false);
});

test("VAD calibrates to ambient noise before accepting speech", async () => {
  const { run } = setup();
  await flush();
  run(`tracker = createVadTracker({
    vad_start_threshold: 0.02, vad_start_duration_ms: 350,
    vad_end_silence_ms: 450, vad_min_speech_ms: 500,
    recording_max_seconds: 15, vad_calibration_ms: 1000,
    vad_noise_multiplier: 2, vad_noise_margin: 0.006
  }, 0)`);
  assert.equal(run("updateVadTracker(tracker, 0.1, 0)"), null);
  assert.equal(run("updateVadTracker(tracker, 0.015, 500)"), null);
  assert.equal(run("updateVadTracker(tracker, 0.015, 1000)"), null);
  assert.equal(run("tracker.calibrated"), true);
  assert.equal(run("tracker.effectiveThreshold"), 0.03);
  assert.equal(run("updateVadTracker(tracker, 0.025, 1500)"), null);
  assert.equal(run("tracker.candidateSince"), null);
  assert.equal(run("updateVadTracker(tracker, 0.04, 1600)"), null);
  assert.equal(run("updateVadTracker(tracker, 0.04, 1950).type"), "start");
});

test("VAD rejects transient and too-short noise", async () => {
  const { run } = setup();
  await flush();
  run(`tracker = createVadTracker({
    vad_start_threshold: 0.03, vad_start_duration_ms: 300,
    vad_end_silence_ms: 1000, vad_min_speech_ms: 400,
    recording_max_seconds: 15
  }, 0)`);
  assert.equal(run("updateVadTracker(tracker, 0.04, 0)"), null);
  assert.equal(run("updateVadTracker(tracker, 0.0, 100)"), null);
  assert.equal(run("tracker.speaking"), false);
  run("updateVadTracker(tracker, 0.04, 200)");
  assert.equal(run("updateVadTracker(tracker, 0.04, 500).type"), "start");
  assert.equal(run("updateVadTracker(tracker, 0.0, 1500).type"), "discard");
});

test("VAD enforces maximum recording duration", async () => {
  const { run } = setup();
  await flush();
  run(`tracker = createVadTracker({
    vad_start_threshold: 0.03, vad_start_duration_ms: 300,
    vad_end_silence_ms: 1000, vad_min_speech_ms: 400,
    recording_max_seconds: 15
  }, 0)`);
  run("updateVadTracker(tracker, 0.04, 0)");
  run("updateVadTracker(tracker, 0.04, 300)");
  assert.equal(run("updateVadTracker(tracker, 0.04, 15000).type"), "max");
});

test("SPEAKING state never accepts a new greeting", async () => {
  const { run } = setup();
  await flush();
  run('runtime.displayActive = true; runtime.state = State.SPEAKING');
  run("handleServerMessage(" + JSON.stringify(event) + ")");
  assert.equal(run("runtime.state"), "SPEAKING");
});
