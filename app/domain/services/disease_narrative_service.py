from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.config import Settings
from app.domain.rules.timezones import format_datetime_msk
from app.logging import logger
from app.schemas.disease import DiseaseNarrativeContext, DiseaseNarrativeResult


class DiseaseNarrativeService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate_narrative(self, context: DiseaseNarrativeContext) -> DiseaseNarrativeResult:
        fallback = self.build_fallback(context)
        if not self._settings.openai_api_key or not self._settings.disease_model:
            return DiseaseNarrativeResult(text=fallback, llm_model=None, used_llm=False)

        prompt = "Факты о заболевании:\n" + json.dumps(context.to_payload(), ensure_ascii=False, indent=2)
        instructions = (
            "Ты пишешь короткое сообщение о заболевании свиньи для Telegram-группы PigWars на русском языке. "
            "Используй только факты из JSON. Не придумывай новые штрафы, причины, предметы, даты или цифры. "
            "Обязательно отрази название болезни, потерю веса и карантин, если он есть. "
            "Тон определи по полю tone_hint: можно ехидно, жалостливо или театрально, но без грубости и без токсичности к игроку. "
            "Выход: 2-4 коротких предложения, без markdown, без списков, до 280 символов."
        )

        try:
            async with AsyncOpenAI(
                api_key=self._settings.openai_api_key,
                timeout=self._settings.disease_llm_timeout_seconds,
            ) as client:
                response = await client.responses.create(
                    model=self._settings.disease_model,
                    instructions=instructions,
                    input=prompt,
                    max_output_tokens=140,
                )
        except Exception:
            logger.warning(
                "Disease LLM request failed for group %s pig %s disease %s",
                context.group_id,
                context.pig_name,
                context.disease_title,
                exc_info=True,
            )
            return DiseaseNarrativeResult(text=fallback, llm_model=None, used_llm=False)

        text = self._normalize_text(getattr(response, "output_text", ""))
        if not self._is_valid_message(text):
            logger.warning(
                "Disease LLM returned invalid message for group %s pig %s disease %s",
                context.group_id,
                context.pig_name,
                context.disease_title,
            )
            return DiseaseNarrativeResult(text=fallback, llm_model=None, used_llm=False)

        return DiseaseNarrativeResult(
            text=text,
            llm_model=self._settings.disease_model,
            used_llm=True,
        )

    def build_fallback(self, context: DiseaseNarrativeContext) -> str:
        first = (
            f"🤒 {context.pig_name} словила «{context.disease_title}» и сразу схуднула на -{context.weight_loss:.2f} кг."
        )
        second = (
            f"Настроение теперь {context.mood_label}, лояльность {context.loyalty_label}, а хлев выглядит откровенно недовольным."
        )
        if context.quarantine_until is not None:
            third = f"Свину увели в карантин до {format_datetime_msk(context.quarantine_until)}."
        else:
            third = f"Эта напасть будет висеть до {format_datetime_msk(context.effect_expires_at)}."
        return " ".join([first, second, third])

    def _normalize_text(self, text: str) -> str:
        return " ".join(text.split())

    def _is_valid_message(self, text: str) -> bool:
        if len(text) < 40 or len(text) > 320:
            return False
        banned_markers = ("•", "1.", "2.", "3.", "#", "*")
        return not any(marker in text for marker in banned_markers)
