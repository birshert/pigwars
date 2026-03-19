from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db.base import build_engine, build_session_factory, session_scope
from app.db.repositories.admin_dashboard_repo import AdminDashboardRepository
from app.domain.services.player_dashboard_service import PlayerDashboardService
from app.web.auth import TelegramInitDataError, TelegramMiniAppSession, validate_telegram_webapp_init_data


STATIC_DIR = Path(__file__).resolve().parent / "static"
ADMIN_INDEX_FILE = STATIC_DIR / "index.html"
PLAYER_INDEX_FILE = STATIC_DIR / "me.html"


def create_app(
    *,
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = resolved_settings
        if session_factory is not None:
            app.state.session_factory = session_factory
            yield
            return

        engine = build_engine(resolved_settings)
        app.state.session_factory = build_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="PigWars Web", lifespan=lifespan)
    app.state.settings = resolved_settings
    if session_factory is not None:
        app.state.session_factory = session_factory
    app.mount("/admin/assets", StaticFiles(directory=STATIC_DIR), name="admin-assets")
    app.mount("/me/assets", StaticFiles(directory=STATIC_DIR), name="player-assets")

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/me", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/admin", include_in_schema=False)
    async def admin_index() -> FileResponse:
        return FileResponse(ADMIN_INDEX_FILE)

    @app.get("/me", include_in_schema=False)
    async def player_index() -> FileResponse:
        return FileResponse(PLAYER_INDEX_FILE)

    @app.get("/admin/api/dashboard")
    async def admin_dashboard(
        request: Request,
        admin_session: TelegramMiniAppSession = Depends(_get_admin_session),
    ) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        async with session_scope(_get_session_factory(request)) as session:
            repo = AdminDashboardRepository(session)
            return {
                "viewer": {
                    "id": admin_session.user.id,
                    "first_name": admin_session.user.first_name,
                    "last_name": admin_session.user.last_name,
                    "username": admin_session.user.username,
                    "is_premium": admin_session.user.is_premium,
                },
                "generated_at": now.isoformat(),
                "overview": await repo.get_overview(now=now),
                "active_world_events": await repo.list_active_world_events(now=now),
                "top_pigs": await repo.list_top_pigs(),
                "groups": await repo.list_group_summaries(),
                "recent_battles": await repo.list_recent_battles(),
                "recent_raids": await repo.list_recent_raids(),
                "recent_events": await repo.list_recent_pig_events(),
            }

    @app.get("/me/api/dashboard")
    async def player_dashboard(
        request: Request,
        session: TelegramMiniAppSession = Depends(_get_telegram_session),
    ) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        async with session_scope(_get_session_factory(request)) as db_session:
            service = PlayerDashboardService(
                db_session,
                feed_cooldown=resolved_settings.feed_cooldown,
                battle_cooldown=resolved_settings.battle_cooldown,
                sabotage_cooldown=resolved_settings.sabotage_cooldown,
                raid_cooldown=resolved_settings.raid_cooldown,
            )
            dashboard = await service.build_dashboard(
                telegram_user_id=session.user.id,
                now=now,
            )
        return {
            "viewer": {
                "id": session.user.id,
                "first_name": session.user.first_name,
                "last_name": session.user.last_name,
                "username": session.user.username,
                "is_premium": session.user.is_premium,
            },
            "generated_at": now.isoformat(),
            **dashboard,
        }

    return app


def _get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.session_factory


def _get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _extract_init_data(request: Request) -> str | None:
    header_value = request.headers.get("x-telegram-init-data")
    if header_value:
        return header_value

    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("tma "):
        return authorization[4:].strip()
    return None


def _get_telegram_session(request: Request) -> TelegramMiniAppSession:
    settings = _get_settings(request)
    init_data = _extract_init_data(request)
    if not init_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Open the dashboard from Telegram to provide Mini App auth data.",
        )

    try:
        session = validate_telegram_webapp_init_data(
            init_data,
            settings.bot_token,
            max_age_seconds=settings.telegram_webapp_auth_max_age_seconds,
        )
    except TelegramInitDataError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return session


def _get_admin_session(request: Request) -> TelegramMiniAppSession:
    settings = _get_settings(request)
    session = _get_telegram_session(request)

    if not settings.is_admin_telegram_user(session.user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This Telegram account is not an admin.")
    return session
