# PigWars

PigWars is a Telegram group bot where every member can raise one pig per group, feed it, throw it into a battle queue, and climb a weight leaderboard.

## Stack

- Python 3.12
- `uv`
- aiogram 3
- PostgreSQL 16
- Redis 7
- SQLAlchemy 2 async
- Alembic
- Docker Compose

## Local run

1. Copy `.env.example` to `.env` and set `BOT_TOKEN`.
2. Start infrastructure with `docker compose up --build`.

## Manual commands

- Run bot: `uv run python -m app.main`
- Run worker: `uv run python -m app.worker`
- Run tests: `uv run pytest`
- Apply migrations: `uv run alembic upgrade head`
