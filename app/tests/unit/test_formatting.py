from __future__ import annotations

from decimal import Decimal

from app.bot.formatting import format_raid_result_html
from app.schemas.pig import RaidResolutionResult


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
