from __future__ import annotations

from enum import StrEnum


class DiseaseRollStatus(StrEnum):
    TRIGGERED = "triggered"
    SKIPPED = "skipped"
