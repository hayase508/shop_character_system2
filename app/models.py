from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Customer:
    id: int
    customer_id: str
    face_encoding: tuple[float, ...]
    first_seen_at: datetime
    last_seen_at: datetime
    visit_count: int
    created_at: datetime
    updated_at: datetime
    visit_previous_seen_at: datetime | None = None
    visit_discount_eligible: bool = False


@dataclass(frozen=True, slots=True)
class CustomerMatch:
    customer: Customer
    distance: float


@dataclass(frozen=True, slots=True)
class VisitResult:
    customer: Customer
    previous_last_seen_at: datetime | None
    visit_incremented: bool
    days_since_last_visit: int | None
    discount_eligible: bool
