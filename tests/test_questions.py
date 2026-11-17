import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.reception import ReceptionController
from app.question_service import (
    GEMINI_SYSTEM_INSTRUCTION,
    LOCAL_VOICE_LINES,
    GeminiService,
    QuestionAnswerService,
    QuestionContext,
    get_touch_question,
    is_likely_spoken_question,
    touch_question_catalog,
)
from app.speech_service import SpeechRecognizer, correct_domain_transcription
from app.voicevox_service import VoicevoxError, VoicevoxService


class FakeGemini:
    def __init__(self, *, available=True, answer="鬼の回答です。", cached=None, error=None):
        self.available = available
        self.answer_text = answer
        self.cached = cached
        self.error = error
        self.calls = 0

    def cached_answer(self, question):
        return self.cached

    async def answer_uncached(self, question):
        self.calls += 1
        if self.error:
            raise self.error
        return self.answer_text


def test_touch_question_catalog_uses_prerecorded_local_answers():
    catalog = touch_question_catalog()
    assert len(catalog) == 3
    assert len({item["id"] for item in catalog}) == len(catalog)
    assert {item["category"] for item in catalog} == {
        "payment", "benefit", "about"
    }
    assert all(item["category_label"] for item in catalog)
    assert [item["category_label"] for item in catalog] == [
        "支払方法", "再来店特典", "いちごうカフェとは"
    ]
    for item in catalog:
        question = get_touch_question(item["id"])
        assert question is not None
        assert question.answer == LOCAL_VOICE_LINES[question.audio_key]
    assert get_touch_question("unknown") is None
    assert get_touch_question("payment-method").display_image_url == (
        "/static/images/checkout-machine.png"
    )
    assert get_touch_question("repeat-benefit").display_image_url == (
        "/static/images/revisit-benefit.png"
    )
    assert get_touch_question("repeat-benefit").display_image_layout == "portrait"


class FakeAsyncModels:
    def __init__(self):
        self.calls = []

    async def get(self, *, model):
        self.calls.append(model)
        return SimpleNamespace(name=model)


def resolve(service, question, context=None, used=0, force_gemini=False):
    return asyncio.run(
        service.answer(
            question,
            context or QuestionContext(False, None),
            used,
            force_gemini=force_gemini,
        )
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("春が好きです。（全12文字）", "春が好きです。"),
        ("春が好きです。 文字数：12文字", "春が好きです。"),
        ("春が好きです。 約12文字", "春が好きです。"),
    ],
)
def test_gemini_answer_removes_character_count_annotations(raw, expected):
    assert GeminiService._sanitize_answer(raw) == expected


def test_customer_facing_answers_use_polite_style():
    forbidden = ("じゃ", "だぞ", "してくれ", "頼むぞ", "すまぬ")
    assert all(not any(word in text for word in forbidden) for text in LOCAL_VOICE_LINES.values())
    assert "です・ます調" in GEMINI_SYSTEM_INSTRUCTION
    assert all(word not in GEMINI_SYSTEM_INSTRUCTION for word in ("一人称は「わし」", "店員に確認してくれ"))


def test_gemini_connection_warmup_only_gets_model_metadata():
    service = GeminiService(Settings(gemini_api_key="test-key"))
    models = FakeAsyncModels()
    service._client = SimpleNamespace(aio=SimpleNamespace(models=models))
    service._types = SimpleNamespace()

    asyncio.run(service.warm_connection())
    asyncio.run(service.warm_connection())

    assert models.calls == [service.settings.gemini_model]
    assert service.cached_answer("質問") is None


@pytest.mark.parametrize(
    "question,expected",
    [
        ("定食はいくら？", "1,200円"),
        ("豚汁はおかわりできる？", "豚汁はお代わり自由"),
        ("トンジルはお変わりできますか？", "豚汁はお代わり自由"),
        ("卵は何個まで？", "たまごもお代わり自由"),
        ("ご飯おかわりできる？", "ご飯もお代わり自由"),
        ("コーヒーはいくら？", "500円"),
        ("飲み物はおかわりできる？", "飲み物もお代わり自由"),
        ("再来店特典を教えて", "60日以内"),
        ("配膳はどうするの？", "セルフサービス"),
    ],
)
def test_faq_answers_without_gemini(question, expected):
    gemini = FakeGemini()
    service = QuestionAnswerService(Settings(), gemini)
    answer = resolve(service, question)
    assert expected in answer.text
    assert answer.source == "faq"
    assert answer.audio_key
    assert gemini.calls == 0


def test_session_discount_question_is_local():
    gemini = FakeGemini()
    service = QuestionAnswerService(Settings(), gemini)
    eligible = resolve(service, "今日は500円？", QuestionContext(True, 10))
    ineligible = resolve(service, "今日は500円？", QuestionContext(False, 61))
    assert "QRコードを精算機にかざす" in eligible.text
    assert "豚汁たまご定食が500円" in eligible.text
    assert "対象ではない" in ineligible.text
    assert gemini.calls == 0


def test_repeat_visit_faq_explains_qr_code_without_gemini():
    gemini = FakeGemini()
    service = QuestionAnswerService(Settings(), gemini)
    answer = resolve(service, "再来店特典を教えて")
    assert "60日以内" in answer.text
    assert "QRコードを精算機にかざす" in answer.text
    assert "豚汁たまご定食が500円" in answer.text
    assert answer.source == "faq"
    assert gemini.calls == 0


def test_only_unknown_question_calls_gemini():
    gemini = FakeGemini(answer="休みの日は山で鍛錬します。")
    service = QuestionAnswerService(
        Settings(gemini_api_key="test", question_unknown_policy="gemini"), gemini
    )
    answer = resolve(service, "鬼さんは休みの日に何してるの？")
    assert answer.source == "gemini"
    assert answer.gemini_attempted
    assert gemini.calls == 1


def test_gemini_cache_does_not_make_request():
    gemini = FakeGemini(cached="以前の短い回答です。")
    service = QuestionAnswerService(
        Settings(gemini_api_key="test", question_unknown_policy="gemini"), gemini
    )
    answer = resolve(service, "自由な質問です")
    assert answer.source == "gemini_cache"
    assert gemini.calls == 0


def test_gemini_disabled_limit_and_errors_are_local():
    disabled = FakeGemini(available=False)
    gemini_settings = Settings(question_unknown_policy="gemini")
    assert resolve(QuestionAnswerService(gemini_settings, disabled), "自由な質問です").source == "gemini_disabled"
    limited = FakeGemini()
    settings = Settings(
        gemini_api_key="test",
        gemini_max_requests_per_session=3,
        question_unknown_policy="gemini",
    )
    assert resolve(QuestionAnswerService(settings, limited), "自由な質問です", used=3).source == "gemini_limit"
    assert limited.calls == 0
    for error in (RuntimeError("429"), asyncio.TimeoutError()):
        failed = FakeGemini(error=error)
        answer = resolve(QuestionAnswerService(settings, failed), "自由な質問です")
        assert answer.source == "gemini_error"
        assert failed.calls == 1


def test_unknown_question_uses_prerecorded_staff_answer_by_default():
    gemini = FakeGemini(answer="呼ばれてはいけない回答")
    service = QuestionAnswerService(Settings(gemini_api_key="test"), gemini)

    answer = resolve(service, "鬼さんの好きな季節は？")

    assert answer.source == "unsupported_question"
    assert answer.audio_key == "ask-staff"
    assert answer.text == "お答えできません。詳しくはスタッフにお尋ねください。"
    assert gemini.calls == 0

    debug_answer = resolve(service, "鬼さんの好きな季節は？", force_gemini=True)
    assert debug_answer.source == "gemini"
    assert gemini.calls == 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("豚汁はおかわりできますか", True),
        ("営業時間", True),
        ("今日は500円", True),
        ("鬼さんの好きな季節は", True),
        ("おすすめは？", True),
        ("ご視聴ありがとうございました", False),
        ("店内で音楽が流れています", False),
        ("明日は何をしますか？", True),
    ],
)
def test_spoken_question_gate_rejects_background_prose(text, expected):
    assert is_likely_spoken_question(text) is expected


def question_app(tmp_path, **overrides):
    values = {
        "database_path": tmp_path / "shop.db",
        "static_dir": tmp_path / "static",
        "camera_enabled": False,
        "debug_mode": True,
        "gemini_enabled": False,
        "voicevox_enabled": False,
        "vad_resume_delay_ms": 0,
    }
    values.update(overrides)
    settings = Settings(**values)
    return create_app(settings)


def claim_with_questions(ws):
    assert ws.receive_json()["state"] == "IDLE"
    ws.send_json({"type": "display_ready"})
    assert ws.receive_json() == {"type": "display_role", "active": True}
    ws.send_json({"type": "question_capability", "available": True})
    assert ws.receive_json() == {"type": "question_capability", "available": True}


def start_ready(client, ws):
    event = client.post("/api/debug/new-customer").json()["event"]
    assert ws.receive_json()["type"] == "customer_detected"
    ws.send_json({"type": "greeting_finished", "greeting_id": event["greeting_id"]})
    ready = ws.receive_json()
    assert ready["state"] == "READY"
    return ready["question_session_id"]


def test_greeting_to_ready_and_ready_timeout(tmp_path):
    app = question_app(
        tmp_path,
        question_ready_timeout_seconds=0.02,
        question_session_timeout_seconds=1,
    )
    with TestClient(app, base_url="http://localhost") as client, client.websocket_connect("ws://localhost/ws") as ws:
        claim_with_questions(ws)
        start_ready(client, ws)
        assert ws.receive_json()["state"] == "IDLE"
        assert client.get("/api/state").json()["state"] == "IDLE"


def test_touch_question_is_available_while_idle_and_returns_to_idle(tmp_path):
    class FakeWebSocketManager:
        def __init__(self):
            self.messages = []

        async def broadcast(self, payload):
            self.messages.append(payload)
            return 1

    async def scenario():
        manager = FakeWebSocketManager()
        controller = ReceptionController(
            SimpleNamespace(),
            manager,
            Settings(
                database_path=tmp_path / "shop.db",
                static_dir=tmp_path / "static",
                camera_enabled=False,
                question_input_mode="touch",
                gemini_enabled=False,
                voicevox_enabled=False,
                vad_resume_delay_ms=0,
            ),
        )
        question = get_touch_question("payment-method")
        assert question is not None

        answer = await controller.answer_touch_question(question)

        assert manager.messages[0]["type"] == "touch_question_started"
        assert manager.messages[0]["state"] == "THINKING"
        assert manager.messages[1]["type"] == "touch_answer_started"
        assert manager.messages[1]["state"] == "SPEAKING"
        assert (await controller.snapshot())["state"] == "SPEAKING"
        assert await controller.finish_answer(
            answer["question_session_id"], answer["question_id"]
        )
        assert manager.messages[-1]["state"] == "IDLE"
        assert (await controller.snapshot())["state"] == "IDLE"
        await controller.close()

    asyncio.run(scenario())


def test_question_flow_shows_text_before_voicevox_failure_and_returns_ready(tmp_path, monkeypatch):
    app = question_app(tmp_path, voicevox_enabled=True)
    monkeypatch.setattr(app.state.speech_recognizer, "transcribe", lambda audio: "豚汁はおかわりできる？")
    monkeypatch.setattr(
        app.state.voicevox,
        "synthesize",
        lambda text: (_ for _ in ()).throw(VoicevoxError("VOICEVOX failed")),
    )
    with TestClient(app, base_url="http://localhost") as client, client.websocket_connect("ws://localhost/ws") as ws:
        claim_with_questions(ws)
        session_id = start_ready(client, ws)
        question_id = "question-1"
        ws.send_json({
            "type": "speech_started",
            "question_session_id": session_id,
            "question_id": question_id,
        })
        assert ws.receive_json()["state"] == "LISTENING"
        response = client.post(
            f"/api/questions/{session_id}/{question_id}?duration_ms=1200",
            content=b"not-persisted-audio",
            headers={"content-type": "audio/webm"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["answer_source"] == "faq"
        assert "豚汁はお代わり自由" in body["answer"]
        assert body["audio_base64"] is None
        assert body["audio_url"] is None
        assert ws.receive_json()["state"] == "TRANSCRIBING"
        assert ws.receive_json()["type"] == "question_recognized"
        preview = ws.receive_json()
        assert preview["type"] == "answer_text_ready"
        assert "豚汁はお代わり自由" in preview["answer"]
        assert ws.receive_json()["type"] == "answer_started"
        ws.send_json({
            "type": "answer_finished",
            "question_session_id": session_id,
            "question_id": question_id,
        })
        assert ws.receive_json()["state"] == "READY"


def test_prerecorded_faq_audio_skips_voicevox_synthesis(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    audio_path = static_dir / "audio" / "faq" / "pork-soup-refill.wav"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"RIFFxxxxWAVEfast")
    app = question_app(tmp_path, voicevox_enabled=True, static_dir=static_dir)
    monkeypatch.setattr(app.state.speech_recognizer, "transcribe", lambda audio: "豚汁はおかわりできる？")
    monkeypatch.setattr(
        app.state.voicevox,
        "synthesize",
        lambda text: pytest.fail("prerecorded FAQ must skip VOICEVOX synthesis"),
    )
    with TestClient(app, base_url="http://localhost") as client, client.websocket_connect("ws://localhost/ws") as ws:
        claim_with_questions(ws)
        session_id = start_ready(client, ws)
        ws.send_json({
            "type": "speech_started",
            "question_session_id": session_id,
            "question_id": "fast-faq",
        })
        ws.receive_json()
        response = client.post(
            f"/api/questions/{session_id}/fast-faq?duration_ms=1200",
            content=b"audio",
            headers={"content-type": "audio/webm"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["audio_base64"] is None
        assert body["audio_url"].startswith(
            "/static/audio/faq/pork-soup-refill.wav?v="
        )


def test_voicevox_generates_valid_wav_and_reuses_memory_cache(monkeypatch):
    service = VoicevoxService(
        Settings(voicevox_cache_entries=2, voicevox_speed_scale=1.08)
    )
    calls: list[tuple[str, bytes | None]] = []

    def fake_request(url, body=None, content_type=None):
        calls.append((url, body))
        if "/audio_query?" in url:
            return json.dumps({"speedScale": 1.0}).encode("utf-8")
        return b"RIFFxxxxWAVEfast"

    monkeypatch.setattr(service, "_request", fake_request)
    first = service.synthesize("同じ回答です。")
    second = service.synthesize("同じ回答です。")
    assert first == second
    assert VoicevoxService.is_wav(first)
    assert service.status() == {"status": "ready", "last_error": None}
    assert len(calls) == 2
    configured_query = json.loads(calls[1][1])
    assert configured_query["speedScale"] == 1.08


def test_whisper_uses_fast_domain_aware_decoding_settings():
    settings = Settings(
        whisper_beam_size=1,
        whisper_max_new_tokens=80,
        whisper_initial_prompt="豚汁たまご定食。",
        whisper_hotwords="豚汁 たまご定食 QRコード",
    )
    recognizer = SpeechRecognizer(settings)

    class FakeModel:
        def __init__(self):
            self.options = None

        def transcribe(self, audio, **options):
            self.options = options
            return [SimpleNamespace(text=" 豚汁たまご定食はいくらですか。")], None

    model = FakeModel()
    recognizer._model = model
    assert recognizer.transcribe(b"audio") == "豚汁たまご定食はいくらですか。"
    assert model.options["beam_size"] == 1
    assert model.options["temperature"] == 0.0
    assert model.options["vad_filter"] is True
    assert model.options["vad_parameters"] == {
        "min_speech_duration_ms": settings.whisper_vad_min_speech_ms,
        "min_silence_duration_ms": settings.whisper_vad_min_silence_ms,
        "speech_pad_ms": settings.whisper_vad_speech_pad_ms,
    }
    assert model.options["without_timestamps"] is True
    assert model.options["initial_prompt"] == "豚汁たまご定食。"
    assert model.options["hotwords"] == "豚汁 たまご定食 QRコード"
    assert model.options["no_speech_threshold"] == settings.whisper_no_speech_threshold
    assert model.options["log_prob_threshold"] == settings.whisper_min_avg_logprob


def test_whisper_rejects_low_confidence_noise():
    recognizer = SpeechRecognizer(Settings())

    class FakeModel:
        def transcribe(self, audio, **options):
            return [
                SimpleNamespace(
                    text=" 誤って生成された文章です。",
                    no_speech_prob=0.95,
                    avg_logprob=-0.2,
                )
            ], None

    recognizer._model = FakeModel()
    assert recognizer.transcribe(b"ambient noise") == ""


@pytest.mark.parametrize(
    "recognized,corrected",
    [
        ("お兄さんの好きな食べ物は何ですか?", "鬼さんの好きな食べ物は何ですか?"),
        ("トンジル玉ご定食はいくらですか", "豚汁たまご定食はいくらですか"),
        ("ポン汁はおかわりできますか", "豚汁はおかわりできますか"),
        ("QR コードはどこにかさせばいいですか", "QRコードはどこにかざせばいいですか"),
        ("コーヒはいくらですか", "コーヒーはいくらですか"),
        ("豚汁たまご定食はイクラですか", "豚汁たまご定食はいくらですか"),
    ],
)
def test_domain_transcription_corrections(recognized, corrected):
    assert correct_domain_transcription(recognized) == corrected


def test_whisper_failure_is_silently_discarded(tmp_path, monkeypatch):
    app = question_app(tmp_path)
    def fail(audio):
        raise RuntimeError("whisper failed")
    monkeypatch.setattr(app.state.speech_recognizer, "transcribe", fail)
    with TestClient(app, base_url="http://localhost") as client, client.websocket_connect("ws://localhost/ws") as ws:
        claim_with_questions(ws)
        session_id = start_ready(client, ws)
        ws.send_json({"type": "speech_started", "question_session_id": session_id, "question_id": "q1"})
        ws.receive_json()
        response = client.post(
            f"/api/questions/{session_id}/q1?duration_ms=1000",
            content=b"audio",
            headers={"content-type": "audio/webm"},
        )
        assert response.status_code == 200
        assert response.json()["answer_source"] == "no_speech"
        assert response.json()["discarded"] is True
        assert [ws.receive_json()["state"], ws.receive_json()["state"]] == [
            "TRANSCRIBING",
            "READY",
        ]


def test_background_prose_is_silently_discarded(tmp_path, monkeypatch):
    app = question_app(tmp_path)
    monkeypatch.setattr(
        app.state.speech_recognizer,
        "transcribe",
        lambda audio: "店内で音楽が流れています。",
    )
    with TestClient(app, base_url="http://localhost") as client, client.websocket_connect("ws://localhost/ws") as ws:
        claim_with_questions(ws)
        session_id = start_ready(client, ws)
        ws.send_json({"type": "speech_started", "question_session_id": session_id, "question_id": "noise-prose"})
        ws.receive_json()
        response = client.post(
            f"/api/questions/{session_id}/noise-prose?duration_ms=1500",
            content=b"ambient audio",
            headers={"content-type": "audio/webm"},
        )
        assert response.status_code == 200
        assert response.json()["answer_source"] == "no_speech"
        assert response.json()["discarded"] is True
        assert [ws.receive_json()["state"], ws.receive_json()["state"]] == [
            "TRANSCRIBING",
            "READY",
        ]


def test_stale_question_id_is_rejected(tmp_path):
    app = question_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client, client.websocket_connect("ws://localhost/ws") as ws:
        claim_with_questions(ws)
        session_id = start_ready(client, ws)
        ws.send_json({"type": "speech_started", "question_session_id": session_id, "question_id": "current"})
        ws.receive_json()
        response = client.post(
            f"/api/questions/{session_id}/stale?duration_ms=1000",
            content=b"audio",
            headers={"content-type": "audio/webm"},
        )
        assert response.status_code == 409


def test_short_sound_is_discarded_without_transcription(tmp_path, monkeypatch):
    app = question_app(tmp_path)
    transcribe = monkeypatch.setattr(
        app.state.speech_recognizer,
        "transcribe",
        lambda audio: pytest.fail("short noise must not be transcribed"),
    )
    with TestClient(app, base_url="http://localhost") as client, client.websocket_connect("ws://localhost/ws") as ws:
        claim_with_questions(ws)
        session_id = start_ready(client, ws)
        ws.send_json({"type": "speech_started", "question_session_id": session_id, "question_id": "noise"})
        ws.receive_json()
        response = client.post(
            f"/api/questions/{session_id}/noise?duration_ms=100",
            content=b"noise",
            headers={"content-type": "audio/webm"},
        )
        assert response.status_code == 422
        assert ws.receive_json()["state"] == "READY"
