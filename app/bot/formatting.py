from __future__ import annotations

from app.domain.models.pig import PigStatus
from app.domain.rules.cooldowns import format_timedelta
from app.schemas.battle import BattleMessagePayload
from app.schemas.leaderboard import LeaderboardEntry
from app.schemas.pig import BattleEntryResult, FeedResult, PigProfile


STATUS_LABELS = {
    PigStatus.IDLE: "idle",
    PigStatus.BATTLE_READY: "battle_ready",
    PigStatus.IN_BATTLE: "in_battle",
}


def format_start_message(*, is_group: bool) -> str:
    if is_group:
        return (
            "🐷 PigWars в строю.\n\n"
            "Команды:\n"
            "/create_pig <name> — создать свинью\n"
            "/pig — посмотреть свою свинью\n"
            "/feed — покормить\n"
            "/battle — выйти на арену\n"
            "/leaderboard — лидерборд группы\n"
            "/rules — краткие правила"
        )
    return (
        "🐷 PigWars работает в группах.\n\n"
        "Добавь бота в Telegram-группу и используй там:\n"
        "/create_pig <name>, /pig, /feed, /battle, /leaderboard"
    )


def format_help_message() -> str:
    return (
        "Команды PigWars:\n"
        "/create_pig <name> — создать свинью в этой группе\n"
        "/pig — показать свою свинью\n"
        "/feed — кормить раз в час\n"
        "/battle — войти в боевой режим раз в 2 часа\n"
        "/leaderboard — топ свиней по весу\n"
        "/rules — короткие правила"
    )


def format_rules_message() -> str:
    return (
        "Правила MVP:\n"
        "1. В одной группе у тебя может быть только одна свинья.\n"
        "2. Кормить можно раз в 1 час.\n"
        "3. В боевой режим можно входить раз в 2 часа.\n"
        "4. Боевой режим живёт 15 минут.\n"
        "5. Победитель боя тяжелеет, проигравший худеет.\n"
        "6. Лидерборд считается по весу внутри группы."
    )


def format_pig_profile(profile: PigProfile) -> str:
    lines = [
        f"🐷 {profile.name}",
        f"Вес: {profile.weight_kg} кг",
        f"Статус: {STATUS_LABELS[profile.status]}",
        f"Победы / поражения: {profile.wins} / {profile.losses}",
        f"До следующего кормления: {format_timedelta(profile.next_feed_in)}",
        f"До следующего входа в бой: {format_timedelta(profile.next_battle_in)}",
    ]
    if profile.status == PigStatus.BATTLE_READY and profile.battle_ready_until is not None:
        lines.append(f"Ищет драку до: {profile.battle_ready_until:%H:%M UTC}")
    return "\n".join(lines)


def format_feed_result(result: FeedResult) -> str:
    return (
        f"🥕 {result.pig_name} сожрал всё, что нашёл.\n"
        f"+{result.weight_gain} кг\n\n"
        f"Текущий вес: {result.current_weight} кг\n"
        f"Следующее кормление будет доступно через {format_timedelta(result.next_feed_in)}."
    )


def format_battle_entry(result: BattleEntryResult) -> str:
    return (
        f"⚔️ {result.pig_name} вышел на арену и подозрительно хрюкает.\n"
        f"Он будет искать драку до {result.ready_until:%H:%M UTC}.\n"
        f"Повторно в бой можно через {format_timedelta(result.next_battle_in)}."
    )


def format_leaderboard(entries: list[LeaderboardEntry]) -> str:
    if not entries:
        return "🐷 В этой группе пока нет свиней."

    header = ["🐷 Топ жирнейших свиней группы", ""]
    rows = [
        f"{entry.place}. {entry.pig_name} — {entry.weight_kg} кг ({entry.owner_label}, {entry.wins}/{entry.losses})"
        for entry in entries
    ]
    return "\n".join(header + rows)


def format_battle_result(payload: BattleMessagePayload) -> str:
    return (
        "🐷💥 Бой на арене!\n\n"
        f"{payload.pig1_name} ({payload.pig1_weight} кг) vs {payload.pig2_name} ({payload.pig2_weight} кг)\n\n"
        "После короткой, но унизительной свиной схватки\n"
        f"победил: {payload.winner_name} 🏆\n\n"
        f"{payload.winner_name} получает +{payload.winner_gain} кг\n"
        f"{payload.loser_name} теряет -{payload.loser_loss} кг"
    )
