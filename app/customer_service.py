from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Sequence

from .config import Settings
from .database import Database
from .models import CustomerMatch, VisitResult


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CustomerService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    def match_customer(self, face_encoding: Sequence[float]) -> CustomerMatch | None:
        candidate = tuple(float(value) for value in face_encoding)
        if len(candidate) != 128 or not all(math.isfinite(value) for value in candidate):
            raise ValueError("face encoding must contain 128 finite numbers")
        best_match: CustomerMatch | None = None
        for customer in self.database.list_customers():
            if len(customer.face_encoding) != len(candidate):
                continue
            distance = math.sqrt(
                sum(
                    (stored_value - candidate_value) ** 2
                    for stored_value, candidate_value in zip(
                        customer.face_encoding, candidate, strict=True
                    )
                )
            )
            if distance <= self.settings.face_match_threshold and (
                best_match is None or distance < best_match.distance
            ):
                best_match = CustomerMatch(customer=customer, distance=distance)
        return best_match

    def register_new_customer(
        self,
        face_encoding: Sequence[float],
        now: datetime | None = None,
    ) -> VisitResult:
        seen_at = now or utc_now()
        customer = self.database.create_customer(face_encoding, seen_at)
        return VisitResult(
            customer=customer,
            previous_last_seen_at=None,
            visit_incremented=True,
            days_since_last_visit=None,
            discount_eligible=False,
        )

    def record_returning_visit(
        self,
        match: CustomerMatch,
        now: datetime | None = None,
    ) -> VisitResult:
        return self.database.record_visit(
            match.customer.id, now or utc_now(), self.settings.visit_cooldown_minutes,
            self.settings.discount_valid_days,
        )


def build_greeting_message(
    customer_type: str,
    days_since_last_visit: int | None,
    discount_eligible: bool,
    discount_valid_days: int = 60,
) -> str:
    if customer_type == "new":
        return (
            "いらっしゃいませ。初めてのご来店、ありがとうございます。"
            "当店では、豚汁たまご定食を1,200円でご用意しております。"
            "たまごとご飯は、どちらもお代わり自由です。"
            "コーヒーやお茶などのお飲み物は500円で、こちらもお代わり自由です。"
            f"また、2回目以降のご来店で、前回のご来店から{discount_valid_days}日以内の場合は、"
            "たまご定食を500円でご利用いただけます。"
            "配膳はセルフサービスとなっております。"
            "どうぞ、ごゆっくりお過ごしください。"
        )

    if days_since_last_visit is not None and days_since_last_visit >= 1:
        message = (
            f"お久しぶりですね。{days_since_last_visit}日ぶりですね。"
            "また来てくださって、ありがとうございます。"
        )
    else:
        message = "また来てくださって、ありがとうございます。お元気でしたか？"

    if discount_eligible:
        message += (
            f"前回のご来店から{discount_valid_days}日以内ですので、"
            "本日はたまご定食を500円でご利用いただけます。"
        )
    return message
