from __future__ import annotations

import logging
import math
import sqlite3
import struct
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, Sequence

from .models import Customer, VisitResult


logger = logging.getLogger(__name__)


def _datetime_to_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must include timezone information")
    return value.isoformat()


def _datetime_from_text(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _encode_face(values: Sequence[float]) -> bytes:
    normalized = tuple(float(value) for value in values)
    if len(normalized) != 128 or not all(math.isfinite(value) for value in normalized):
        raise ValueError("face encoding must contain 128 finite numbers")
    return struct.pack(f"<{len(normalized)}d", *normalized)


def _decode_face(value: bytes) -> tuple[float, ...]:
    if len(value) != 128 * 8:
        raise ValueError("invalid face encoding stored in database")
    return tuple(struct.unpack(f"<{len(value) // 8}d", value))


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 10000")
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = NORMAL")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS customers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        customer_id TEXT NOT NULL UNIQUE,
                        face_encoding BLOB NOT NULL,
                        first_seen_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL,
                        visit_count INTEGER NOT NULL DEFAULT 1 CHECK (visit_count >= 1),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_customers_last_seen_at "
                    "ON customers(last_seen_at)"
                )
                columns = {row[1] for row in connection.execute("PRAGMA table_info(customers)")}
                if "visit_previous_seen_at" not in columns:
                    connection.execute("ALTER TABLE customers ADD COLUMN visit_previous_seen_at TEXT")
                if "visit_discount_eligible" not in columns:
                    connection.execute("ALTER TABLE customers ADD COLUMN visit_discount_eligible INTEGER NOT NULL DEFAULT 0")
                connection.commit()
        except sqlite3.Error:
            logger.exception("[DB] Failed to initialize database: %s", self.path)
            raise

    def ping(self) -> bool:
        try:
            with self.connect() as connection:
                connection.execute("SELECT id FROM customers LIMIT 1").fetchone()
            return True
        except sqlite3.Error:
            logger.exception("[DB] Health check failed")
            return False

    def list_customers(self) -> list[Customer]:
        try:
            with self.connect() as connection:
                rows = connection.execute(
                    "SELECT id, customer_id, face_encoding, first_seen_at, last_seen_at, "
                    "visit_count, created_at, updated_at, visit_previous_seen_at, "
                    "visit_discount_eligible FROM customers ORDER BY id"
                ).fetchall()
            return [self._row_to_customer(row) for row in rows]
        except sqlite3.Error:
            logger.exception("[DB] Failed to read customers")
            raise

    def create_customer(self, face_encoding: Sequence[float], seen_at: datetime) -> Customer:
        timestamp = _datetime_to_text(seen_at)
        pending_id = f"pending_{uuid.uuid4().hex}"
        try:
            with self.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    INSERT INTO customers (
                        customer_id, face_encoding, first_seen_at, last_seen_at,
                        visit_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        pending_id,
                        _encode_face(face_encoding),
                        timestamp,
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
                row_id = int(cursor.lastrowid)
                customer_id = f"customer_{row_id:06d}"
                connection.execute(
                    "UPDATE customers SET customer_id = ? WHERE id = ?",
                    (customer_id, row_id),
                )
                row = connection.execute(
                    "SELECT id, customer_id, face_encoding, first_seen_at, last_seen_at, "
                    "visit_count, created_at, updated_at FROM customers WHERE id = ?",
                    (row_id,),
                ).fetchone()
                connection.commit()
            if row is None:
                raise RuntimeError("created customer could not be read back")
            return self._row_to_customer(row)
        except sqlite3.Error:
            logger.exception("[DB] Failed to create customer")
            raise

    def update_customer_seen(
        self,
        row_id: int,
        seen_at: datetime,
        increment_visit: bool,
    ) -> Customer:
        timestamp = _datetime_to_text(seen_at)
        increment = 1 if increment_visit else 0
        try:
            with self.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    UPDATE customers
                    SET last_seen_at = ?,
                        visit_count = visit_count + ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (timestamp, increment, timestamp, row_id),
                )
                row = connection.execute(
                    "SELECT id, customer_id, face_encoding, first_seen_at, last_seen_at, "
                    "visit_count, created_at, updated_at FROM customers WHERE id = ?",
                    (row_id,),
                ).fetchone()
                connection.commit()
            if row is None:
                raise LookupError(f"customer row not found: {row_id}")
            return self._row_to_customer(row)
        except sqlite3.Error:
            logger.exception("[DB] Failed to update customer: id=%s", row_id)
            raise

    def clear_customers(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM customers")
            connection.execute("DELETE FROM sqlite_sequence WHERE name = 'customers'")
            connection.commit()

    def backup(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source:
            with sqlite3.connect(destination) as target:
                source.backup(target)

    def record_visit(self, row_id: int, seen_at: datetime, cooldown_minutes: float,
                     discount_days: int) -> VisitResult:
        """Read, decide and update in one transaction; keep this visit's benefit stable."""
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM customers WHERE id = ?", (row_id,)).fetchone()
            if row is None:
                raise LookupError(f"customer row not found: {row_id}")
            before = self._row_to_customer(row)
            # A clock adjustment must not move last_seen_at backwards.
            seen_at = max(seen_at, before.last_seen_at)
            elapsed = seen_at - before.last_seen_at
            increment = elapsed > timedelta(minutes=cooldown_minutes)
            previous = before.last_seen_at if increment else before.visit_previous_seen_at
            eligible = (elapsed <= timedelta(days=discount_days)) if increment else before.visit_discount_eligible
            connection.execute(
                "UPDATE customers SET last_seen_at=?, updated_at=?, visit_count=visit_count+?, "
                "visit_previous_seen_at=?, visit_discount_eligible=? WHERE id=?",
                (_datetime_to_text(seen_at), _datetime_to_text(seen_at), int(increment),
                 _datetime_to_text(previous) if previous else None, int(eligible), row_id),
            )
            updated = connection.execute("SELECT * FROM customers WHERE id = ?", (row_id,)).fetchone()
            connection.commit()
        return VisitResult(self._row_to_customer(updated), before.last_seen_at, increment,
                           (seen_at - previous).days if previous else None, eligible)

    @staticmethod
    def _row_to_customer(row: sqlite3.Row) -> Customer:
        return Customer(
            id=int(row["id"]),
            customer_id=str(row["customer_id"]),
            face_encoding=_decode_face(row["face_encoding"]),
            first_seen_at=_datetime_from_text(row["first_seen_at"]),
            last_seen_at=_datetime_from_text(row["last_seen_at"]),
            visit_count=int(row["visit_count"]),
            created_at=_datetime_from_text(row["created_at"]),
            updated_at=_datetime_from_text(row["updated_at"]),
            visit_previous_seen_at=(
                _datetime_from_text(row["visit_previous_seen_at"])
                if "visit_previous_seen_at" in row.keys() and row["visit_previous_seen_at"] else None
            ),
            visit_discount_eligible=(
                bool(row["visit_discount_eligible"]) if "visit_discount_eligible" in row.keys() else False
            ),
        )
