from datetime import datetime, timedelta, timezone
import pytest
from app.config import Settings
from app.customer_service import CustomerService, build_greeting_message
from app.database import Database

FACE = (0.1,) * 128
START = datetime(2026, 1, 1, tzinfo=timezone.utc)

@pytest.fixture
def service(tmp_path):
    db = Database(tmp_path / "shop.db")
    db.initialize()
    return CustomerService(db, Settings(database_path=db.path))

def test_new_roundtrip(service):
    result = service.register_new_customer(FACE, START)
    assert result.customer.customer_id == "customer_000001"
    assert result.customer.visit_count == 1
    assert result.customer.first_seen_at == START
    assert result.customer.face_encoding == FACE
    assert not result.discount_eligible
    assert service.match_customer(FACE).distance == 0
    assert service.match_customer((1.1,) * 128) is None

def test_new_customer_drink_price_is_five_hundred_yen():
    message = build_greeting_message("new", None, False)
    assert "豚汁とたまごとご飯は、すべてお代わり自由" in message
    assert "お飲み物は500円" in message
    assert "300円" not in message

@pytest.mark.parametrize("days,eligible", [(10, True), (60, True), (61, False)])
def test_previous_timestamp(service, days, eligible):
    service.register_new_customer(FACE, START)
    result = service.record_returning_visit(service.match_customer(FACE), START + timedelta(days=days))
    assert result.previous_last_seen_at == START
    assert result.days_since_last_visit == days
    assert result.discount_eligible is eligible
    assert result.customer.visit_count == 2
    assert result.customer.last_seen_at == START + timedelta(days=days)
    assert ("500円" in build_greeting_message("returning", days, eligible)) is eligible

def test_sixty_days_plus_second(service):
    service.register_new_customer(FACE, START)
    result = service.record_returning_visit(service.match_customer(FACE), START + timedelta(days=60, seconds=1))
    assert result.days_since_last_visit == 60
    assert not result.discount_eligible

@pytest.mark.parametrize("minutes,increment", [(59, False), (60, False), (61, True)])
def test_cooldown_boundary(service, minutes, increment):
    service.register_new_customer(FACE, START)
    result = service.record_returning_visit(service.match_customer(FACE), START + timedelta(minutes=minutes))
    assert result.visit_incremented is increment
    assert result.customer.visit_count == (2 if increment else 1)
    assert result.discount_eligible is increment

def test_continuous_presence(service):
    service.register_new_customer(FACE, START)
    for minute in range(1, 181):
        result = service.record_returning_visit(service.match_customer(FACE), START + timedelta(minutes=minute))
        assert result.customer.visit_count == 1
        assert not result.discount_eligible
    assert result.customer.last_seen_at == START + timedelta(hours=3)

def test_expired_benefit_stays_expired_after_restart(service):
    service.register_new_customer(FACE, START)
    returned = START + timedelta(days=61)
    service.record_returning_visit(service.match_customer(FACE), returned)
    restarted = CustomerService(Database(service.database.path), service.settings)
    again = restarted.record_returning_visit(restarted.match_customer(FACE), returned + timedelta(seconds=61))
    assert again.customer.visit_count == 2
    assert not again.discount_eligible
    assert again.days_since_last_visit == 61

def test_stale_match_does_not_increment_twice(service):
    service.register_new_customer(FACE, START)
    match = service.match_customer(FACE)
    when = START + timedelta(days=10)
    service.record_returning_visit(match, when)
    assert service.record_returning_visit(match, when + timedelta(seconds=1)).customer.visit_count == 2

def test_clock_rollback(service):
    service.register_new_customer(FACE, START)
    result = service.record_returning_visit(service.match_customer(FACE), START - timedelta(hours=1))
    assert result.customer.last_seen_at == START
    assert result.customer.visit_count == 1

@pytest.mark.parametrize("encoding", [(), (0.1,), (float("nan"),) * 128, (float("inf"),) * 128])
def test_invalid_features(service, encoding):
    with pytest.raises(ValueError):
        service.register_new_customer(encoding, START)
    with pytest.raises(ValueError):
        service.match_customer(encoding)

def test_configured_discount_message():
    message = build_greeting_message("returning", 10, True, 30)
    assert "30日以内" in message and "60日以内" not in message

def test_reset(service):
    service.register_new_customer(FACE, START)
    service.database.clear_customers()
    assert service.database.list_customers() == []
    assert service.database.ping()

def test_backup_can_restore_customer(service, tmp_path):
    service.register_new_customer(FACE, START)
    backup = tmp_path / "backups" / "snapshot.db"
    service.database.backup(backup)
    service.database.clear_customers()
    assert Database(backup).list_customers()[0].customer_id == "customer_000001"
