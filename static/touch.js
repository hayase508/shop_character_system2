"use strict";

const touchElements = {
  connection: document.getElementById("connectionBadge"),
  title: document.getElementById("statusTitle"),
  message: document.getElementById("statusMessage"),
  grid: document.getElementById("questionGrid"),
  fullscreen: document.getElementById("touchFullscreenButton"),
};

const touchRuntime = {
  enabled: false,
  state: "IDLE",
  socket: null,
  reconnectTimer: null,
  questions: [],
};

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
  touchElements.fullscreen.textContent = document.fullscreenElement
    ? "全画面解除"
    : "全画面表示";
}

function renderState(state) {
  touchRuntime.state = state;
  const ready = canSubmitTouchQuestion();
  setButtonsEnabled(ready);
  if (ready) {
    touchElements.title.textContent = "質問を選んでください";
    touchElements.message.textContent = "";
  } else if (state === "GREETING") {
    touchElements.title.textContent = "ご案内中です";
    touchElements.message.textContent = "少々お待ちください";
  } else if (["THINKING", "SPEAKING"].includes(state)) {
    touchElements.title.textContent = "回答中です";
    touchElements.message.textContent = "";
  } else {
    touchElements.title.textContent = "質問を選んでください";
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
  setButtonsEnabled(false);
  touchElements.title.textContent = "送信中です";
  touchElements.message.textContent = question.label;
  try {
    const response = await fetch(
      `/api/touch/questions/${encodeURIComponent(question.id)}`,
      { method: "POST" },
    );
    if (!response.ok) {
      if (response.status === 409) {
        touchElements.title.textContent = "鬼店員は接客中です";
        touchElements.message.textContent = "少し待ってから、もう一度選んでください";
        if (canSubmitTouchQuestion()) setButtonsEnabled(true);
        return;
      }
      throw new Error(`Touch question failed: ${response.status}`);
    }
    touchElements.title.textContent = "回答します";
    touchElements.message.textContent = question.label;
  } catch (error) {
    console.warn("[TOUCH]", error);
    touchElements.title.textContent = "質問を送れませんでした";
    touchElements.message.textContent = "接続を確認して、もう一度お試しください";
    if (canSubmitTouchQuestion()) setButtonsEnabled(true);
  }
}

function connectTouchSocket() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${location.host}/ws`);
  touchRuntime.socket = socket;
  socket.addEventListener("open", () => {
    touchElements.connection.dataset.connected = "true";
    touchElements.connection.textContent = "接続済み";
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
    touchElements.connection.textContent = "再接続中";
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

async function initializeTouchPanel() {
  try {
    const response = await fetch("/api/touch/questions", { cache: "no-store" });
    if (!response.ok) throw new Error("Touch configuration failed");
    const config = await response.json();
    touchRuntime.enabled = config.enabled === true;
    touchRuntime.questions = Array.isArray(config.questions) ? config.questions : [];
    renderQuestions(touchRuntime.questions);
    if (!touchRuntime.enabled) {
      touchElements.title.textContent = "タッチパネルは無効です";
      touchElements.message.textContent = "設定を確認してください";
    }
    connectTouchSocket();
  } catch (error) {
    console.error("[TOUCH]", error);
    touchElements.title.textContent = "画面を準備できませんでした";
    touchElements.message.textContent = "サーバー接続を確認してください";
  }
}

touchElements.fullscreen.addEventListener("click", () => void toggleTouchFullscreen());
document.addEventListener("fullscreenchange", updateTouchFullscreenButton);
void initializeTouchPanel();
