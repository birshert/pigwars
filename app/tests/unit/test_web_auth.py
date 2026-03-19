from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

import pytest

from app.web.auth import TelegramInitDataError, validate_telegram_webapp_init_data


def _build_init_data(*, bot_token: str, telegram_user_id: int, auth_date: datetime) -> str:
    payload = {
        "auth_date": str(int(auth_date.timestamp())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            {
                "id": telegram_user_id,
                "first_name": "Admin",
                "last_name": "Pig",
                "username": "boss_hog",
                "language_code": "ru",
                "is_premium": True,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    payload["hash"] = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode(payload)


def test_validate_telegram_webapp_init_data_accepts_valid_payload() -> None:
    now = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)
    init_data = _build_init_data(bot_token="test-token", telegram_user_id=241301944, auth_date=now)

    session = validate_telegram_webapp_init_data(
        init_data,
        "test-token",
        max_age_seconds=86400,
        now=now,
    )

    assert session.user.id == 241301944
    assert session.user.username == "boss_hog"
    assert session.user.is_premium is True


def test_validate_telegram_webapp_init_data_rejects_tampered_payload() -> None:
    now = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)
    init_data = _build_init_data(bot_token="test-token", telegram_user_id=241301944, auth_date=now)
    tampered = init_data.replace("boss_hog", "intruder")

    with pytest.raises(TelegramInitDataError, match="signature mismatch"):
        validate_telegram_webapp_init_data(
            tampered,
            "test-token",
            max_age_seconds=86400,
            now=now,
        )
