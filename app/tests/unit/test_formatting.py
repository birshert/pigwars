from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.bot.formatting import format_battle_result, format_disease_announcement_html, format_feed_result, format_raid_result_html
from app.bot.routers.features import DESTINATION_ALIASES
from app.domain.feature_catalog import get_raid_destination
from app.domain.models.pig import RaidDestination
from app.schemas.battle import BattleMessagePayload
from app.schemas.disease import DiseaseAnnouncement
from app.schemas.pig import FeedResult, RaidResolutionResult


def test_format_raid_result_html_mentions_owner_and_escapes_fields() -> None:
    result = RaidResolutionResult(
        telegram_group_id=-10001,
        owner_telegram_user_id=555,
        owner_mention_label='@raid<&>"owner',
        pig_name='Scout <prime>',
        destination_title='Рынок & лес',
        outcome_title='Удачная <вылазка>',
        narrative='Нашла "редкий" <трофей> & вернулась.',
        weight_change=Decimal("0.45"),
        mood_label='Бодрая & довольная',
        loyalty_label='Верная <почти>',
        found_item_title='Шлем <грязи>',
        granted_effect_title='Добрые "приметы"',
        flavor_text=None,
    )

    message = format_raid_result_html(result)

    assert '<a href="tg://user?id=555">@raid&lt;&amp;&gt;&quot;owner</a>' in message
    assert "Scout &lt;prime&gt; вернулась из рейда." in message
    assert "🗺️ Удачная &lt;вылазка&gt;: Scout &lt;prime&gt;" in message
    assert "Направление: Рынок &amp; лес" in message
    assert "Нашла &quot;редкий&quot; &lt;трофей&gt; &amp; вернулась." in message
    assert "Настроение сейчас: Бодрая &amp; довольная" in message
    assert "Лояльность сейчас: Верная &lt;почти&gt;" in message
    assert "Найден предмет: Шлем &lt;грязи&gt;" in message
    assert "Получен эффект: Добрые &quot;приметы&quot;" in message


def test_format_disease_announcement_html_mentions_owner_and_escapes_text() -> None:
    result = DiseaseAnnouncement(
        roll_id=1,
        telegram_group_id=-10001,
        text='🤒 Хрюн заболел <серьёзно> & теперь "страдает".',
        group_title="Pen",
        owner_telegram_user_id=777,
        owner_mention_label='@owner<&>"pig',
    )

    message = format_disease_announcement_html(result)

    assert '<a href="tg://user?id=777">@owner&lt;&amp;&gt;&quot;pig</a>' in message
    assert "у вашей свиньи неприятности." in message
    assert "🤒 Хрюн заболел &lt;серьёзно&gt; &amp; теперь &quot;страдает&quot;." in message


def test_format_feed_result_adds_stable_flavor_text() -> None:
    result = FeedResult(
        pig_name="Хряпыч",
        weight_gain=Decimal("0.92"),
        current_weight=Decimal("12.34"),
        next_feed_in=timedelta(hours=1),
        mood_label="Доволен",
        loyalty_label="Верный",
    )

    message = format_feed_result(result)

    assert "Хряпыч вылизал корыто так, будто там прятали вторую зарплату по желудям." in message
    assert "+0.92 кг" in message


def test_format_battle_result_adds_extra_flavor_text() -> None:
    payload = BattleMessagePayload(
        telegram_group_id=-10001,
        pig1_name="Гром",
        pig1_weight=Decimal("13.40"),
        pig2_name="Шмяк",
        pig2_weight=Decimal("12.80"),
        winner_name="Гром",
        loser_name="Шмяк",
        winner_gain=Decimal("0.75"),
        loser_loss=Decimal("0.42"),
        winner_trait_title="Агрессивная",
        loser_trait_title="Флегматичная",
        winner_loot_title=None,
        broken_item_title=None,
        flavor_text=None,
    )

    message = format_battle_result(payload)

    assert "Гром и Шмяк влетели в арену так, будто делили последнее корыто района." in message
    assert "После такого замеса Гром выглядит как хозяйка арены, а Шмяк как важный урок по технике падения." in message


def test_new_raid_destinations_are_available_in_catalog_and_aliases() -> None:
    assert DESTINATION_ALIASES["мельница"] == RaidDestination.MILL
    assert DESTINATION_ALIASES["пристань"] == RaidDestination.PIER
    assert DESTINATION_ALIASES["усадьба"] == RaidDestination.MANOR
    assert get_raid_destination(RaidDestination.MILL).title == "Старая мельница"
    assert get_raid_destination(RaidDestination.PIER).title == "Речная пристань"
    assert get_raid_destination(RaidDestination.MANOR).title == "Барская усадьба"
