from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl


class TelegramInitDataError(ValueError):
    """Raised when Telegram Mini App initData is missing or invalid."""


@dataclass(frozen=True, slots=True)
class TelegramMiniAppUser:
    id: int
    username: str | None
    first_name: str
    last_name: str | None
    language_code: str | None
    is_premium: bool


@dataclass(frozen=True, slots=True)
class TelegramMiniAppSession:
    auth_date: datetime
    user: TelegramMiniAppUser
    query_id: str | None
    raw_data: dict[str, str]


def validate_telegram_webapp_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int,
    now: datetime | None = None,
) -> TelegramMiniAppSession:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not pairs or received_hash is None:
        raise TelegramInitDataError("Missing Telegram init data hash")

    data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise TelegramInitDataError("Telegram init data signature mismatch")

    auth_date_raw = pairs.get("auth_date")
    if auth_date_raw is None:
        raise TelegramInitDataError("Missing auth_date in Telegram init data")
    try:
        auth_timestamp = int(auth_date_raw)
    except ValueError as exc:
        raise TelegramInitDataError("Invalid auth_date in Telegram init data") from exc

    current_time = now or datetime.now(timezone.utc)
    current_timestamp = int(current_time.timestamp())
    if auth_timestamp > current_timestamp + 30:
        raise TelegramInitDataError("Telegram init data auth_date is in the future")
    if current_timestamp - auth_timestamp > max_age_seconds:
        raise TelegramInitDataError("Telegram init data is too old")

    user_raw = pairs.get("user")
    if user_raw is None:
        raise TelegramInitDataError("Missing Telegram user payload")
    try:
        user_payload = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise TelegramInitDataError("Invalid Telegram user payload") from exc

    try:
        user = TelegramMiniAppUser(
            id=int(user_payload["id"]),
            username=user_payload.get("username"),
            first_name=str(user_payload.get("first_name") or ""),
            last_name=user_payload.get("last_name"),
            language_code=user_payload.get("language_code"),
            is_premium=bool(user_payload.get("is_premium", False)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TelegramInitDataError("Incomplete Telegram user payload") from exc

    if not user.first_name:
        raise TelegramInitDataError("Telegram user first_name is empty")

    return TelegramMiniAppSession(
        auth_date=datetime.fromtimestamp(auth_timestamp, tz=timezone.utc),
        user=user,
        query_id=pairs.get("query_id"),
        raw_data=pairs,
    )
