const tg = window.Telegram?.WebApp;
const statusPill = document.getElementById("status-pill");
const viewerName = document.getElementById("viewer-name");
const generatedAt = document.getElementById("generated-at");
const refreshButton = document.getElementById("refresh-button");

const overviewGrid = document.getElementById("overview-grid");
const worldEvents = document.getElementById("world-events");
const topPigs = document.getElementById("top-pigs");
const groupsTable = document.getElementById("groups-table");
const recentBattles = document.getElementById("recent-battles");
const recentRaids = document.getElementById("recent-raids");
const recentEvents = document.getElementById("recent-events");

const overviewLabels = [
  ["groups", "Группы", "Активные Telegram-чаты с игрой"],
  ["users", "Игроки", "Уникальные Telegram-пользователи"],
  ["pigs", "Свиньи", "Всего созданных игровых профилей"],
  ["battles", "Бои", "История завершённых матчей"],
  ["raids", "Рейды", "Запуски вылазок по всем группам"],
  ["battle_ready_pigs", "На арене", "Свиньи, которые прямо сейчас ищут драку"],
  ["active_raids", "В рейде", "Активные вылазки в текущий момент"],
  ["active_world_events", "Мировые события", "События, влияющие на игровой баланс сейчас"],
];

let isLoading = false;

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
  if (isLoading) {
    return;
  }
  isLoading = true;
  setStatus("Загрузка", "loading");

  try {
    const initData = tg?.initData ?? "";
    if (!initData) {
      throw new Error("Открой mini app из Telegram, чтобы передать авторизацию.");
    }

    const response = await fetch("/admin/api/dashboard", {
      headers: {
        "X-Telegram-Init-Data": initData,
      },
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Не удалось загрузить дашборд.");
    }

    renderDashboard(payload);
    setStatus("Live", "live");
  } catch (error) {
    const message = error instanceof Error ? error.message : "Неизвестная ошибка загрузки.";
    renderError(message);
    setStatus("Ошибка", "error");
  } finally {
    isLoading = false;
  }
}

function renderDashboard(payload) {
  const viewer = payload.viewer;
  const label = viewer.username ? `@${viewer.username}` : [viewer.first_name, viewer.last_name].filter(Boolean).join(" ");
  viewerName.textContent = label || String(viewer.id);
  generatedAt.textContent = formatDateTime(payload.generated_at);

  overviewGrid.innerHTML = overviewLabels
    .map(([key, title, hint]) => {
      const value = Number(payload.overview[key] ?? 0);
      return `
        <article class="metric-card">
          <span class="metric-card__label">${escapeHtml(title)}</span>
          <strong class="metric-card__value">${value.toLocaleString("ru-RU")}</strong>
          <span class="metric-card__hint">${escapeHtml(hint)}</span>
        </article>
      `;
    })
    .join("");

  worldEvents.innerHTML = renderWorldEvents(payload.active_world_events);
  topPigs.innerHTML = renderTopPigs(payload.top_pigs);
  groupsTable.innerHTML = renderGroups(payload.groups);
  recentBattles.innerHTML = renderBattleFeed(payload.recent_battles);
  recentRaids.innerHTML = renderRaidFeed(payload.recent_raids);
  recentEvents.innerHTML = renderEventFeed(payload.recent_events);
}

function renderError(message) {
  viewerName.textContent = "Нет сессии";
  generatedAt.textContent = "Нет данных";
  const state = `<div class="empty-state">${escapeHtml(message)}</div>`;
  overviewGrid.innerHTML = state;
  worldEvents.innerHTML = state;
  topPigs.innerHTML = state;
  groupsTable.innerHTML = state;
  recentBattles.innerHTML = state;
  recentRaids.innerHTML = state;
  recentEvents.innerHTML = state;
}

function renderWorldEvents(items) {
  if (!items.length) {
    return `<div class="empty-state">Сейчас нет активных мировых событий.</div>`;
  }
  return items
    .map(
      (item) => `
        <article class="event-card">
          <h3>${escapeHtml(item.title)}</h3>
          <p>${escapeHtml(item.description)}</p>
          <div class="event-card__meta">
            <span class="chip">${escapeHtml(item.event_code)}</span>
            <span>До ${escapeHtml(formatDateTime(item.ends_at))}</span>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderTopPigs(items) {
  if (!items.length) {
    return `<div class="empty-state">Лидерборд пока пуст.</div>`;
  }
  return `
    <table>
      <thead>
        <tr>
          <th>Свинья</th>
          <th>Вес</th>
          <th>Владелец</th>
          <th>Группа</th>
          <th>Бои</th>
          <th>Статус</th>
        </tr>
      </thead>
      <tbody>
        ${items
          .map(
            (item) => `
              <tr>
                <td>
                  <strong>${escapeHtml(item.pig_name)}</strong>
                  <span class="subtext">${escapeHtml(item.trait)}</span>
                </td>
                <td>${escapeHtml(item.weight_kg)} кг</td>
                <td>${escapeHtml(item.owner_name)}</td>
                <td>${escapeHtml(item.group_title)}</td>
                <td>${item.wins}/${item.losses}</td>
                <td>${escapeHtml(item.status)}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderGroups(items) {
  if (!items.length) {
    return `<div class="empty-state">Группы ещё не подключались к боту.</div>`;
  }
  return `
    <table>
      <thead>
        <tr>
          <th>Группа</th>
          <th>Свиньи</th>
          <th>Средний вес</th>
          <th>Арена / рейды</th>
          <th>Активность</th>
          <th>Топ-свинья</th>
        </tr>
      </thead>
      <tbody>
        ${items
          .map(
            (item) => `
              <tr>
                <td>
                  <strong>${escapeHtml(item.title)}</strong>
                  <span class="subtext">${escapeHtml(String(item.telegram_group_id))}</span>
                </td>
                <td>${Number(item.pig_count).toLocaleString("ru-RU")}</td>
                <td>${item.avg_weight_kg ? `${escapeHtml(item.avg_weight_kg)} кг` : "—"}</td>
                <td>${Number(item.ready_count)} / ${Number(item.raiding_count)}</td>
                <td>
                  <strong>${Number(item.battle_count)} боёв</strong>
                  <span class="subtext">${item.last_activity_at ? escapeHtml(formatDateTime(item.last_activity_at)) : "Пока тихо"}</span>
                </td>
                <td>
                  ${item.top_pig_name ? `<strong>${escapeHtml(item.top_pig_name)}</strong>` : "—"}
                  ${item.top_pig_weight_kg ? `<span class="subtext">${escapeHtml(item.top_pig_weight_kg)} кг</span>` : ""}
                </td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderBattleFeed(items) {
  if (!items.length) {
    return `<div class="empty-state">Бои ещё не проводились.</div>`;
  }
  return items
    .map(
      (item) => `
        <article class="feed-item">
          <strong>${escapeHtml(item.pig1_name)} vs ${escapeHtml(item.pig2_name)}</strong>
          <p>Победитель: ${escapeHtml(item.winner_name || "не определён")}.</p>
          <div class="feed-item__meta">
            <span>${escapeHtml(item.group_title)}</span>
            <span>${escapeHtml(formatDateTime(item.created_at))}</span>
            <span>+${escapeHtml(item.winner_gain_kg)} / -${escapeHtml(item.loser_loss_kg)} кг</span>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderRaidFeed(items) {
  if (!items.length) {
    return `<div class="empty-state">Рейдов ещё не было.</div>`;
  }
  return items
    .map(
      (item) => `
        <article class="feed-item">
          <strong>${escapeHtml(item.pig_name)} → ${escapeHtml(item.destination)}</strong>
          <p>${escapeHtml(item.group_title)}</p>
          <div class="feed-item__meta">
            <span>${escapeHtml(item.status)}</span>
            <span>${escapeHtml(formatDateTime(item.started_at))}</span>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderEventFeed(items) {
  if (!items.length) {
    return `<div class="empty-state">Событий пока нет.</div>`;
  }
  return items
    .map(
      (item) => `
        <article class="feed-item">
          <strong>${escapeHtml(item.event_type)}</strong>
          <p>${escapeHtml(item.pig_name)} в группе ${escapeHtml(item.group_title)}</p>
          <div class="feed-item__meta">
            <span>${escapeHtml(formatDateTime(item.created_at))}</span>
          </div>
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
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
