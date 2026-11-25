from dataclasses import replace
from datetime import datetime, timedelta, timezone
import asyncio
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.config import Settings
from app.main import create_app

FACE = (0.1,) * 128

@pytest.fixture
def app(tmp_path):
    # These tests exercise the original face-reception lifecycle. Question
    # session transitions are covered separately in test_questions.py.
    return create_app(Settings(
        database_path=tmp_path / "shop.db",
        camera_enabled=False,
        debug_mode=True,
        question_enabled=False,
    ))

def client_for(app):
    return TestClient(app, base_url="http://localhost")

def claim(ws):
    assert ws.receive_json()["state"] == "IDLE"
    ws.send_json({"type": "display_ready"})
    assert ws.receive_json() == {"type": "display_role", "active": True}

def test_production_debug_disabled(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "shop.db", camera_enabled=False))
    with client_for(app) as client:
        assert client.post("/api/debug/new-customer").status_code == 404
        assert client.get("/debug").status_code == 404
        assert client.get("/docs").status_code == 404
        assert client.get("/").status_code == 200

def test_public_config_exposes_preferred_microphone(tmp_path):
    app = create_app(Settings(
        database_path=tmp_path / "shop.db",
        camera_enabled=False,
        microphone_device_label="USB Condenser Microphone",
    ))
    endpoint = next(route.endpoint for route in app.routes if route.path == "/api/config")
    config = asyncio.run(endpoint())
    assert config["questions"]["microphone_device_label"] == "USB Condenser Microphone"
    assert config["assistance_voice"] == {
        "enabled": True,
        "cooldown_seconds": 20.0,
        "start_threshold": 0.010,
        "start_duration_ms": 200.0,
        "calibration_ms": 500.0,
        "noise_multiplier": 1.4,
        "noise_margin": 0.0025,
        "speech_band_ratio": 0.20,
        "zcr_min": 0.001,
        "zcr_max": 0.45,
    }

def test_requires_ready_display(app):
    with client_for(app) as client:
        assert client.post("/api/debug/new-customer").status_code == 409
        with client.websocket_connect("ws://localhost/ws") as ws:
            ws.receive_json()
            assert client.post("/api/debug/new-customer").status_code == 409
        assert client.portal.call(app.state.reception.process_face_encoding, FACE) is None
        assert app.state.database.list_customers() == []

@pytest.mark.parametrize("route,kind,eligible,days", [
    ("/api/debug/new-customer", "new", False, None),
    ("/api/debug/returning-customer?days_since_last_visit=10", "returning", True, 10),
    ("/api/debug/returning-customer?days_since_last_visit=60", "returning", True, 60),
    ("/api/debug/returning-customer?days_since_last_visit=61", "returning", False, 61),
])
def test_debug_websocket(app, route, kind, eligible, days):
    with client_for(app) as client, client.websocket_connect("ws://localhost/ws") as ws:
        claim(ws)
        assert client.post(route).status_code == 200
        event = ws.receive_json()
        assert event["customer_type"] == kind
        assert event["discount_eligible"] is eligible
        assert event["days_since_last_visit"] == days
        assert client.post("/api/debug/new-customer").status_code == 409
        ws.send_json({"type": "greeting_finished", "greeting_id": event["greeting_id"]})
        assert ws.receive_json()["state"] == "IDLE"
        assert app.state.database.list_customers() == []

def test_wrong_id_and_observer_cannot_finish(app):
    with client_for(app) as client, client.websocket_connect("ws://localhost/ws") as ws:
        claim(ws)
        with client.websocket_connect("ws://localhost/ws") as observer:
            observer.receive_json()
            observer.send_json({"type": "display_ready"})
            assert observer.receive_json()["active"] is False
            client.post("/api/debug/new-customer")
            event = ws.receive_json()
            ws.send_json({"type": "greeting_finished"})
            ws.send_json({"type": "greeting_finished", "greeting_id": "stale"})
            observer.send_json({"type": "greeting_finished", "greeting_id": event["greeting_id"]})
            observer.send_json({"type": "ping"})
            assert observer.receive_json()["type"] == "pong"
            ws.send_json({"type": "ping"})
            assert ws.receive_json()["type"] == "pong"
            assert client.get("/api/state").json()["state"] == "GREETING"
            ws.send_json({"type": "greeting_finished", "greeting_id": event["greeting_id"]})
            assert ws.receive_json()["state"] == "IDLE"
            assert observer.receive_json()["state"] == "IDLE"

def test_empty_and_invalid_websocket_messages_are_ignored(app):
    with client_for(app) as client, client.websocket_connect("ws://localhost/ws") as ws:
        assert ws.receive_json()["state"] == "IDLE"
        ws.send_text("")
        ws.send_text("not-json")
        ws.send_text("[]")
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}

def test_real_path_and_cooldowns(app):
    with client_for(app) as client, client.websocket_connect("ws://localhost/ws") as ws:
        claim(ws)
        controller = app.state.reception
        event = client.portal.call(controller.process_face_encoding, FACE)
        assert ws.receive_json()["customer_id"] == "customer_000001"
        old = app.state.database.list_customers()[0].last_seen_at
        assert client.portal.call(controller.process_face_encoding, FACE) is None
        assert app.state.database.list_customers()[0].last_seen_at > old
        assert app.state.database.list_customers()[0].visit_count == 1
        assert client.portal.call(controller.process_face_encoding, (1.0,) * 128) is None
        assert len(app.state.database.list_customers()) == 1
        ws.send_json({"type": "greeting_finished", "greeting_id": event["greeting_id"]})
        ws.receive_json()
        assert client.portal.call(controller.process_face_encoding, FACE) is None
        assert client.portal.call(controller.process_face_encoding, (1.0,) * 128) is None
        controller._last_global_greeting_at -= timedelta(seconds=10)
        assert client.portal.call(controller.process_face_encoding, FACE) is None
        other = client.portal.call(controller.process_face_encoding, (1.0,) * 128)
        assert other["customer_id"] == "customer_000002"
        assert ws.receive_json()["customer_id"] == "customer_000002"

def test_returning_full_path(app):
    with client_for(app) as client, client.websocket_connect("ws://localhost/ws") as ws:
        claim(ws)
        app.state.database.create_customer(FACE, datetime.now(timezone.utc) - timedelta(days=10))
        event = client.portal.call(app.state.reception.process_face_encoding, FACE)
        received = ws.receive_json()
        assert received == event
        assert received["visit_count"] == 2
        assert received["days_since_last_visit"] == 10
        assert received["discount_eligible"]

def test_disconnect_resets(app):
    with client_for(app) as client:
        with client.websocket_connect("ws://localhost/ws") as ws:
            claim(ws)
            client.post("/api/debug/new-customer")
            ws.receive_json()
        assert client.get("/api/state").json()["state"] == "IDLE"

def test_timeout_resets(app):
    with client_for(app) as client, client.websocket_connect("ws://localhost/ws") as ws:
        claim(ws)
        app.state.reception.settings = replace(app.state.settings, greeting_timeout_seconds=0.02)
        client.post("/api/debug/new-customer")
        assert ws.receive_json()["type"] == "customer_detected"
        assert ws.receive_json()["state"] == "IDLE"

def test_db_failure_survives(app, monkeypatch):
    with client_for(app) as client, client.websocket_connect("ws://localhost/ws") as ws:
        claim(ws)
        def fail():
            raise OSError("database unavailable")
        monkeypatch.setattr(app.state.database, "list_customers", fail)
        assert client.portal.call(app.state.reception.process_face_encoding, FACE) is None
        assert client.get("/api/state").json()["state"] == "IDLE"
        assert client.get("/").status_code == 200

def test_missing_video_survives(app):
    with client_for(app) as client:
        assert client.get("/static/videos/missing.mp4").status_code == 404
        assert client.get("/").status_code == 200

def test_health_reports_display_readiness(app):
    with client_for(app) as client:
        assert client.get("/health").json()["display_ready"] is False
        with client.websocket_connect("ws://localhost/ws") as ws:
            claim(ws)
            health = client.get("/health").json()
            assert health["display_ready"] is True
            assert health["websocket_clients"] == 1

def test_missing_video_is_degraded(tmp_path):
    settings = Settings(database_path=tmp_path / "shop.db", camera_enabled=False,
                        idle_video_url="/static/videos/nonexistent.mp4")
    with client_for(create_app(settings)) as client:
        health = client.get("/health").json()
        assert health["status"] == "degraded"
        assert health["videos"] == "missing"

def test_startup_db_error_still_serves_display(tmp_path):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("fixture", encoding="utf-8")
    settings = Settings(database_path=blocked / "shop.db", camera_enabled=False)
    with client_for(create_app(settings)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/health").json()["database"] == "error"

def test_origin_and_host(app):
    with client_for(app) as client:
        assert client.post("/api/debug/new-customer", headers={"origin": "https://example.com"}).status_code == 403
        assert client.get("/health", headers={"host": "evil.example"}).status_code == 400
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("ws://localhost/ws", headers={"origin": "https://example.com"}):
                pass
