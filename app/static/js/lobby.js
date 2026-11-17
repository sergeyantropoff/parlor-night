import { attachPager } from "./pager.js";

const root = document.querySelector("[data-room='lobby']");
if (root) {
  const seekFilter = root.querySelector("#seek-filter");
  const seekEmpty = root.querySelector("#seek-empty");
  const seekList = root.querySelector(".seek-list");
  let seekGame = seekFilter?.value || "all";
  const paintSeekers = seekList
    ? attachPager(seekList, {
      size: 6,
      label: "Страницы вызовов",
      match: (row) => seekGame === "all" || row.dataset.seek === seekGame,
    })
    : null;

  const refreshSeekers = (reset = false) => {
    const state = paintSeekers ? paintSeekers({ reset }) : { count: 0 };
    if (seekEmpty) {
      seekEmpty.hidden = state.count > 0;
      seekEmpty.textContent = seekGame === "all" ? seekEmpty.dataset.base : "Сейчас никто не ищет этот стол.";
    }
  };

  if (seekEmpty) seekEmpty.dataset.base = seekEmpty.textContent.trim();
  seekFilter?.addEventListener("change", () => {
    seekGame = seekFilter.value || "all";
    refreshSeekers(true);
  });
  if (paintSeekers) refreshSeekers();

  const guestSearch = root.querySelector("#guest-search");
  const guestEmpty = root.querySelector("#guest-empty");
  const guestList = root.querySelector("#guest-list");
  const paintGuests = guestList
    ? attachPager(guestList, {
      size: 8,
      label: "Страницы гостей",
      match: (row) => {
        const term = (guestSearch?.value || "").trim().toLowerCase();
        return !term || (row.dataset.guest || "").includes(term);
      },
    })
    : null;

  const refreshGuests = (reset = false) => {
    const state = paintGuests ? paintGuests({ reset }) : { count: 1 };
    if (guestEmpty) guestEmpty.hidden = state.count > 0;
  };

  guestSearch?.addEventListener("input", () => refreshGuests(true));
  if (paintGuests) refreshGuests();

  const seekGameSelect = root.querySelector("#seek-game");
  const seekSeats = root.querySelector("#seek-seats");
  const seatInputs = [...root.querySelectorAll("[data-seat]")];

  const syncSeats = () => {
    const option = seekGameSelect?.selectedOptions?.[0];
    const min = Number(option?.dataset.min || 2);
    const max = Number(option?.dataset.max || 2);
    if (seekSeats) seekSeats.hidden = min === max;
    let chosen = false;
    for (const input of seatInputs) {
      const count = Number(input.dataset.seat);
      const on = count >= min && count <= max;
      input.disabled = !on;
      const label = input.closest("label");
      if (label) label.hidden = !on;
      if (on && input.checked) chosen = true;
    }
    if (!chosen) {
      const fallback = seatInputs.find((input) => !input.disabled);
      if (fallback) fallback.checked = true;
    }
  };

  seekGameSelect?.addEventListener("change", () => {
    const next = seekGameSelect.value;
    for (const mark of root.querySelectorAll("[data-seek-mark]")) {
      if (mark instanceof HTMLImageElement) mark.src = mark.src.replace(/game-[a-z]+-/, `game-${next}-`);
    }
    syncSeats();
  });
  syncSeats();
}
