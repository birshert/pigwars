from __future__ import annotations

from app.config import Settings
from app.schemas.digest import DailyDigestFacts, DailyDigestSummaryResult


class DailyDigestSummaryService:
    def __init__(self, _settings: Settings) -> None:
        pass

    async def generate_summary(self, facts: DailyDigestFacts) -> DailyDigestSummaryResult:
        fallback = self._build_fallback_paragraph(facts)
        return DailyDigestSummaryResult(text=fallback, llm_model=None, used_llm=False)

    def _build_fallback_paragraph(self, facts: DailyDigestFacts) -> str:
        counts = facts.counts
        highlight_map = {highlight.type: highlight for highlight in facts.highlights}
        if counts.activity_total == 0:
            return (
                "Вчера в загоне было тихо: без боёв, рейдов и большого свинского шума. "
                "Стадо просто пережевало сутки и спокойно вкатывается в новое утро."
            )

        activity_parts: list[str] = []
        if counts.battles:
            activity_parts.append(f"{counts.battles} боёв")
        if counts.raids_total:
            activity_parts.append(f"{counts.raids_total} вылазок")
        if counts.sabotage_success:
            activity_parts.append(f"{counts.sabotage_success} удачных диверсий")
        elif counts.sabotage_total:
            activity_parts.append(f"{counts.sabotage_total} диверсий")

        if activity_parts:
            first_sentence = "Вчера в загоне было шумно: " + ", ".join(activity_parts) + "."
        else:
            first_sentence = "Вчера жизнь в загоне не стояла на месте, пусть и без большой драмы."

        sentences = [first_sentence]
        top_gain = highlight_map.get("top_gain")
        if top_gain is not None and top_gain.pig_name and top_gain.weight_delta is not None:
            sentences.append(f"Сильнее всех отъелся {top_gain.pig_name}: +{top_gain.weight_delta} кг за день.")

        raid_loot = highlight_map.get("raid_loot")
        if raid_loot is not None and raid_loot.pig_name and raid_loot.item_title:
            sentences.append(f"Трофей дня у {raid_loot.pig_name}: «{raid_loot.item_title}» из рейда.")
        else:
            bad_raid = highlight_map.get("raid_bad")
            if bad_raid is not None:
                sentences.append(bad_raid.text)

        world_event = facts.world_event
        if world_event is not None and world_event.active:
            sentences.append(f"Над хлевом всё ещё висит мировое событие «{world_event.title}».")

        return " ".join(sentences[:3])
