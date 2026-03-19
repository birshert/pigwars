from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.db.base import session_scope
from app.db.models import Battle, Pig, PigEvent, PigRaid, TelegramGroup, TelegramUser, WorldEvent
from app.domain.models.pig import PigRaidStatus, PigStatus, PigTrait, RaidDestination
from app.web.app import create_app


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
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    payload["hash"] = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode(payload)


@pytest.mark.asyncio
async def test_admin_dashboard_api_returns_overview_and_activity(session_factory) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    settings = Settings(
        BOT_TOKEN="test-token",
        ADMIN_TELEGRAM_USER_IDS="241301944",
        TELEGRAM_WEBAPP_AUTH_MAX_AGE_SECONDS=86400,
    )

    async with session_scope(session_factory) as session:
        group = TelegramGroup(telegram_group_id=-100777, title="Admin Pen")
        owner = TelegramUser(
            telegram_user_id=777,
            username="pig_keeper",
            first_name="Pig",
            last_name="Keeper",
        )
        session.add_all([group, owner])
        await session.flush()

        pig = Pig(
            id=uuid4(),
            group_id=group.id,
            owner_user_id=owner.id,
            name="Marshal Ham",
            weight_kg=Decimal("12.40"),
            status=PigStatus.BATTLE_READY,
            trait=PigTrait.LUCKY,
            mood_score=22,
            loyalty=71,
            wins=4,
            losses=1,
            battle_ready_until=now + timedelta(minutes=10),
        )
        session.add(pig)
        await session.flush()

        session.add(
            Battle(
                id=uuid4(),
                group_id=group.id,
                pig1_id=pig.id,
                pig2_id=pig.id,
                winner_pig_id=pig.id,
                loser_pig_id=pig.id,
                pig1_score=Decimal("18.20"),
                pig2_score=Decimal("17.10"),
                weight_delta_winner=Decimal("0.40"),
                weight_delta_loser=Decimal("0.25"),
                created_at=now - timedelta(minutes=5),
            )
        )
        session.add(
            PigRaid(
                id=uuid4(),
                pig_id=pig.id,
                group_id=group.id,
                destination=RaidDestination.DUMP,
                status=PigRaidStatus.ACTIVE,
                started_at=now - timedelta(minutes=2),
                resolve_at=now + timedelta(minutes=8),
            )
        )
        session.add(
            PigEvent(
                pig_id=pig.id,
                group_id=group.id,
                event_type="feed",
                created_at=now - timedelta(minutes=1),
            )
        )
        session.add(
            WorldEvent(
                event_code="mud_moon",
                title="Грязевая луна",
                description="Свиньи тащатся по липкой грязи и жиреют быстрее.",
                starts_at=now - timedelta(hours=1),
                ends_at=now + timedelta(hours=3),
            )
        )
        await session.commit()

    app = create_app(settings=settings, session_factory=session_factory)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/admin/api/dashboard",
            headers={
                "X-Telegram-Init-Data": _build_init_data(
                    bot_token="test-token",
                    telegram_user_id=241301944,
                    auth_date=now,
                )
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["viewer"]["id"] == 241301944
    assert payload["overview"]["groups"] == 1
    assert payload["overview"]["pigs"] == 1
    assert payload["overview"]["battle_ready_pigs"] == 1
    assert payload["overview"]["active_raids"] == 1
    assert payload["overview"]["active_world_events"] == 1
    assert payload["top_pigs"][0]["pig_name"] == "Marshal Ham"
    assert payload["groups"][0]["title"] == "Admin Pen"
    assert payload["recent_battles"][0]["winner_name"] == "Marshal Ham"
    assert payload["recent_raids"][0]["status"] == "active"
    assert payload["recent_events"][0]["event_type"] == "feed"
