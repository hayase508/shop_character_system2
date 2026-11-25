"use strict";

const touchElements = {
  connection: document.getElementById("connectionBadge"),
  title: document.getElementById("statusTitle"),
  message: document.getElementById("statusMessage"),
  grid: document.getElementById("questionGrid"),
  fullscreen: document.getElementById("touchFullscreenButton"),
  language: document.getElementById("languageButton"),
  selectedLanguage: document.getElementById("selectedLanguageLabel"),
  languageDialog: document.getElementById("languageDialog"),
  languageClose: document.getElementById("languageCloseButton"),
  languageDialogTitle: document.getElementById("languageDialogTitle"),
  languageOptions: [...document.querySelectorAll(".language-option")],
  brand: document.getElementById("touchBrand"),
  heading: document.getElementById("touchHeading"),
  footer: document.getElementById("touchFooter"),
};

const touchLanguages = ["ja", "en", "zh", "ko"];
const touchLanguageNames = {
  ja: "日本語",
  en: "English",
  zh: "中文",
  ko: "한국어",
};
const touchText = {
  ja: {
    documentTitle: "いちごうカフェ 質問タッチパネル", brand: "いちごうカフェ",
    languageDialogTitle: "言語を選択してください", close: "閉じる",
    questionListLabel: "質問一覧",
    heading: "聞きたい質問を選んでください",
    fullscreen: "全画面表示", exitFullscreen: "全画面解除", connecting: "接続中",
    connected: "接続済み", reconnecting: "再接続中", select: "質問を選んでください",
    guiding: "ご案内中です", wait: "少々お待ちください", answering: "回答中です",
    sending: "送信中です", willAnswer: "回答します", busy: "鬼店員は接客中です",
    retry: "少し待ってから、もう一度選んでください", sendFailed: "質問を送れませんでした",
    checkConnection: "接続を確認して、もう一度お試しください",
    disabled: "タッチパネルは無効です", checkSettings: "設定を確認してください",
    setupFailed: "画面を準備できませんでした", checkServer: "サーバー接続を確認してください",
    footer: "顔認証をしていないときも、いつでも質問できます",
  },
  en: {
    documentTitle: "Ichigo Cafe Question Panel", brand: "Ichigo Cafe",
    languageDialogTitle: "Select a language", close: "Close",
    questionListLabel: "Question list",
    heading: "Please select a question",
    fullscreen: "Full screen", exitFullscreen: "Exit full screen", connecting: "Connecting",
    connected: "Connected", reconnecting: "Reconnecting", select: "Please select a question",
    guiding: "The attendant is speaking", wait: "Please wait", answering: "Answering",
    sending: "Sending", willAnswer: "Here is the answer", busy: "The attendant is busy",
    retry: "Please wait and try again", sendFailed: "Could not send the question",
    checkConnection: "Check the connection and try again",
    disabled: "Touch panel is disabled", checkSettings: "Please check the settings",
    setupFailed: "Could not prepare this screen", checkServer: "Please check the server connection",
    footer: "You can ask a question at any time, even without face recognition",
  },
  zh: {
    documentTitle: "一合咖啡馆 问题触摸屏", brand: "一合咖啡馆",
    languageDialogTitle: "请选择语言", close: "关闭",
    questionListLabel: "问题列表",
    heading: "请选择您想问的问题",
    fullscreen: "全屏显示", exitFullscreen: "退出全屏", connecting: "连接中",
    connected: "已连接", reconnecting: "正在重新连接", select: "请选择问题",
    guiding: "正在为您介绍", wait: "请稍候", answering: "正在回答",
    sending: "正在发送", willAnswer: "为您回答", busy: "鬼店员正在接待中",
    retry: "请稍候再试", sendFailed: "问题发送失败",
    checkConnection: "请检查连接后重试", disabled: "触摸屏已停用",
    checkSettings: "请检查设置", setupFailed: "无法准备画面",
    checkServer: "请检查服务器连接", footer: "即使未进行人脸识别，也可以随时提问",
  },
  ko: {
    documentTitle: "이치고 카페 질문 터치 패널", brand: "이치고 카페",
    languageDialogTitle: "언어를 선택해 주세요", close: "닫기",
    questionListLabel: "질문 목록",
    heading: "궁금한 질문을 선택해 주세요",
    fullscreen: "전체 화면", exitFullscreen: "전체 화면 종료", connecting: "연결 중",
    connected: "연결됨", reconnecting: "다시 연결 중", select: "질문을 선택해 주세요",
    guiding: "안내 중입니다", wait: "잠시 기다려 주세요", answering: "답변 중입니다",
    sending: "전송 중입니다", willAnswer: "답변해 드리겠습니다", busy: "도깨비 직원이 응대 중입니다",
    retry: "잠시 후 다시 선택해 주세요", sendFailed: "질문을 전송하지 못했습니다",
    checkConnection: "연결을 확인하고 다시 시도해 주세요", disabled: "터치 패널이 비활성화되어 있습니다",
    checkSettings: "설정을 확인해 주세요", setupFailed: "화면을 준비하지 못했습니다",
    checkServer: "서버 연결을 확인해 주세요", footer: "얼굴 인식을 하지 않아도 언제든지 질문할 수 있습니다",
  },
};

const touchRuntime = {
  enabled: false,
  state: "IDLE",
  socket: null,
  reconnectTimer: null,
  questions: [],
  language: "ja",
};

function currentTouchText() {
  return touchText[touchRuntime.language] || touchText.ja;
}

function applyTouchLanguage() {
  const text = currentTouchText();
  document.documentElement.lang = touchRuntime.language;
  document.title = text.documentTitle;
  touchElements.brand.textContent = text.brand;
  touchElements.languageDialogTitle.textContent = text.languageDialogTitle;
  touchElements.languageClose.setAttribute("aria-label", text.close);
  touchElements.grid.setAttribute("aria-label", text.questionListLabel);
  touchElements.selectedLanguage.textContent = touchLanguageNames[touchRuntime.language];
  touchElements.language.setAttribute(
    "aria-label",
    `Language: ${touchLanguageNames[touchRuntime.language]}`,
  );
  touchElements.languageOptions.forEach(option => {
    const selected = option.dataset.language === touchRuntime.language;
    option.classList.toggle("is-selected", selected);
    option.setAttribute("aria-pressed", String(selected));
  });
  touchElements.heading.textContent = text.heading;
  touchElements.footer.textContent = text.footer;
  updateTouchFullscreenButton();
  renderState(touchRuntime.state);
}

function broadcastDisplayLanguage() {
  if (touchRuntime.socket?.readyState === WebSocket.OPEN) {
    touchRuntime.socket.send(JSON.stringify({
      type: "display_language_changed",
      language: touchRuntime.language,
    }));
  }
}

function openLanguageDialog() {
  if (touchElements.language.disabled) return;
  touchElements.languageDialog.hidden = false;
  touchElements.language.setAttribute("aria-expanded", "true");
  const selected = touchElements.languageOptions.find(
    option => option.dataset.language === touchRuntime.language,
  );
  selected?.focus();
}

function closeLanguageDialog() {
  if (touchElements.languageDialog.hidden) return;
  touchElements.languageDialog.hidden = true;
  touchElements.language.setAttribute("aria-expanded", "false");
  touchElements.language.focus();
}

function setButtonsEnabled(enabled) {
  touchElements.grid.querySelectorAll("button").forEach(button => {
    button.disabled = !enabled;
  });
}

function canSubmitTouchQuestion() {
  return touchRuntime.enabled && ["IDLE", "READY"].includes(touchRuntime.state);
}

async function toggleTouchFullscreen() {
  try {
    if (document.fullscreenElement) {
      if (typeof document.exitFullscreen === "function") await document.exitFullscreen();
    } else if (typeof document.documentElement?.requestFullscreen === "function") {
      await document.documentElement.requestFullscreen();
    }
  } catch (error) {
    console.warn("[TOUCH FULLSCREEN]", error);
  }
}

function updateTouchFullscreenButton() {
  const text = currentTouchText();
  touchElements.fullscreen.textContent = document.fullscreenElement
    ? text.exitFullscreen
    : text.fullscreen;
}

function renderState(state) {
  touchRuntime.state = state;
  const text = currentTouchText();
  const ready = canSubmitTouchQuestion();
  setButtonsEnabled(ready);
  touchElements.language.disabled = !["IDLE", "READY"].includes(state);
  if (touchElements.language.disabled) closeLanguageDialog();
  if (ready) {
    touchElements.title.textContent = text.select;
    touchElements.message.textContent = "";
  } else if (state === "GREETING") {
    touchElements.title.textContent = text.guiding;
    touchElements.message.textContent = text.wait;
  } else if (["THINKING", "SPEAKING"].includes(state)) {
    touchElements.title.textContent = text.answering;
    touchElements.message.textContent = "";
  } else {
    touchElements.title.textContent = text.select;
    touchElements.message.textContent = "";
  }
}

function renderQuestions(questions) {
  touchElements.grid.replaceChildren();
  for (const question of questions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "question-button";
    button.textContent = question.label;
    button.dataset.questionId = question.id;
    button.disabled = !canSubmitTouchQuestion();
    button.addEventListener("click", () => void submitQuestion(question));
    touchElements.grid.append(button);
  }
}

async function submitQuestion(question) {
  if (!canSubmitTouchQuestion()) return;
  const text = currentTouchText();
  setButtonsEnabled(false);
  touchElements.title.textContent = text.sending;
  touchElements.message.textContent = question.label;
  try {
    const response = await fetch(
      `/api/touch/questions/${encodeURIComponent(question.id)}?language=${encodeURIComponent(touchRuntime.language)}`,
      { method: "POST" },
    );
    if (!response.ok) {
      if (response.status === 409) {
        touchElements.title.textContent = text.busy;
        touchElements.message.textContent = text.retry;
        if (canSubmitTouchQuestion()) setButtonsEnabled(true);
        return;
      }
      throw new Error(`Touch question failed: ${response.status}`);
    }
    touchElements.title.textContent = text.willAnswer;
    touchElements.message.textContent = question.label;
  } catch (error) {
    console.warn("[TOUCH]", error);
    touchElements.title.textContent = text.sendFailed;
    touchElements.message.textContent = text.checkConnection;
    if (canSubmitTouchQuestion()) setButtonsEnabled(true);
  }
}

function connectTouchSocket() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${location.host}/ws`);
  touchRuntime.socket = socket;
  socket.addEventListener("open", () => {
    touchElements.connection.dataset.connected = "true";
    touchElements.connection.textContent = currentTouchText().connected;
    broadcastDisplayLanguage();
  });
  socket.addEventListener("message", event => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "state_changed" && payload.state) {
        renderState(payload.state);
      } else if (payload.type === "customer_detected") {
        renderState("GREETING");
      } else if (payload.type === "touch_question_started") {
        renderState("THINKING");
      } else if (payload.type === "touch_answer_started") {
        renderState("SPEAKING");
      }
    } catch (error) {
      console.warn("[TOUCH] Invalid message", error);
    }
  });
  socket.addEventListener("close", () => {
    touchElements.connection.dataset.connected = "false";
    touchElements.connection.textContent = currentTouchText().reconnecting;
    setButtonsEnabled(false);
    if (!touchRuntime.reconnectTimer) {
      touchRuntime.reconnectTimer = setTimeout(() => {
        touchRuntime.reconnectTimer = null;
        connectTouchSocket();
      }, 1500);
    }
  });
  socket.addEventListener("error", () => socket.close());
}

async function loadTouchQuestions() {
  const text = currentTouchText();
  try {
    const response = await fetch(
      `/api/touch/questions?language=${encodeURIComponent(touchRuntime.language)}`,
      { cache: "no-store" },
    );
    if (!response.ok) throw new Error("Touch configuration failed");
    const config = await response.json();
    touchRuntime.enabled = config.enabled === true;
    touchRuntime.questions = Array.isArray(config.questions) ? config.questions : [];
    renderQuestions(touchRuntime.questions);
    if (!touchRuntime.enabled) {
      touchElements.title.textContent = text.disabled;
      touchElements.message.textContent = text.checkSettings;
    }
  } catch (error) {
    console.error("[TOUCH]", error);
    touchRuntime.enabled = false;
    setButtonsEnabled(false);
    touchElements.title.textContent = text.setupFailed;
    touchElements.message.textContent = text.checkServer;
  }
}

async function changeTouchLanguage(language) {
  if (touchElements.language.disabled || !touchLanguages.includes(language)) return;
  touchRuntime.language = language;
  try {
    localStorage.setItem("ichigoTouchLanguage", touchRuntime.language);
  } catch (error) {
    console.warn("[TOUCH] Could not save language", error);
  }
  closeLanguageDialog();
  applyTouchLanguage();
  broadcastDisplayLanguage();
  touchElements.connection.textContent = touchElements.connection.dataset.connected === "true"
    ? currentTouchText().connected
    : currentTouchText().connecting;
  await loadTouchQuestions();
}

async function initializeTouchPanel() {
  try {
    const savedLanguage = localStorage.getItem("ichigoTouchLanguage");
    if (touchLanguages.includes(savedLanguage)) touchRuntime.language = savedLanguage;
  } catch (error) {
    console.warn("[TOUCH] Could not load language", error);
  }
  applyTouchLanguage();
  await loadTouchQuestions();
  connectTouchSocket();
}

touchElements.fullscreen.addEventListener("click", () => void toggleTouchFullscreen());
touchElements.language.addEventListener("click", openLanguageDialog);
touchElements.languageClose.addEventListener("click", closeLanguageDialog);
touchElements.languageDialog.addEventListener("click", event => {
  if (event.target === touchElements.languageDialog) closeLanguageDialog();
});
touchElements.languageOptions.forEach(option => {
  option.addEventListener("click", () => void changeTouchLanguage(option.dataset.language));
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape") closeLanguageDialog();
});
document.addEventListener("fullscreenchange", updateTouchFullscreenButton);
void initializeTouchPanel();
