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
from app.db.models import Pig, PigEffect, PigEvent, PigItem, TelegramGroup, TelegramUser, WorldEvent
from app.domain.models.pig import PigItemType, PigStatus, PigTrait
from app.web.app import create_app


def _build_init_data(*, bot_token: str, telegram_user_id: int, auth_date: datetime) -> str:
    payload = {
        "auth_date": str(int(auth_date.timestamp())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            {
                "id": telegram_user_id,
                "first_name": "Player",
                "last_name": "Pig",
                "username": "player_hog",
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
async def test_player_dashboard_api_returns_only_viewer_pigs(session_factory) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    settings = Settings(BOT_TOKEN="test-token")

    async with session_scope(session_factory) as session:
        owner = TelegramUser(
            telegram_user_id=7001,
            username="player_hog",
            first_name="Player",
            last_name="Pig",
        )
        stranger = TelegramUser(
            telegram_user_id=7002,
            username="stranger_hog",
            first_name="Stranger",
            last_name="Pig",
        )
        group = TelegramGroup(telegram_group_id=-100501, title="Player Pen")
        session.add_all([owner, stranger, group])
        await session.flush()

        player_pig = Pig(
            id=uuid4(),
            group_id=group.id,
            owner_user_id=owner.id,
            name="Dashboard Ham",
            weight_kg=Decimal("9.80"),
            status=PigStatus.ON_RAID,
            trait=PigTrait.CUNNING,
            mood_score=11,
            loyalty=64,
            wins=3,
            losses=2,
            last_feed_at=now - timedelta(minutes=20),
            last_battle_at=now - timedelta(hours=5),
            last_sabotage_at=now - timedelta(hours=8),
            last_raid_at=now - timedelta(minutes=2),
            raid_until=now + timedelta(minutes=8),
        )
        stranger_pig = Pig(
            id=uuid4(),
            group_id=group.id,
            owner_user_id=stranger.id,
            name="Not Yours",
            weight_kg=Decimal("11.10"),
            status=PigStatus.IDLE,
            trait=PigTrait.AGGRESSIVE,
            mood_score=0,
            loyalty=50,
            wins=0,
            losses=0,
        )
        session.add_all([player_pig, stranger_pig])
        await session.flush()

        session.add(
            PigItem(
                pig_id=player_pig.id,
                group_id=group.id,
                item_code="iron_pot",
                item_type=PigItemType.EQUIPMENT,
                is_equipped=True,
                durability=2,
            )
        )
        session.add(
            PigEffect(
                pig_id=player_pig.id,
                group_id=group.id,
                effect_type="battle_focus",
                source_type="daily",
                expires_at=now + timedelta(hours=2),
            )
        )
        session.add(
            PigEvent(
                pig_id=player_pig.id,
                group_id=group.id,
                event_type="raid_started",
                created_at=now - timedelta(minutes=1),
            )
        )
        session.add(
            PigEvent(
                pig_id=stranger_pig.id,
                group_id=group.id,
                event_type="intruder_event",
                created_at=now,
            )
        )
        session.add(
            WorldEvent(
                event_code="lard_fest",
                title="Праздник сала",
                description="Все свиньи слегка жиреют от одного вида корыт.",
                starts_at=now - timedelta(hours=1),
                ends_at=now + timedelta(hours=1),
            )
        )
        await session.commit()

    app = create_app(settings=settings, session_factory=session_factory)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/me/api/dashboard",
            headers={
                "X-Telegram-Init-Data": _build_init_data(
                    bot_token="test-token",
                    telegram_user_id=7001,
                    auth_date=now,
                )
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["viewer"]["id"] == 7001
    assert payload["summary"]["pig_count"] == 1
    assert payload["summary"]["latest_group_title"] == "Player Pen"
    assert len(payload["pigs"]) == 1
    assert payload["pigs"][0]["profile"]["name"] == "Dashboard Ham"
    assert payload["pigs"][0]["profile"]["equipped_item"]["title"] == "Кастрюля на голове"
    assert payload["pigs"][0]["profile"]["active_effects"][0]["title"] == "Боевой раж"
    assert payload["pigs"][0]["profile"]["world_event_title"] == "Праздник сала"
    assert payload["recent_events"][0]["event_type"] == "raid_started"
    assert all(event["event_type"] != "intruder_event" for event in payload["recent_events"])
