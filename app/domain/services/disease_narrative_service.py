from __future__ import annotations

from app.config import Settings
from app.domain.rules.timezones import format_datetime_msk
from app.schemas.disease import DiseaseNarrativeContext, DiseaseNarrativeResult


class DiseaseNarrativeService:
    def __init__(self, _settings: Settings) -> None:
        pass

    async def generate_narrative(self, context: DiseaseNarrativeContext) -> DiseaseNarrativeResult:
        fallback = self.build_fallback(context)
        return DiseaseNarrativeResult(text=fallback, llm_model=None, used_llm=False)

    def build_fallback(self, context: DiseaseNarrativeContext) -> str:
        if context.fatal_outcome:
            if context.death_message is not None:
                return context.death_message
            return f"☠️ {context.pig_name} скончалась от «{context.disease_title}». Хлев записал это как производственный риск."

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
