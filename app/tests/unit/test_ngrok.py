from __future__ import annotations

import json

from app.config import Settings
from app.infra.ngrok import resolve_admin_mini_app_url, resolve_ngrok_public_url, resolve_player_mini_app_url


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_resolve_admin_mini_app_url_prefers_explicit_setting() -> None:
    settings = Settings(
        BOT_TOKEN="test-token",
        MINI_APP_URL="https://fixed.example.com/admin",
    )

    assert resolve_admin_mini_app_url(settings) == "https://fixed.example.com/admin"


def test_resolve_ngrok_public_url_uses_matching_https_tunnel() -> None:
    def fake_urlopen(url: str, timeout: float):
        return _FakeResponse(
            {
                "tunnels": [
                    {
                        "public_url": "https://other.ngrok-free.app",
                        "config": {"addr": "http://localhost:3000"},
                    },
                    {
                        "public_url": "https://pigwars.ngrok-free.app",
                        "config": {"addr": "http://localhost:8080"},
                    },
                ]
            }
        )

    public_url = resolve_ngrok_public_url(
        web_port=8080,
        ngrok_api_url="http://127.0.0.1:4040/api/tunnels",
        urlopen_fn=fake_urlopen,
    )

    assert public_url == "https://pigwars.ngrok-free.app"


def test_resolve_admin_mini_app_url_builds_admin_path_from_ngrok() -> None:
    settings = Settings(
        BOT_TOKEN="test-token",
        WEB_PORT=8080,
    )

    def fake_urlopen(url: str, timeout: float):
        return _FakeResponse(
            {
                "tunnels": [
                    {
                        "public_url": "https://pigwars.ngrok-free.app",
                        "config": {"addr": "http://localhost:8080"},
                    }
                ]
            }
        )

    assert resolve_admin_mini_app_url(settings, urlopen_fn=fake_urlopen) == "https://pigwars.ngrok-free.app/admin"


def test_resolve_player_mini_app_url_builds_player_path_from_admin_origin() -> None:
    settings = Settings(
        BOT_TOKEN="test-token",
        MINI_APP_URL="https://fixed.example.com/admin",
    )

    assert resolve_player_mini_app_url(settings) == "https://fixed.example.com/me"
