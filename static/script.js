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
  shopMark: document.getElementById("shopMark"),
  shopSubmark: document.getElementById("shopSubmark"),
  characterStage: document.getElementById("characterStage"),
  usageGuideImage: document.getElementById("usageGuideImage"),
  voiceCredit: document.getElementById("voiceCredit"),
};
const runtime = {
  state: State.IDLE, socket: null, activeGreetingId: null,
  enabled: false, displayActive: false, abort: null, answerAbort: null,
  utterance: null, reconnectDelayMs: 1000, reconnectTimer: null,
  config: null, subtitleCues: {}, microphoneGranted: null, microphone: null,
  microphoneConstraints: null, microphoneDeviceLabel: "",
  audioContext: null, assistanceMicrophone: null, assistanceTimer: null,
  assistanceCooldownUntil: 0, assistanceSuppressed: false, assistanceGeneration: 0,
  questionSessionId: null, activeQuestionId: null, lastCustomerType: "returning",
  displayLanguage: "ja",
};

const displayText = {
  ja: {
    documentTitle: "いちごうカフェ", shopMark: "いちごうカフェ", shopSubmark: "御食事と珈琲",
    characterLabel: "鬼キャラクター", usageGuideAlt: "お店の利用方法。豚汁・たまご・ご飯のお代わり自由、飲み物、再来店特典、セルフ配膳のご案内",
    checkoutAlt: "精算機の画面。通常1,200円の定食と、QRコード利用時の500円表示",
    audioButton: "接客を開始", fullscreen: "全画面表示", exitFullscreen: "全画面解除",
    voiceCredit: "VOICEVOX:四国めたん", ready: "準備完了", reconnecting: "再接続中",
    welcoming: "お迎えしています", otherDisplay: "別の画面で接客中", preparing: "準備中です",
    microphoneWaiting: "マイク待機中", microphoneCheck: "マイクを確認してください",
    microphonePermission: "ブラウザでマイクの使用を許可してください",
    idleKicker: "お客様をお待ちしています", idleTitle: "いらっしゃいませ",
    idleMessage: "カメラの前で少しお待ちください",
    newKicker: "初めてのご来店", newTitle: "はじめまして",
    returningKicker: "またのご来店", returningTitle: "おかえりなさい",
    readyKicker: "ご質問をどうぞ", touchTitle: "タッチパネルからお選びください",
    touchMessage: "選んだ質問に鬼店員がお答えします", askTitle: "何でもお尋ねください",
    askMessage: "質問があれば、そのままお話しください", calibrationTitle: "周囲の音を確認しています…",
    listeningKicker: "ご質問を聞いています", listeningTitle: "お話を聞いています…",
    listeningMessage: "そのままお話しください", transcribingTitle: "聞き取っています…",
    wait: "少々お待ちください", previewKicker: "鬼からの回答",
    previewTitle: "回答をお伝えします", preparingAudio: "音声を準備しています…",
    assistanceAnswer: "何かお困りでしょうか？タッチパネルから私に質問してくださいね。",
  },
  en: {
    documentTitle: "Ichigo Cafe", shopMark: "Ichigo Cafe", shopSubmark: "Meals & Coffee",
    characterLabel: "Oni attendant", usageGuideAlt: "Guide to meals, free refills, drinks, the return-visit discount, and self-service",
    checkoutAlt: "Payment screen showing the regular 1,200-yen set meal and the 500-yen QR price",
    audioButton: "Start service", fullscreen: "Full screen", exitFullscreen: "Exit full screen",
    voiceCredit: "VOICEVOX: Shikoku Metan", ready: "Ready", reconnecting: "Reconnecting",
    welcoming: "Welcoming guests", otherDisplay: "Serving on another display", preparing: "Preparing",
    microphoneWaiting: "Microphone ready", microphoneCheck: "Check the microphone",
    microphonePermission: "Please allow microphone access in your browser",
    idleKicker: "Waiting for guests", idleTitle: "Welcome",
    idleMessage: "Please wait briefly in front of the camera",
    newKicker: "Your first visit", newTitle: "Nice to meet you",
    returningKicker: "Welcome back", returningTitle: "Welcome back",
    readyKicker: "Questions", touchTitle: "Please use the touch panel",
    touchMessage: "Select a question and the oni attendant will answer", askTitle: "Please ask anything",
    askMessage: "If you have a question, please speak", calibrationTitle: "Checking the room sound…",
    listeningKicker: "Listening to your question", listeningTitle: "Listening…",
    listeningMessage: "Please continue speaking", transcribingTitle: "Transcribing…",
    wait: "Please wait", previewKicker: "Answer from the attendant",
    previewTitle: "Here is the answer", preparingAudio: "Preparing the audio…",
    assistanceAnswer: "May I help you? Please select a question on the touch panel.",
  },
  zh: {
    documentTitle: "一合咖啡馆", shopMark: "一合咖啡馆", shopSubmark: "餐饮与咖啡",
    characterLabel: "鬼店员", usageGuideAlt: "餐点、免费续加、饮品、再次来店优惠及自助取餐指南",
    checkoutAlt: "显示普通套餐1,200日元和二维码优惠价500日元的结算画面",
    audioButton: "开始接待", fullscreen: "全屏显示", exitFullscreen: "退出全屏",
    voiceCredit: "VOICEVOX：四国米丹", ready: "准备完毕", reconnecting: "正在重新连接",
    welcoming: "正在迎接顾客", otherDisplay: "正在其他画面接待", preparing: "准备中",
    microphoneWaiting: "麦克风待机中", microphoneCheck: "请检查麦克风",
    microphonePermission: "请在浏览器中允许使用麦克风",
    idleKicker: "正在等候顾客", idleTitle: "欢迎光临",
    idleMessage: "请在摄像头前稍候",
    newKicker: "首次光临", newTitle: "初次见面",
    returningKicker: "再次光临", returningTitle: "欢迎回来",
    readyKicker: "请选择问题", touchTitle: "请使用触摸屏选择",
    touchMessage: "选择问题后，鬼店员会为您回答", askTitle: "欢迎提问",
    askMessage: "如有问题，请直接说出来", calibrationTitle: "正在检测周围声音…",
    listeningKicker: "正在听取问题", listeningTitle: "正在聆听…",
    listeningMessage: "请继续说", transcribingTitle: "正在识别…",
    wait: "请稍候", previewKicker: "鬼店员的回答",
    previewTitle: "为您回答", preparingAudio: "正在准备语音…",
    assistanceAnswer: "您需要帮助吗？请在触摸屏上选择问题。",
  },
  ko: {
    documentTitle: "이치고 카페", shopMark: "이치고 카페", shopSubmark: "식사와 커피",
    characterLabel: "도깨비 직원", usageGuideAlt: "식사, 무료 리필, 음료, 재방문 혜택 및 셀프서비스 안내",
    checkoutAlt: "일반 정식 1,200엔과 QR 할인가 500엔을 표시한 결제 화면",
    audioButton: "접객 시작", fullscreen: "전체 화면", exitFullscreen: "전체 화면 종료",
    voiceCredit: "VOICEVOX: 시코쿠 메탄", ready: "준비 완료", reconnecting: "다시 연결 중",
    welcoming: "손님을 맞이하고 있습니다", otherDisplay: "다른 화면에서 응대 중", preparing: "준비 중",
    microphoneWaiting: "마이크 대기 중", microphoneCheck: "마이크를 확인해 주세요",
    microphonePermission: "브라우저에서 마이크 사용을 허용해 주세요",
    idleKicker: "손님을 기다리고 있습니다", idleTitle: "어서 오세요",
    idleMessage: "카메라 앞에서 잠시 기다려 주세요",
    newKicker: "첫 방문", newTitle: "처음 뵙겠습니다",
    returningKicker: "재방문", returningTitle: "다시 오신 것을 환영합니다",
    readyKicker: "질문을 선택해 주세요", touchTitle: "터치 패널에서 선택해 주세요",
    touchMessage: "질문을 선택하면 도깨비 직원이 답변합니다", askTitle: "무엇이든 물어보세요",
    askMessage: "질문이 있으면 말씀해 주세요", calibrationTitle: "주변 소리를 확인하고 있습니다…",
    listeningKicker: "질문을 듣고 있습니다", listeningTitle: "듣고 있습니다…",
    listeningMessage: "계속 말씀해 주세요", transcribingTitle: "음성을 인식하고 있습니다…",
    wait: "잠시 기다려 주세요", previewKicker: "도깨비 직원의 답변",
    previewTitle: "답변해 드리겠습니다", preparingAudio: "음성을 준비하고 있습니다…",
    assistanceAnswer: "무엇을 도와드릴까요? 터치 패널에서 질문을 선택해 주세요.",
  },
};

function normalizeDisplayLanguage(language) {
  const value = String(language || "ja").toLowerCase().replace("_", "-").split("-", 1)[0];
  return Object.hasOwn(displayText, value) ? value : "ja";
}

function currentDisplayText() {
  return displayText[runtime.displayLanguage] || displayText.ja;
}

function updateFullscreenButton() {
  const text = currentDisplayText();
  elements.fullscreenButton.textContent = document.fullscreenElement
    ? text.exitFullscreen : text.fullscreen;
}

function applyDisplayLanguage(language) {
  runtime.displayLanguage = normalizeDisplayLanguage(language);
  const text = currentDisplayText();
  if (document.documentElement) document.documentElement.lang = runtime.displayLanguage;
  document.title = text.documentTitle;
  elements.shopMark.textContent = text.shopMark;
  elements.shopSubmark.textContent = text.shopSubmark;
  elements.characterStage?.setAttribute?.("aria-label", text.characterLabel);
  elements.usageGuideImage?.setAttribute?.("alt", text.usageGuideAlt);
  elements.checkoutImage?.setAttribute?.("alt", text.checkoutAlt);
  elements.audioButton.textContent = text.audioButton;
  elements.voiceCredit.textContent = text.voiceCredit;
  updateFullscreenButton();
  if (runtime.state === State.IDLE && runtime.config) renderIdleText();
  else if (runtime.state === State.READY) renderReadyText();
}

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
    connectionStatus(true, currentDisplayText().ready);
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
    connectionStatus(false, currentDisplayText().reconnecting);
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
  if (payload.type === "display_language_changed") {
    applyDisplayLanguage(payload.language);
    try { localStorage.setItem("ichigoTouchLanguage", runtime.displayLanguage); }
    catch (error) { console.debug("[LANGUAGE] Could not save language", error); }
  } else if (payload.type === "display_role") {
    if (payload.language) applyDisplayLanguage(payload.language);
    runtime.displayActive = payload.active;
    elements.audioButton.dataset.enabled = String(payload.active);
    const text = currentDisplayText();
    connectionStatus(true, payload.active ? text.welcoming : text.otherDisplay);
    if (payload.active) scheduleAssistanceMonitoring();
    else stopAssistanceMonitoring();
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
    stopAssistanceMonitoring();
    stopQuestionMonitoring();
    runtime.questionSessionId = payload.question_session_id;
    runtime.activeQuestionId = payload.question_id;
    runtime.state = State.THINKING;
    document.body.dataset.state = State.THINKING;
    renderQuestionState(
      State.THINKING,
      payload.question,
      payload.answer_language || "ja",
    );
  } else if (payload.type === "touch_answer_started") {
    if (questionIdsMatch(payload)) void playQuestionAnswer(payload);
  } else if (payload.type === "assistance_prompt_started" && runtime.displayActive) {
    stopAssistanceMonitoring();
    runtime.questionSessionId = payload.question_session_id;
    runtime.activeQuestionId = payload.question_id;
    void playQuestionAnswer(payload);
  } else if (payload.type === "assistance_prompt_rejected") {
    scheduleAssistanceMonitoring();
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
    stopAssistanceMonitoring();
  }
}

async function beginGreeting(payload) {
  if (runtime.state !== State.IDLE) return;
  stopAssistanceMonitoring();
  stopQuestionMonitoring();
  runtime.state = State.GREETING;
  runtime.activeGreetingId = payload.greeting_id;
  runtime.lastCustomerType = payload.customer_type;
  runtime.abort = new AbortController();
  const signal = runtime.abort.signal;
  const isNewCustomer = payload.customer_type === "new";
  document.body.dataset.state = State.GREETING;
  document.body.dataset.customerType = payload.customer_type;
  // These two supplied image assets contain Japanese text baked into the
  // pixels. Hide them in translated modes so the screen never mixes an old
  // Japanese sign with the selected language; the translated subtitles keep
  // the same guidance available.
  const showJapaneseGuideImages = isNewCustomer && runtime.displayLanguage === "ja";
  elements.menuBoard.hidden = !showJapaneseGuideImages;
  elements.checkoutBoard.hidden = !showJapaneseGuideImages;
  showQuestionText("");
  const display = currentDisplayText();
  elements.kicker.textContent = isNewCustomer ? display.newKicker : display.returningKicker;
  elements.title.textContent = isNewCustomer ? display.newTitle : display.returningTitle;
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

const greetingSubtitleTranslations = {
  en: {
    new: [
      "Thank you for visiting.",
      "Our tonjiru and egg set meal is 1,200 yen with unlimited refills.",
      "Coffee and other drinks are 500 yen with unlimited refills.",
      "Meal service is self-service.",
      "Please relax and enjoy your time.",
    ],
    returning: ["Welcome back. Thank you for visiting us again. How have you been?"],
    returning_discount: [
      "Welcome.",
      "Scan your QR code at the payment machine to get the tonjiru and egg set meal for 500 yen.",
    ],
  },
  zh: {
    new: [
      "感谢您的光临。",
      "本店的猪肉味噌汤鸡蛋套餐可免费续加，价格为1,200日元。",
      "咖啡等饮品500日元，可无限续杯。",
      "取餐为自助服务。",
      "请慢慢享用。",
    ],
    returning: ["欢迎再次光临。感谢您再次来到本店。最近过得好吗？"],
    returning_discount: [
      "欢迎光临。",
      "在结算机上扫描二维码，即可以500日元享用猪肉味噌汤鸡蛋套餐。",
    ],
  },
  ko: {
    new: [
      "방문해 주셔서 감사합니다.",
      "리필이 자유로운 돼지고기 된장국 달걀 정식은 1,200엔입니다.",
      "커피 등의 음료는 500엔이며 리필이 자유롭습니다.",
      "배식은 셀프서비스입니다.",
      "편안한 시간 보내세요.",
    ],
    returning: ["어서 오세요. 다시 방문해 주셔서 감사합니다. 잘 지내셨나요?"],
    returning_discount: [
      "어서 오세요.",
      "QR 코드를 결제기에 스캔하면 돼지고기 된장국 달걀 정식을 500엔에 이용할 수 있습니다.",
    ],
  },
};

function localizedGreetingCues(cueKey, cues) {
  const translated = greetingSubtitleTranslations[runtime.displayLanguage]?.[cueKey];
  if (!translated) return cues;
  return cues.map((cue, index) => ({ ...cue, text: translated[index] || cue.text }));
}

function localizedGreetingText(cueKey, fallback) {
  return greetingSubtitleTranslations[runtime.displayLanguage]?.[cueKey]?.join(" ") || fallback;
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
    elements.message.textContent = localizedGreetingText(cueKey, payload.message);
    const played = await playRecordedAudio(
      recordedUrl,
      signal,
      localizedGreetingCues(cueKey, runtime.subtitleCues[cueKey] || []),
    );
    if (played || signal.aborted) return;
  }
  const translatedGreeting = runtime.displayLanguage === "ja"
    ? null
    : localizedGreetingText(cueKey, payload.message);
  await speak(payload.message, signal, "ja", translatedGreeting);
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
function speechLocale(language = "ja") {
  return ({ ja: "ja-JP", en: "en-US", zh: "zh-CN", ko: "ko-KR" })[language] || "ja-JP";
}

function answerDisplayText(language = runtime.displayLanguage) {
  const text = {
    ja: {
      kicker: "鬼からの回答", title: "お答えします", customer: "お客さま",
      assistanceKicker: "鬼からのご案内", assistanceTitle: "何かお困りですか？",
      received: "ご質問を受け付けました", thinking: "回答を考えています…",
      wait: "もう少々お待ちください",
    },
    en: {
      kicker: "Answer from the attendant", title: "Here is the answer", customer: "Guest",
      assistanceKicker: "Message from the attendant", assistanceTitle: "May I help you?",
      received: "Your question has been received", thinking: "Preparing the answer…",
      wait: "Please wait a moment",
    },
    zh: {
      kicker: "鬼店员的回答", title: "为您回答", customer: "顾客",
      assistanceKicker: "鬼店员的提示", assistanceTitle: "您需要帮助吗？",
      received: "已收到您的问题", thinking: "正在准备回答…", wait: "请稍候",
    },
    ko: {
      kicker: "도깨비 직원의 답변", title: "답변해 드리겠습니다", customer: "고객",
      assistanceKicker: "도깨비 직원의 안내", assistanceTitle: "도와드릴까요?",
      received: "질문을 받았습니다", thinking: "답변을 준비하고 있습니다…",
      wait: "잠시 기다려 주세요",
    },
  };
  return text[language] || text.ja;
}

function speakSentence(text, signal, language = "ja") {
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
      const locale = speechLocale(language);
      utterance.lang = locale;
      utterance.rate = 0.95;
      utterance.pitch = 0.92;
      const languageCode = locale.split("-", 1)[0];
      const voice = window.speechSynthesis.getVoices().find(
        candidate => candidate.lang?.toLowerCase().startsWith(languageCode),
      );
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
async function speak(
  text,
  signal = new AbortController().signal,
  language = "ja",
  displayOverride = null,
) {
  window.speechSynthesis?.cancel();
  const sentences = text.match(/[^。！？!?]+[。！？!?]?/gu) || [text];
  for (const sentence of sentences) {
    if (signal.aborted) break;
    elements.message.textContent = displayOverride || sentence;
    const spoken = await speakSentence(sentence, signal, language);
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
  const questionMicrophoneEnabled = Boolean(
    questions?.enabled && questions.vad_enabled &&
    ["microphone", "both"].includes(questions?.input_mode),
  );
  const assistanceEnabled = runtime.config?.assistance_voice?.enabled === true;
  if (!questionMicrophoneEnabled && !assistanceEnabled) {
    runtime.microphoneGranted = false;
    send({ type: "question_capability", available: false });
    send({ type: "assistance_capability", available: false });
    return;
  }
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia ||
      (questionMicrophoneEnabled && typeof MediaRecorder === "undefined")) {
    runtime.microphoneGranted = false;
    send({ type: "question_capability", available: false });
    send({ type: "assistance_capability", available: false });
    document.body.dataset.assistanceMicrophone = "unavailable";
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
    document.body.dataset.assistanceMicrophone = "ready";
    send({
      type: "question_capability",
      available: questionMicrophoneEnabled,
      microphone_label: runtime.microphoneDeviceLabel || null,
    });
    send({
      type: "assistance_capability",
      available: assistanceEnabled,
      microphone_label: runtime.microphoneDeviceLabel || null,
    });
    if (assistanceEnabled && runtime.displayActive) {
      connectionStatus(true, currentDisplayText().microphoneWaiting);
    }
  } catch (error) {
    console.warn("[MICROPHONE] Permission unavailable", error);
    runtime.microphoneGranted = false;
    document.body.dataset.assistanceMicrophone = "unavailable";
    send({ type: "question_capability", available: false });
    send({ type: "assistance_capability", available: false });
    if (runtime.enabled && runtime.state === State.IDLE) {
      connectionStatus(true, currentDisplayText().microphoneCheck);
      elements.message.textContent = currentDisplayText().microphonePermission;
    }
  }
}

function microphoneConstraints(deviceId = "") {
  const constraints = {
    echoCancellation: true,
    noiseSuppression: true,
    // Automatic gain raises quiet room noise until it looks like speech.
    // Keep the real microphone level so the calibrated VAD remains stable.
    autoGainControl: runtime.config?.assistance_voice?.enabled === true,
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
  if (!navigator.mediaDevices?.enumerateDevices) {
    return microphoneConstraints();
  }
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const audioInputs = devices.filter(device => device.kind === "audioinput");
    const match = preferred
      ? audioInputs.find(device => device.label.toLowerCase().includes(preferred))
      : audioInputs.find(device => /usb/i.test(device.label));
    if (match?.deviceId) {
      console.info(`[MICROPHONE] Selected input: ${match.label || "USB microphone"}`);
      return microphoneConstraints(match.deviceId);
    }
    if (preferred) console.warn(`[MICROPHONE] Preferred input was not found: ${preferred}`);
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

function createAssistanceVoiceTracker(config, now = 0) {
  const configuredCalibration = Number(config?.calibration_ms);
  const vadConfig = {
    vad_start_threshold: Number(config?.start_threshold) || 0.010,
    vad_start_duration_ms: Number(config?.start_duration_ms) || 200,
    vad_calibration_ms: Number.isFinite(configuredCalibration) && configuredCalibration >= 0
      ? configuredCalibration : 500,
    vad_noise_multiplier: Number(config?.noise_multiplier) || 1.4,
    vad_noise_margin: Number(config?.noise_margin) || 0.0025,
  };
  const tracker = createVadTracker(vadConfig, now);
  tracker.speechBandRatio = Number(config?.speech_band_ratio) || 0.20;
  tracker.zcrMin = Number(config?.zcr_min) || 0.001;
  tracker.zcrMax = Number(config?.zcr_max) || 0.45;
  tracker.triggered = false;
  return tracker;
}

function updateAssistanceVoiceTracker(tracker, level, speechBandRatio, zcr, now) {
  if (tracker.triggered) return null;
  tracker.currentLevel = level;
  if (!tracker.calibrated) {
    tracker.calibrationSamples.push(level);
    if (now - tracker.startedAt < tracker.calibrationMs) return null;
    finishVadCalibration(tracker);
    tracker.candidateSince = null;
    return null;
  }
  if (tracker.candidateSince === null && level < tracker.noiseFloor) {
    tracker.noiseFloor = tracker.noiseFloor * 0.95 + level * 0.05;
    tracker.effectiveThreshold = calculateVadThreshold(tracker.config, tracker.noiseFloor);
  }
  const voiceLike = level >= tracker.effectiveThreshold &&
    speechBandRatio >= tracker.speechBandRatio &&
    zcr >= tracker.zcrMin && zcr <= tracker.zcrMax;
  if (!voiceLike) {
    tracker.candidateSince = null;
    return null;
  }
  if (tracker.candidateSince === null) tracker.candidateSince = now;
  if (now - tracker.candidateSince < tracker.config.vad_start_duration_ms) return null;
  tracker.triggered = true;
  return { type: "voice", level, speechBandRatio, zcr };
}

function calculateAssistanceAudioFeatures(analyser, sampleRate) {
  const timeSamples = new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(timeSamples);
  let squareSum = 0;
  let zeroCrossings = 0;
  for (let index = 0; index < timeSamples.length; index += 1) {
    const sample = timeSamples[index];
    squareSum += sample * sample;
    if (index > 0 && ((sample >= 0) !== (timeSamples[index - 1] >= 0))) {
      zeroCrossings += 1;
    }
  }
  const level = Math.sqrt(squareSum / Math.max(1, timeSamples.length));
  const zcr = zeroCrossings / Math.max(1, timeSamples.length - 1);

  const frequencySamples = new Float32Array(analyser.frequencyBinCount);
  analyser.getFloatFrequencyData(frequencySamples);
  const nyquist = sampleRate / 2;
  let totalPower = 0;
  let speechPower = 0;
  for (let index = 1; index < frequencySamples.length; index += 1) {
    const decibels = frequencySamples[index];
    if (!Number.isFinite(decibels)) continue;
    const frequency = index * nyquist / frequencySamples.length;
    const power = 10 ** (decibels / 10);
    totalPower += power;
    if (frequency >= 100 && frequency <= 4000) speechPower += power;
  }
  return {
    level,
    zcr,
    speechBandRatio: totalPower > 0 ? speechPower / totalPower : 0,
  };
}

function assistanceMonitoringAllowed() {
  // READY is the fixed touch-panel input window. Keeping ambient detection
  // active there could replay the assistance prompt and extend that window.
  return runtime.state === State.IDLE;
}

function stopAssistanceMonitoring() {
  runtime.assistanceGeneration += 1;
  if (runtime.assistanceTimer !== null) {
    clearTimeout(runtime.assistanceTimer);
    runtime.assistanceTimer = null;
  }
  const microphone = runtime.assistanceMicrophone;
  if (!microphone) return;
  microphone.stopped = true;
  if (microphone.raf !== null && typeof cancelAnimationFrame === "function") {
    cancelAnimationFrame(microphone.raf);
  }
  try { microphone.source?.disconnect(); } catch (error) { console.debug(error); }
  microphone.stream?.getTracks().forEach(track => track.stop());
  runtime.assistanceMicrophone = null;
  delete document.body.dataset.assistanceLevel;
  delete document.body.dataset.assistanceThreshold;
}

function scheduleAssistanceMonitoring(delayMs = 0) {
  stopAssistanceMonitoring();
  const config = runtime.config?.assistance_voice;
  if (!config?.enabled || !runtime.enabled || !runtime.displayActive ||
      !assistanceMonitoringAllowed() || runtime.assistanceSuppressed ||
      runtime.microphoneGranted !== true) return;
  const cooldownDelay = Math.max(0, runtime.assistanceCooldownUntil - Date.now());
  runtime.assistanceTimer = setTimeout(() => {
    runtime.assistanceTimer = null;
    void startAssistanceMonitoring();
  }, Math.max(delayMs, cooldownDelay));
}

async function startAssistanceMonitoring() {
  stopAssistanceMonitoring();
  const generation = runtime.assistanceGeneration;
  const config = runtime.config?.assistance_voice;
  if (!config?.enabled || !runtime.enabled || !runtime.displayActive ||
      !assistanceMonitoringAllowed() || runtime.assistanceSuppressed ||
      runtime.microphoneGranted !== true || Date.now() < runtime.assistanceCooldownUntil) {
    return;
  }
  try {
    const stream = await openMicrophoneStream();
    rememberMicrophoneDevice(stream);
    if (generation !== runtime.assistanceGeneration ||
        !assistanceMonitoringAllowed() || runtime.assistanceSuppressed) {
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
    analyser.smoothingTimeConstant = 0.65;
    source.connect(analyser);
    const microphone = {
      stream, source, analyser, audioContext, config,
      tracker: createAssistanceVoiceTracker(config, Date.now()),
      raf: null, stopped: false, lastMetricsAt: 0,
    };
    runtime.assistanceMicrophone = microphone;
    const frame = () => {
      if (runtime.assistanceMicrophone !== microphone || microphone.stopped ||
          !assistanceMonitoringAllowed() || runtime.assistanceSuppressed) return;
      const features = calculateAssistanceAudioFeatures(
        analyser,
        audioContext.sampleRate || 48000,
      );
      const event = updateAssistanceVoiceTracker(
        microphone.tracker,
        features.level,
        features.speechBandRatio,
        features.zcr,
        Date.now(),
      );
      document.body.dataset.assistanceLevel = features.level.toFixed(4);
      document.body.dataset.assistanceThreshold =
        microphone.tracker.effectiveThreshold.toFixed(4);
      const now = Date.now();
      if (now - microphone.lastMetricsAt >= 2000) {
        microphone.lastMetricsAt = now;
        send({
          type: "assistance_metrics",
          level: features.level,
          threshold: microphone.tracker.effectiveThreshold,
          speech_band_ratio: features.speechBandRatio,
          zero_crossing_rate: features.zcr,
          calibrated: microphone.tracker.calibrated,
        });
      }
      if (event) {
        runtime.assistanceCooldownUntil = Date.now() +
          Number(config.cooldown_seconds || 30) * 1000;
        stopAssistanceMonitoring();
        send({
          type: "assistance_requested",
          vad_level: event.level,
          speech_band_ratio: event.speechBandRatio,
          zero_crossing_rate: event.zcr,
        });
        return;
      }
      microphone.raf = requestAnimationFrame(frame);
    };
    microphone.raf = requestAnimationFrame(frame);
  } catch (error) {
    console.warn("[ASSISTANCE] Could not monitor ambient voice", error);
    stopAssistanceMonitoring();
  }
}

function renderReadyText() {
  const text = currentDisplayText();
  const inputMode = runtime.config?.questions?.input_mode || "microphone";
  const touchEnabled = ["touch", "both"].includes(inputMode);
  elements.kicker.textContent = text.readyKicker;
  if (touchEnabled) {
    elements.title.textContent = text.touchTitle;
    elements.message.textContent = text.touchMessage;
  } else {
    elements.title.textContent = text.askTitle;
    elements.message.textContent = text.askMessage;
  }
}

async function enterReady(payload) {
  stopAssistanceMonitoring();
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
  renderReadyText();
  showQuestionText("");
  if (microphoneEnabled && runtime.microphoneGranted === true) {
    await startQuestionMonitoring();
  } else {
    stopQuestionMonitoring();
    scheduleAssistanceMonitoring();
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
      elements.title.textContent = currentDisplayText().calibrationTitle;
      elements.message.textContent = currentDisplayText().wait;
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
    elements.title.textContent = currentDisplayText().askTitle;
    elements.message.textContent = currentDisplayText().askMessage;
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
  const text = currentDisplayText();
  elements.kicker.textContent = text.listeningKicker;
  elements.title.textContent = text.listeningTitle;
  elements.message.textContent = text.listeningMessage;
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
  stopAssistanceMonitoring();
  stopQuestionMonitoring();
  runtime.state = State.SPEAKING;
  document.body.dataset.state = State.SPEAKING;
  runtime.answerAbort?.abort();
  runtime.answerAbort = new AbortController();
  const signal = runtime.answerAbort.signal;
  const answerLanguage = normalizeDisplayLanguage(
    payload.answer_language || runtime.displayLanguage,
  );
  const displayAnswer = payload.answer_source === "assistance_prompt"
    ? displayText[answerLanguage].assistanceAnswer
    : payload.answer;
  const spokenAnswer = payload.spoken_answer || payload.answer;
  renderAnswer(
    payload.question,
    displayAnswer,
    payload.answer_source,
    answerLanguage,
  );
  const displayImageUrl = answerLanguage === "ja"
    && typeof payload.display_image_url === "string"
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
        if (!signal.aborted) {
          await playAnswerVoice(
            audioUrl,
            spokenAnswer,
            displayAnswer,
            signal,
          );
        }
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

async function playAnswerVoice(audioUrl, spokenAnswer, displayAnswer, signal) {
  if (audioUrl) {
    elements.message.textContent = displayAnswer;
    const played = await playRecordedAudio(audioUrl, signal);
    if (played || signal.aborted) return;
  }
  await speak(spokenAnswer, signal, "ja", displayAnswer);
}

function renderQuestionState(state, question = "", language = runtime.displayLanguage) {
  runtime.state = state;
  document.body.dataset.state = state;
  if (state !== State.LISTENING) stopQuestionMonitoring();
  const displayText = answerDisplayText(language);
  elements.kicker.textContent = displayText.received;
  const ui = currentDisplayText();
  if (state === State.LISTENING) {
    elements.title.textContent = ui.listeningTitle;
    elements.message.textContent = ui.listeningMessage;
  } else if (state === State.TRANSCRIBING) {
    elements.title.textContent = ui.transcribingTitle;
    elements.message.textContent = ui.wait;
  } else {
    elements.title.textContent = displayText.thinking;
    elements.message.textContent = displayText.wait;
  }
  if (question) showQuestionText(`${displayText.customer}「${question}」`);
}

function renderAnswer(question, answer, source = "", language = "ja") {
  runtime.state = State.SPEAKING;
  document.body.dataset.state = State.SPEAKING;
  const isAssistancePrompt = source === "assistance_prompt";
  const displayText = answerDisplayText(language);
  elements.kicker.textContent = isAssistancePrompt
    ? displayText.assistanceKicker : displayText.kicker;
  elements.title.textContent = isAssistancePrompt
    ? displayText.assistanceTitle : displayText.title;
  elements.message.textContent = answer || currentDisplayText().wait;
  showQuestionText(question ? `${displayText.customer}「${question}」` : "");
}

function renderAnswerPreview(question, answer) {
  runtime.state = State.THINKING;
  document.body.dataset.state = State.THINKING;
  const text = currentDisplayText();
  const answerText = answerDisplayText(runtime.displayLanguage);
  elements.kicker.textContent = text.previewKicker;
  elements.title.textContent = text.previewTitle;
  elements.message.textContent = answer || text.preparingAudio;
  showQuestionText(question ? `${answerText.customer}「${question}」` : "");
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

function renderIdleText() {
  const text = currentDisplayText();
  elements.kicker.textContent = text.idleKicker;
  elements.title.textContent = text.idleTitle;
  elements.message.textContent = text.idleMessage;
}

function returnToIdle() {
  stopAssistanceMonitoring();
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
  renderIdleText();
  elements.video.loop = true;
  setVideoSource(runtime.config.videos.idle);
  try { elements.video.play()?.catch(() => markVideoError(true)); }
  catch (error) { markVideoError(true); }
  scheduleAssistanceMonitoring();
}

async function enableAudio() {
  elements.audioButton.disabled = true;
  runtime.enabled = true;
  // The start button is a user gesture, so it can also enter browser fullscreen.
  // This hides the Chrome controls and the Windows taskbar on the shop display.
  void enterFullscreen();
  // Web Audio is also used for lightweight ambient voice detection.
  if (["microphone", "both"].includes(runtime.config?.questions?.input_mode) ||
      runtime.config?.assistance_voice?.enabled) {
    void prepareAudioContext();
  }
  send({ type: "display_ready" });
  runtime.assistanceSuppressed = true;
  const permission = requestMicrophoneCapability();
  void speakSentence("いらっしゃいませ。", new AbortController().signal)
    .finally(async () => {
      await permission;
      runtime.assistanceSuppressed = false;
      elements.audioButton.disabled = false;
      scheduleAssistanceMonitoring();
    });
}
elements.audioButton.addEventListener("click", () => void enableAudio());
elements.video.addEventListener("canplay", () => markVideoError(false));
elements.video.addEventListener("error", () => markVideoError(true));
elements.fullscreenButton.addEventListener("click", () => void toggleFullscreen());
document.addEventListener?.("fullscreenchange", updateFullscreenButton);

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
    const savedLanguage = localStorage.getItem("ichigoTouchLanguage");
    applyDisplayLanguage(savedLanguage || "ja");
  } catch (error) {
    applyDisplayLanguage("ja");
  }
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
    connectionStatus(false, currentDisplayText().preparing);
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
