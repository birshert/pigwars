from __future__ import annotations

from enum import StrEnum


class DailyDigestStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
