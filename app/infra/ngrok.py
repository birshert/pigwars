from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from app.config import Settings


DEFAULT_NGROK_API_URLS = (
    "http://127.0.0.1:4040/api/tunnels",
    "http://host.docker.internal:4040/api/tunnels",
)


def resolve_admin_mini_app_url(
    settings: Settings,
    *,
    urlopen_fn: Callable[..., object] = urlopen,
) -> str | None:
    return resolve_mini_app_url(
        settings,
        explicit_url=settings.mini_app_url,
        default_path="/admin",
        urlopen_fn=urlopen_fn,
    )


def resolve_player_mini_app_url(
    settings: Settings,
    *,
    urlopen_fn: Callable[..., object] = urlopen,
) -> str | None:
    return resolve_mini_app_url(
        settings,
        explicit_url=settings.player_mini_app_url,
        default_path="/me",
        urlopen_fn=urlopen_fn,
    )


def resolve_mini_app_url(
    settings: Settings,
    *,
    explicit_url: str | None,
    default_path: str,
    urlopen_fn: Callable[..., object] = urlopen,
) -> str | None:
    if explicit_url:
        return explicit_url

    base_url = _extract_base_url(settings.player_mini_app_url) or _extract_base_url(settings.mini_app_url)
    if base_url is None:
        base_url = resolve_ngrok_public_url(
            web_port=settings.web_port,
            ngrok_api_url=settings.ngrok_api_url,
            urlopen_fn=urlopen_fn,
        )
    if base_url is None:
        return None
    return f"{base_url.rstrip('/')}{default_path}"


def resolve_ngrok_public_url(
    *,
    web_port: int,
    ngrok_api_url: str | None = None,
    urlopen_fn: Callable[..., object] = urlopen,
) -> str | None:
    candidate_urls = []
    if ngrok_api_url:
        candidate_urls.append(ngrok_api_url)
    candidate_urls.extend(url for url in DEFAULT_NGROK_API_URLS if url != ngrok_api_url)

    for api_url in candidate_urls:
        payload = _load_ngrok_tunnels(api_url, urlopen_fn=urlopen_fn)
        if payload is None:
            continue
        public_url = _pick_public_url(payload, web_port=web_port)
        if public_url is not None:
            return public_url
    return None


def _load_ngrok_tunnels(
    api_url: str,
    *,
    urlopen_fn: Callable[..., object],
) -> dict[str, object] | None:
    request = _build_request(api_url)
    try:
        with urlopen_fn(request, timeout=0.8) as response:
            body = response.read()
    except OSError:
        return None

    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _build_request(api_url: str) -> Request | str:
    parsed = urlsplit(api_url)
    if parsed.hostname == "host.docker.internal":
        return Request(api_url, headers={"Host": "127.0.0.1:4040"})
    return api_url


def _extract_base_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _pick_public_url(payload: dict[str, object], *, web_port: int) -> str | None:
    tunnels = payload.get("tunnels")
    if not isinstance(tunnels, list):
        return None

    preferred_addrs = {
        f"http://localhost:{web_port}",
        f"localhost:{web_port}",
        f"http://127.0.0.1:{web_port}",
        f"127.0.0.1:{web_port}",
        f"http://host.docker.internal:{web_port}",
        f"host.docker.internal:{web_port}",
        f"http://web:{web_port}",
        f"web:{web_port}",
    }
    fallback_public_url: str | None = None

    for tunnel in tunnels:
        if not isinstance(tunnel, dict):
            continue
        public_url = tunnel.get("public_url")
        if not isinstance(public_url, str) or not public_url.startswith("https://"):
            continue
        config = tunnel.get("config")
        addr = config.get("addr") if isinstance(config, dict) else None
        if isinstance(addr, str) and addr in preferred_addrs:
            return public_url
        if fallback_public_url is None:
            fallback_public_url = public_url

    return fallback_public_url
