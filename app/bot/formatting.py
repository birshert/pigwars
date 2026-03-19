from __future__ import annotations

from html import escape

from app.domain.models.pig import PigStatus
from app.domain.rules.cooldowns import format_timedelta
from app.domain.rules.timezones import format_datetime_msk, format_time_msk
from app.schemas.battle import BattleMessagePayload
from app.schemas.leaderboard import LeaderboardEntry
from app.schemas.pig import (
    BattleEntryResult,
    DailyActionResult,
    DailyView,
    EquipResult,
    FeedResult,
    InventoryView,
    PigProfile,
    RaidResolutionResult,
    RaidStartResult,
    RenamePigResult,
    SabotageResult,
    UseItemResult,
    WorldEventView,
)


STATUS_LABELS = {
    PigStatus.IDLE: "бездельничает",
    PigStatus.BATTLE_READY: "ищет драку",
    PigStatus.IN_BATTLE: "в бою",
    PigStatus.ON_RAID: "в вылазке",
}


def format_start_message(*, is_group: bool) -> str:
    if is_group:
        return (
            "🐷 PigWars в строю.\n\n"
            "Команды:\n"
            "/create_pig <name> — создать свинью\n"
            "/rename_pig <name> — переименовать свинью\n"
            "/pig — посмотреть свою свинью\n"
            "/feed — покормить\n"
            "/battle — выйти на арену\n"
            "/daily — дневные ритуалы\n"
            "/inventory — инвентарь\n"
            "/equip <slot> — надеть предмет\n"
            "/use_item <slot> — использовать предмет\n"
            "/raid <свалка|рынок|лес> — отправить в вылазку\n"
            "/sabotage — диверсия в ответ на сообщение цели\n"
            "/world — мировое событие\n"
            "/leaderboard — лидерборд группы\n"
            "/rules — краткие правила"
        )
    return (
        "🐷 PigWars работает в группах.\n\n"
        "Добавь бота в Telegram-группу и используй там:\n"
        "/create_pig <name>, /rename_pig <name>, /pig, /feed, /battle, /daily, /raid, /inventory, /world"
    )


def format_help_message() -> str:
    return (
        "Команды PigWars:\n"
        "/create_pig <name> — создать свинью в этой группе\n"
        "/rename_pig <name> — переименовать свою свинью\n"
        "/pig — показать свою свинью\n"
        "/feed — кормить раз в час\n"
        "/battle — войти в боевой режим раз в 2 часа\n"
        "/daily — гороскоп, корыто и колесо позора\n"
        "/inventory — показать инвентарь\n"
        "/equip <slot> — экипировать предмет\n"
        "/use_item <slot> — использовать расходник; мокрую газету кидай reply-целью\n"
        "/raid <свалка|рынок|лес> — отправить свинью в вылазку\n"
        "/sabotage — ответом на сообщение цели устроить диверсию\n"
        "/world — текущее мировое событие\n"
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
        "5. Рейды идут 10 минут и дают лут с риском.\n"
        "6. Диверсии живут недолго и не наносят permanent-урон.\n"
        "7. Победитель боя тяжелеет, проигравший худеет.\n"
        "8. Лидерборд считается по весу внутри группы."
    )


def format_pig_profile(profile: PigProfile) -> str:
    lines = [
        f"🐷 {profile.name}",
        f"Черта: {profile.trait_title}",
        f"Эффект черты: {profile.trait_summary}",
        f"Вес: {profile.weight_kg} кг",
        f"Статус: {STATUS_LABELS[profile.status]}",
        f"Настроение: {profile.mood_label} ({profile.mood_score})",
        f"Лояльность: {profile.loyalty_label} ({profile.loyalty}/100)",
        f"Победы / поражения: {profile.wins} / {profile.losses}",
        f"Экипировка: {profile.equipped_item.title if profile.equipped_item else 'нет'}",
        "Активные эффекты: "
        + (", ".join(effect.title for effect in profile.active_effects) if profile.active_effects else "нет"),
        f"Мировое событие: {profile.world_event_title or 'нет'}",
        f"До следующего кормления: {format_timedelta(profile.next_feed_in)}",
        f"До следующего входа в бой: {format_timedelta(profile.next_battle_in)}",
        f"До следующей диверсии: {format_timedelta(profile.next_sabotage_in)}",
        f"До следующего рейда: {format_timedelta(profile.next_raid_in)}",
    ]
    if profile.world_event_title and profile.world_event_description:
        lines.append(f"Фон дня: {profile.world_event_description}")
    if profile.status == PigStatus.BATTLE_READY and profile.battle_ready_until is not None:
        lines.append(f"Ищет драку до: {format_time_msk(profile.battle_ready_until)}")
    if profile.status == PigStatus.ON_RAID and profile.raid_until is not None:
        lines.append(f"Вернётся из вылазки к: {format_time_msk(profile.raid_until)}")
    return "\n".join(lines)


def format_feed_result(result: FeedResult) -> str:
    return (
        f"🥕 {result.pig_name} сожрал всё, что нашёл.\n"
        f"+{result.weight_gain} кг\n\n"
        f"Текущий вес: {result.current_weight} кг\n"
        f"Настроение: {result.mood_label}\n"
        f"Лояльность: {result.loyalty_label}\n"
        f"Следующее кормление будет доступно через {format_timedelta(result.next_feed_in)}."
    )


def format_battle_entry(result: BattleEntryResult) -> str:
    return (
        f"⚔️ {result.pig_name} вышел на арену и подозрительно хрюкает.\n"
        f"Он будет искать драку до {format_time_msk(result.ready_until)}.\n"
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
    lines = [
        "🐷💥 Бой на арене!",
        "",
        f"{payload.pig1_name} ({payload.pig1_weight} кг) vs {payload.pig2_name} ({payload.pig2_weight} кг)",
        "",
        f"Победила {payload.winner_name} ({payload.winner_trait_title}) 🏆",
        f"Проиграла {payload.loser_name} ({payload.loser_trait_title})",
        "",
        f"{payload.winner_name} получает +{payload.winner_gain} кг",
        f"{payload.loser_name} теряет -{payload.loser_loss} кг",
    ]
    if payload.flavor_text is not None:
        lines.append(payload.flavor_text)
    if payload.winner_loot_title is not None:
        lines.append(f"Редкий дроп после боя: {payload.winner_loot_title}")
    if payload.broken_item_title is not None:
        lines.append(f"Экипировка сломалась: {payload.broken_item_title}")
    return "\n".join(lines)


def format_inventory(view: InventoryView) -> str:
    if not view.items:
        return f"🎒 У {view.pig_name} пусто. Неси её в рейды."

    lines = [f"🎒 Инвентарь {view.pig_name}:"]
    for index, item in enumerate(view.items, start=1):
        suffix = []
        if item.is_equipped:
            suffix.append("надето")
        if item.durability is not None and item.durability > 0:
            suffix.append(f"прочность {item.durability}")
        label = f" ({', '.join(suffix)})" if suffix else ""
        lines.append(f"{index}. {item.title}{label}")
        lines.append(f"   {item.summary}")
    return "\n".join(lines)


def format_equip_result(result: EquipResult) -> str:
    return f"🪖 {result.pig_name} теперь носит: {result.item_title}."


def format_use_item_result(result: UseItemResult) -> str:
    return f"🧪 {result.pig_name} использовала «{result.item_title}».\n{result.outcome_text}"


def format_rename_pig_result(result: RenamePigResult) -> str:
    if not result.changed:
        return f"🐷 Имя не изменилось: свинью уже зовут {result.new_name}."
    return f"🐷 Свинья переименована: {result.old_name} -> {result.new_name}."


def format_daily_view(view: DailyView) -> str:
    lines = [
        f"🌤️ /daily для {view.pig_name}",
        "",
        f"Свинский гороскоп: {view.horoscope_title}",
        view.horoscope_text,
        "",
        f"{view.trough.action_name}: "
        + ("доступно" if view.trough.available else f"уже разыграно — {view.trough.result_title}"),
    ]
    if view.trough.available:
        lines.append(f"Запуск: {view.trough.command_hint}")
    elif view.trough.result_text:
        lines.append(view.trough.result_text)

    lines.extend(
        [
            "",
            f"{view.wheel.action_name}: "
            + ("доступно" if view.wheel.available else f"уже крутануто — {view.wheel.result_title}"),
        ]
    )
    if view.wheel.available:
        lines.append(f"Запуск: {view.wheel.command_hint}")
    elif view.wheel.result_text:
        lines.append(view.wheel.result_text)

    lines.extend(
        [
            "",
            "Активные статусы: "
            + (", ".join(effect.title for effect in view.active_effects) if view.active_effects else "нет"),
        ]
    )
    if view.world_event_title is not None:
        lines.append(f"Глобальная встряска: {view.world_event_title}")
        if view.world_event_description:
            lines.append(view.world_event_description)
    return "\n".join(lines)


def format_daily_action_result(result: DailyActionResult) -> str:
    prefix = "уже было сегодня" if result.already_used else "сработало"
    return (
        f"🎲 {result.action_name}: {prefix}\n"
        f"{result.result_title}\n"
        f"{result.result_text}"
    )


def format_raid_start(result: RaidStartResult) -> str:
    return (
        f"🗺️ {result.pig_name} ушла в вылазку: {result.destination_title}.\n"
        f"Возврат ожидается к {format_time_msk(result.resolve_at)}.\n"
        f"Новый рейд будет доступен через {format_timedelta(result.next_raid_in)}."
    )


def format_raid_result(result: RaidResolutionResult) -> str:
    lines = [
        f"🗺️ {result.outcome_title}: {result.pig_name}",
        f"Направление: {result.destination_title}",
        result.narrative,
        f"Настроение сейчас: {result.mood_label}",
        f"Лояльность сейчас: {result.loyalty_label}",
    ]
    if result.weight_change > 0:
        lines.append(f"Прирост веса: +{result.weight_change} кг")
    if result.found_item_title is not None:
        lines.append(f"Найден предмет: {result.found_item_title}")
    if result.granted_effect_title is not None:
        lines.append(f"Получен эффект: {result.granted_effect_title}")
    return "\n".join(lines)


def format_raid_result_html(result: RaidResolutionResult) -> str:
    lines: list[str] = []
    if result.owner_telegram_user_id is not None and result.owner_mention_label is not None:
        mention_label = escape(result.owner_mention_label)
        lines.append(
            f"🐷 <a href=\"tg://user?id={result.owner_telegram_user_id}\">{mention_label}</a>, "
            f"{escape(result.pig_name)} вернулась из рейда."
        )
    else:
        lines.append(f"🐷 {escape(result.pig_name)} вернулась из рейда.")

    lines.extend(
        [
            f"🗺️ {escape(result.outcome_title)}: {escape(result.pig_name)}",
            f"Направление: {escape(result.destination_title)}",
            escape(result.narrative),
            f"Настроение сейчас: {escape(result.mood_label)}",
            f"Лояльность сейчас: {escape(result.loyalty_label)}",
        ]
    )
    if result.weight_change > 0:
        lines.append(f"Прирост веса: +{result.weight_change} кг")
    if result.found_item_title is not None:
        lines.append(f"Найден предмет: {escape(result.found_item_title)}")
    if result.granted_effect_title is not None:
        lines.append(f"Получен эффект: {escape(result.granted_effect_title)}")
    return "\n".join(lines)


def format_sabotage_result(result: SabotageResult) -> str:
    title = "🧨 Диверсия удалась" if result.success else "🧨 Диверсия провалилась"
    return f"{title}\n{result.narrative}"


def format_world_event(view: WorldEventView) -> str:
    lines = [
        f"🌍 {view.title}",
        view.description,
        "",
        "Эффекты:",
    ]
    lines.extend(f"• {effect}" for effect in view.effects)
    lines.append(f"До конца: {format_datetime_msk(view.ends_at)}")
    return "\n".join(lines)
