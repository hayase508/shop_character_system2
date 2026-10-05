// Optional integration QA: npm install --no-save playwright (uses installed Edge).
// Run against CAMERA_ENABLED=false DEBUG_MODE=true on port 8765.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");

(async () => {
  fs.mkdirSync(".test-artifacts", { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: "msedge" });
  try {
    const native = await browser.newPage();
    await native.goto("http://127.0.0.1:8765");
    const voices = await native.evaluate(() =>
      window.speechSynthesis.getVoices().map(v => ({ name: v.name, lang: v.lang })));
    console.log("Native voices at load:", JSON.stringify(voices));
    await native.close();

    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    // Deterministic speech adapter. Native OS audio is not asserted by this test.
    await context.addInitScript(() => {
      window.testSpoken = [];
      let timer;
      Object.defineProperty(window, "speechSynthesis", { value: {
        // Native SpeechSynthesisUtterance.voice only accepts native voice objects.
        getVoices: () => [],
        cancel: () => clearTimeout(timer),
        speak: utterance => {
          window.testSpoken.push(utterance.text);
          timer = setTimeout(() => utterance.onend?.(), 350);
        },
      } });
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto("http://127.0.0.1:8765");
    await page.waitForFunction(() => {
      const v = document.getElementById("characterVideo");
      return v.readyState >= 2 && v.videoWidth > 0 && v.currentTime > 0;
    });
    console.log("Video:", await page.locator("#characterVideo").evaluate(v =>
      ({ width: v.videoWidth, height: v.videoHeight, duration: v.duration, muted: v.muted })));
    await page.screenshot({ path: ".test-artifacts/idle.png" });
    await page.getByRole("button", { name: "接客を開始（音声を有効にする）" }).click();
    await page.waitForFunction(() => document.getElementById("audioButton").dataset.enabled === "true");

    for (const [name, route, eligible] of [
      ["new", "/api/debug/new-customer", false],
      ["returning-10", "/api/debug/returning-customer?days_since_last_visit=10", true],
      ["returning-60", "/api/debug/returning-customer?days_since_last_visit=60", true],
      ["returning-61", "/api/debug/returning-customer?days_since_last_visit=61", false],
    ]) {
      const response = await page.request.post("http://127.0.0.1:8765" + route);
      assert.equal(response.status(), 200);
      assert.equal((await response.json()).event.discount_eligible, eligible);
      await page.waitForFunction(() => document.body.dataset.state === "GREETING");
      if (name === "new") await page.screenshot({ path: ".test-artifacts/greeting.png" });
      await page.waitForFunction(() => document.body.dataset.state === "IDLE", null, { timeout: 20000 });
      assert.equal((await (await page.request.get("http://127.0.0.1:8765/api/state")).json()).state, "IDLE");
      console.log("Passed:", name);
    }
    assert.equal(errors.length, 0, errors.join("\n"));
    assert.ok(await page.evaluate(() => window.testSpoken.length > 10),
      "The speech adapter must actually run rather than falling back to text-only.");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: ".test-artifacts/mobile.png" });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    assert.equal(overflow, false);
    console.log("Browser integration passed; native audio remains a manual check.");
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
