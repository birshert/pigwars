const tg = window.Telegram?.WebApp;
const viewerName = document.getElementById("viewer-name");
const generatedAt = document.getElementById("generated-at");
const summaryGrid = document.getElementById("summary-grid");
const pigCards = document.getElementById("pig-cards");
const recentEvents = document.getElementById("recent-events");
const refreshButton = document.getElementById("refresh-button");
const statusPill = document.getElementById("status-pill");

let loading = false;

if (tg) {
  tg.ready();
  tg.expand();
}

refreshButton.addEventListener("click", () => {
  void loadDashboard();
});

void loadDashboard();
setInterval(() => {
  void loadDashboard();
}, 45000);

async function loadDashboard() {
  if (loading) {
    return;
  }
  loading = true;
  setStatus("Загрузка", "loading");

  try {
    const initData = tg?.initData ?? "";
    if (!initData) {
      throw new Error("Открой mini app из Telegram, чтобы получить личный дашборд.");
    }

    const response = await fetch("/me/api/dashboard", {
      headers: {
        "X-Telegram-Init-Data": initData,
      },
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Не удалось загрузить личный дашборд.");
    }

    renderDashboard(payload);
    setStatus("Live", "live");
  } catch (error) {
    renderError(error instanceof Error ? error.message : "Неизвестная ошибка.");
    setStatus("Ошибка", "error");
  } finally {
    loading = false;
  }
}

function renderDashboard(payload) {
  const viewer = payload.viewer;
  viewerName.textContent = viewer.username
    ? `@${viewer.username}`
    : [viewer.first_name, viewer.last_name].filter(Boolean).join(" ") || String(viewer.id);
  generatedAt.textContent = formatDateTime(payload.generated_at);

  summaryGrid.innerHTML = renderSummary(payload.summary);
  pigCards.innerHTML = renderPigs(payload.pigs);
  recentEvents.innerHTML = renderEvents(payload.recent_events);
}

function renderError(message) {
  viewerName.textContent = "Нет данных";
  generatedAt.textContent = "—";
  const state = `<div class="empty-state">${escapeHtml(message)}</div>`;
  summaryGrid.innerHTML = state;
  pigCards.innerHTML = state;
  recentEvents.innerHTML = state;
}

function renderSummary(summary) {
  const cards = [
    ["Свиней", summary.pig_count, "Профили по всем твоим группам"],
    ["Общий вес", `${summary.total_weight_kg} кг`, "Суммарный жир стратегического значения"],
    ["Победы", summary.total_wins, "Все выигранные бои"],
    ["Поражения", summary.total_losses, "Все проигрыши"],
    ["Последняя группа", summary.latest_group_title || "—", "Где была последняя игровая активность"],
  ];
  return cards
    .map(
      ([label, value, hint]) => `
        <article class="summary-card">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(String(value))}</strong>
          <small>${escapeHtml(hint)}</small>
        </article>
      `,
    )
    .join("");
}

function renderPigs(items) {
  if (!items.length) {
    return `
      <div class="empty-state">
        У тебя пока нет свиней. Добавь бота в группу и создай свинью через <code>/create_pig &lt;name&gt;</code>.
      </div>
    `;
  }

  return items
    .map((item) => {
      const profile = item.profile;
      const effectChips = profile.active_effects.length
        ? profile.active_effects
            .map((effect) => `<span class="chip">${escapeHtml(effect.title)}</span>`)
            .join("")
        : `<span class="chip chip--muted">Нет активных эффектов</span>`;

      const cooldownChips = [
        ["Кормление", formatDuration(profile.next_feed_in_seconds)],
        ["Арена", formatDuration(profile.next_battle_in_seconds)],
        ["Диверсия", formatDuration(profile.next_sabotage_in_seconds)],
        ["Рейд", formatDuration(profile.next_raid_in_seconds)],
      ]
        .map(([label, value]) => `<span class="chip chip--muted">${escapeHtml(label)}: ${escapeHtml(value)}</span>`)
        .join("");

      return `
        <article class="pig-card">
          <div class="pig-card__top">
            <div class="pig-card__title">
              <strong>${escapeHtml(profile.name)}</strong>
              <span>${escapeHtml(item.group_title)} · ${escapeHtml(profile.trait_title)}</span>
            </div>
            <div class="pig-card__meta">
              <span>${escapeHtml(profile.status)}</span><br />
              <span>Группа: ${escapeHtml(String(item.group_telegram_id))}</span>
            </div>
          </div>

          <div class="pig-card__stats">
            <div class="stat-box"><span>Вес</span><strong>${escapeHtml(profile.weight_kg)} кг</strong></div>
            <div class="stat-box"><span>Настроение</span><strong>${escapeHtml(profile.mood_label)} (${profile.mood_score})</strong></div>
            <div class="stat-box"><span>Лояльность</span><strong>${escapeHtml(profile.loyalty_label)} (${profile.loyalty}/100)</strong></div>
            <div class="stat-box"><span>Бои</span><strong>${profile.wins}/${profile.losses}</strong></div>
            <div class="stat-box"><span>Инвентарь</span><strong>${item.inventory_count}</strong></div>
          </div>

          <div class="pig-card__blocks">
            <section class="info-block">
              <h3>Черта</h3>
              <p>${escapeHtml(profile.trait_summary)}</p>
            </section>

            <section class="info-block">
              <h3>Экипировка</h3>
              <p>${profile.equipped_item ? `${escapeHtml(profile.equipped_item.title)}. ${escapeHtml(profile.equipped_item.summary)}` : "Ничего не экипировано."}</p>
            </section>

            <section class="info-block">
              <h3>Кулдауны</h3>
              <div class="list-chip">${cooldownChips}</div>
            </section>

            <section class="info-block">
              <h3>Эффекты</h3>
              <div class="list-chip">${effectChips}</div>
            </section>

            <section class="info-block">
              <h3>Мировое событие</h3>
              <p>${profile.world_event_title ? `${escapeHtml(profile.world_event_title)}. ${escapeHtml(profile.world_event_description || "")}` : "Сейчас ничего глобального не влияет."}</p>
            </section>

            <section class="info-block">
              <h3>Состояние</h3>
              <p>${profile.battle_ready_until ? `На арене до ${escapeHtml(formatDateTime(profile.battle_ready_until))}.` : ""}${profile.raid_until ? ` В рейде до ${escapeHtml(formatDateTime(profile.raid_until))}.` : ""}${!profile.battle_ready_until && !profile.raid_until ? "Спокойный режим без срочных таймеров." : ""}</p>
            </section>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderEvents(items) {
  if (!items.length) {
    return `<div class="empty-state">По твоим свиньям ещё нет событий.</div>`;
  }
  return items
    .map(
      (item) => `
        <article class="event-item">
          <strong>${escapeHtml(item.event_type)}</strong>
          <p>${escapeHtml(item.pig_name)} · ${escapeHtml(item.group_title)}</p>
          <div class="event-item__meta">${escapeHtml(formatDateTime(item.created_at))}</div>
        </article>
      `,
    )
    .join("");
}

function setStatus(text, state) {
  statusPill.textContent = text;
  statusPill.className = `status-pill status-pill--${state}`;
}

function formatDateTime(value) {
  return new Date(value).toLocaleString("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function formatDuration(seconds) {
  const total = Math.max(Number(seconds || 0), 0);
  if (total === 0) {
    return "готово";
  }
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0) {
    return `${hours}ч ${minutes}м`;
  }
  return `${minutes}м`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
