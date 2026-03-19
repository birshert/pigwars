# PigWars

PigWars is a Telegram group bot where every member can raise one pig per group, feed it, throw it into a battle queue, and climb a weight leaderboard.

## Stack

- Python 3.12
- `uv`
- aiogram 3
- FastAPI
- PostgreSQL 16
- Redis 7
- SQLAlchemy 2 async
- Alembic
- Docker Compose

## Local run

1. Copy `.env.example` to `.env` and set `BOT_TOKEN`.
2. Set `ADMIN_TELEGRAM_USER_IDS` to the Telegram user IDs allowed into the admin dashboard.
3. Set `MINI_APP_URL` to the public HTTPS URL that opens `/admin`.
4. Start infrastructure with `docker compose up --build`.

## Manual commands

- Run bot: `uv run python -m app.main`
- Run worker: `uv run python -m app.worker`
- Run admin web: `uv run python -m app.web.main`
- Run tests: `uv run pytest`
- Apply migrations: `uv run alembic upgrade head`

## Admin Mini App

- The admin dashboard is served by the `web` service on port `8080`.
- Telegram Mini Apps require a public HTTPS URL. For local testing, expose `http://localhost:8080` through a tunnel or reverse proxy and point `MINI_APP_URL` to `https://.../admin`.
- Open the dashboard from Telegram by sending `/admin` to the bot in a private chat from an allowed admin account.
- Player dashboard is available at `/me` and opens from `/dashboard` in a private chat with the bot.

## ngrok

- Install: `brew install ngrok`
- Add your token once: `ngrok config add-authtoken <your_token>`
- Start the app stack: `docker compose up -d --build bot worker web`
- Start the tunnel from the host: `ngrok http 8080`
- If `MINI_APP_URL` or `PLAYER_MINI_APP_URL` is empty, the bot will try to detect the current ngrok HTTPS URL through `NGROK_API_URL` and open `/admin` or `/me` automatically.
