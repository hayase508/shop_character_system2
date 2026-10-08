const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

function setup() {
  class Element extends EventTarget {
    constructor() { super(); this.dataset = {}; this.textContent = ""; this.src = ""; }
    getAttribute(name) { return this[name]; }
    load() {}
    play() { return Promise.resolve(); }
    pause() {}
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
  class Socket extends EventTarget {
    static OPEN = 1;
    constructor() { super(); this.readyState = 1; this.sent = []; }
    send(message) { this.sent.push(JSON.parse(message)); }
    close() { this.dispatchEvent(new Event("close")); }
  }
  const config = { videos: { idle: "/i.mp4", new: "/n.mp4", returning: "/r.mp4" },
    idle_title: "いらっしゃいませ", idle_message: "お待ちください", greeting_timeout_seconds: 30 };
  const context = vm.createContext({
    window: { speechSynthesis: speech }, document: { getElementById: get, body: { dataset: {} } },
    location: { protocol: "http:", host: "localhost" },
    fetch: async () => ({ ok: true, json: async () => config }), WebSocket: Socket,
    SpeechSynthesisUtterance: class { constructor(text) { this.text = text; } },
    AbortController, setTimeout, clearTimeout, console,
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../static/script.js"), "utf8"), context);
  const run = code => vm.runInContext(code, context);
  return { run, get, speech };
}
const flush = () => new Promise(resolve => setImmediate(resolve));
const event = { type: "customer_detected", greeting_id: "g1", customer_type: "new", message: "こんにちは。ごゆっくり。" };

test("speech and video must both finish; duplicate/different events cannot overlap", async () => {
  const { run, get, speech } = setup();
  await flush();
  run('runtime.displayActive = true');
  run("handleServerMessage(" + JSON.stringify(event) + ")");
  assert.equal(get("dialogueMessage").textContent, "こんにちは。");
  assert.equal(get("menuBoard").hidden, false);
  run("handleServerMessage(" + JSON.stringify(event) + ")");
  run("handleServerMessage(" + JSON.stringify({ ...event, greeting_id: "g2" }) + ")");
  assert.equal(speech.spoken.length, 1);
  speech.current.onend();
  await flush();
  assert.equal(get("dialogueMessage").textContent, "ごゆっくり。");
  speech.current.onend();
  await flush();
  assert.equal(run("runtime.state"), "GREETING");
  get("characterVideo").dispatchEvent(new Event("ended"));
  await flush();
  assert.equal(run("runtime.state"), "IDLE");
  assert.equal(get("menuBoard").hidden, true);
  assert.equal(run("runtime.socket.sent[0].greeting_id"), "g1");
});

test("usage guide stays hidden for returning customers", async () => {
  const { run, get } = setup();
  await flush();
  run('runtime.displayActive = true');
  run("handleServerMessage(" + JSON.stringify({ ...event, customer_type: "returning" }) + ")");
  assert.equal(get("menuBoard").hidden, true);
  run("returnToIdle()");
});

test("new customers use configured recorded audio", async () => {
  const { run, get, speech } = setup();
  await flush();
  run('runtime.config.audio = {new: "/first-visit.wav", returning: null}');
  run('runtime.subtitleCues = {new: [{start: 0, end: 1, text: "最初の字幕"}, {start: 1, end: 2, text: "次の字幕"}]}');
  run('runtime.displayActive = true');
  run("handleServerMessage(" + JSON.stringify({ ...event, message: "録音音声です。" }) + ")");
  assert.equal(get("greetingAudio").src, "/first-visit.wav");
  assert.equal(get("dialogueMessage").textContent, "最初の字幕");
  get("greetingAudio").currentTime = 1.2;
  get("greetingAudio").dispatchEvent(new Event("timeupdate"));
  assert.equal(get("dialogueMessage").textContent, "次の字幕");
  assert.equal(speech.spoken.length, 0);
  get("characterVideo").dispatchEvent(new Event("ended"));
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
  assert.equal(get("greetingAudio").src, "/returning.wav");
  get("characterVideo").dispatchEvent(new Event("ended"));
  get("greetingAudio").dispatchEvent(new Event("ended"));
  await flush();

  run("handleServerMessage(" + JSON.stringify({
    ...event, greeting_id: "returning-2", customer_type: "returning", discount_eligible: true,
  }) + ")");
  assert.equal(get("greetingAudio").src, "/returning-discount.wav");
  assert.equal(speech.spoken.length, 0);
  run("returnToIdle()");
});

test("server cancellation removes stale callbacks and stops speech", async () => {
  const { run, speech } = setup();
  await flush();
  run("runtime.displayActive = true");
  run("handleServerMessage(" + JSON.stringify(event) + ")");
  const utterance = speech.current;
  run('handleServerMessage({type:"state_changed",state:"IDLE"})');
  await flush();
  assert.equal(run("runtime.state"), "IDLE");
  assert.equal(utterance.onend, null);
  assert.equal(run("runtime.socket.sent.length"), 0);
});

test("video failure still allows speech to finish", async () => {
  const { run, get, speech } = setup();
  await flush();
  run("runtime.displayActive = true");
  run("handleServerMessage(" + JSON.stringify({ ...event, message: "こんにちは。" }) + ")");
  get("characterVideo").dispatchEvent(new Event("error"));
  assert.equal(get("videoFrame").dataset.videoError, "true");
  speech.current.onend();
  await flush();
  assert.equal(run("runtime.state"), "IDLE");
});

test("speech failure keeps readable subtitles and can be cancelled", async () => {
  const { run, get, speech } = setup();
  await flush();
  run("runtime.displayActive = true");
  run("handleServerMessage(" + JSON.stringify(event) + ")");
  speech.current.onerror({ error: "not-allowed" });
  await flush();
  assert.equal(run("runtime.state"), "GREETING");
  assert.equal(get("dialogueMessage").textContent, "こんにちは。");
  run("returnToIdle()");
  await flush();
  assert.equal(run("runtime.state"), "IDLE");
});

test("start click registers display immediately without waiting for speech", async () => {
  const { run, get, speech } = setup();
  await flush();
  get("audioButton").dispatchEvent(new Event("click"));
  await flush();
  assert.equal(run("runtime.enabled"), true);
  assert.equal(run("runtime.socket.sent[0].type"), "display_ready");
  assert.equal(speech.spoken.at(-1), "いらっしゃいませ。");
});
