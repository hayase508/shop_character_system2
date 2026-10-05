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
  assert.equal(run("runtime.socket.sent[0].greeting_id"), "g1");
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
