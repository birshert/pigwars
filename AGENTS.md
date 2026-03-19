# AGENTS.md

## Продовые контейнеры

- Продовый Docker Compose стек этого репозитория обычно состоит из контейнеров `pigwars-bot-1`, `pigwars-worker-1`, `pigwars-db-1` и `pigwars-redis-1`.
- Основные приложенческие контейнеры: `pigwars-bot-1` и `pigwars-worker-1`.
- Инфраструктурные контейнеры: `pigwars-db-1` и `pigwars-redis-1`.

## Как запускать

- Запускать команды из `/Users/alexeybirshert/pigwars`.
- Поднять весь стек с нуля: `docker compose -f /Users/alexeybirshert/pigwars/docker-compose.yml up -d --build`.
- Поднять только приложенческие контейнеры, если `db` и `redis` уже работают: `docker compose -f /Users/alexeybirshert/pigwars/docker-compose.yml up -d bot worker`.

## Как перезапускать

- Обычный перезапуск без пересборки: `docker compose -f /Users/alexeybirshert/pigwars/docker-compose.yml restart bot worker`.
- Если нужно подхватить изменения из репозитория, обычного `restart` недостаточно.
- В `bot` и `worker` код копируется внутрь образа во время сборки, поэтому для выката нового кода пересобирай и пересоздавай контейнеры командой `docker compose -f /Users/alexeybirshert/pigwars/docker-compose.yml up -d --build bot worker`.
- Полная остановка стека: `docker compose -f /Users/alexeybirshert/pigwars/docker-compose.yml down`.
- `db` и `redis` без необходимости не перезапускай.

## Проверка после рестарта

- Проверить статус контейнеров: `docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'`.
- Проверить логи бота: `docker logs --tail 40 pigwars-bot-1`.
- Проверить логи воркера: `docker logs --tail 40 pigwars-worker-1`.
