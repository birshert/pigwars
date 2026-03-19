from __future__ import annotations

from types import SimpleNamespace

from app.domain.services.leaderboard_service import _build_owner_label


def test_owner_label_prefers_full_name_without_ping() -> None:
    user = SimpleNamespace(
        username="alpha",
        first_name="Alpha",
        last_name="Master",
        telegram_user_id=111,
    )

    assert _build_owner_label(user) == "Alpha Master"


def test_owner_label_falls_back_to_username_without_at_prefix() -> None:
    user = SimpleNamespace(
        username="alpha",
        first_name="",
        last_name=None,
        telegram_user_id=111,
    )

    assert _build_owner_label(user) == "alpha"
