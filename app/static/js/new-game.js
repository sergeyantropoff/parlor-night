function clampCount(input, min, max, fallback) {
  if (!input) return fallback;
  const raw = input.value.trim();
  if (raw === "") return fallback;
  const value = Math.trunc(Number(raw));
  if (!Number.isFinite(value)) return fallback;
  const next = Math.max(min, Math.min(max, value));
  if (String(next) !== raw) input.value = String(next);
  return next;
}

const form = document.querySelector("#new-game");
if (form) {
  const boardOnly = new Set(["free", "analysis", "lesson"]);
  const byId = (id) => document.querySelector(id);

  function checked(name) {
    return form.querySelector(`input[name="${name}"]:checked`);
  }

  function sync(openLesson) {
    const game = checked("game_type") || form.querySelector('input[name="game_type"]');
    const gameValue = game?.value || "chess";
    const cards = ["uno", "poker", "durak", "blackjack", "preferans"].includes(gameValue);
    const poker = gameValue === "poker";
    const durak = gameValue === "durak";
    const blackjack = gameValue === "blackjack";
    const preferans = gameValue === "preferans";
    const grown = poker || blackjack || preferans;
    const checkers = gameValue === "checkers";
    const go = gameValue === "go";
    form.dataset.game = gameValue;

    for (const input of form.querySelectorAll('input[name="mode"]')) {
      const off = (cards || go) && boardOnly.has(input.value);
      input.disabled = off;
      input.closest("label").hidden = off;
      if (off) input.checked = false;
    }
    if (![...form.querySelectorAll('input[name="mode"]')].some((input) => input.checked)) {
      const fallback = form.querySelector('input[name="mode"][value="vs_computer"]');
      if (fallback) fallback.checked = true;
    }

    const mode = checked("mode");
    const modeValue = mode?.value || "vs_computer";
    const online = modeValue === "online";
    const shareable = online || modeValue === "vs_computer";
    byId("#table-setup").hidden = false;
    byId("#side-fields").hidden = cards;
    byId("#card-seats").hidden = !cards;
    const computerInput = form.querySelector("#computers");
    const openInput = form.querySelector("#open-seats");
    const seatFloor = preferans ? 2 : blackjack ? 0 : 1;
    const seatCap = preferans ? 2 : 5;
    if (cards && computerInput && openInput && form.dataset.seatGame !== gameValue) {
      form.dataset.seatGame = gameValue;
      if (preferans) {
        computerInput.value = "2";
        openInput.value = "0";
      } else if (blackjack) {
        computerInput.value = "0";
        openInput.value = "0";
      } else {
        computerInput.value = "1";
        openInput.value = "0";
      }
    }
    const computers = clampCount(computerInput, 0, seatCap, preferans ? 2 : blackjack ? 0 : 1);
    let openMax = Math.max(0, seatCap - computers);
    if (preferans) openMax = Math.max(0, 2 - computers);
    if (openInput) openInput.max = String(cards ? openMax : 5);
    let openSeats = clampCount(openInput, 0, cards ? openMax : 5, 0);
    if (cards && computers + openSeats < seatFloor && openInput) {
      openSeats = clampCount(openInput, seatFloor - computers, openMax, seatFloor - computers);
    }
    const seatNote = byId("#seat-note");
    if (cards) {
      const wanted = openSeats > 0 ? "online" : "vs_computer";
      const picked = form.querySelector(`input[name="mode"][value="${wanted}"]`);
      if (picked) picked.checked = true;
      const total = computers + openSeats;
      const room = preferans ? "В преферансе трое: вы и ещё двое." : blackjack ? "Дилер играет за дом. Другие места — игроки за тем же столом." : `Свободных для людей — не больше ${openMax}: вместе с вами стол на шесть.`;
      const limit = room;
      if (seatNote) {
        const missing = seatFloor - total;
        seatNote.textContent = missing > 0
          ? `Нужно ещё ${missing} ${missing === 1 ? "место" : "места"} кроме вас. ${limit}`
          : blackjack && total === 0
            ? limit
            : openSeats
              ? `${computers ? `${computers} комп. · ` : ""}${openSeats} св. мест. Люди садятся по коду или, если стол открыт, кнопкой «Сесть». ${limit}`
              : computers === 1
                ? `Один компьютер отвечает за другую сторону. ${limit}`
                : `Компьютеров за столом: ${computers}. ${limit}`;
      }
    }
    if (go) {
      for (const name of ["initial_fen", "pgn", "initial_position", "moves"]) {
        const field = form.querySelector(`[name="${name}"]`);
        if (field) field.value = "";
      }
    }
    const modeNow = checked("mode");
    const onlineNow = (modeNow?.value || modeValue) === "online";
    byId("#play-mode").hidden = cards;
    byId("#engine-fields").hidden = blackjack ? false : cards ? computers < 1 : onlineNow;
    const levelLabel = byId("#engine-level-label");
    if (levelLabel) {
      levelLabel.textContent = cards && computers > 1
        ? "Сила всех компьютеров за столом"
        : "Сила игры";
    }
    const shareableNow = cards || shareable;
    byId("#audience-fields").hidden = !shareableNow;
    const note = byId("#online-note");
    if (note && !note.dataset.base) note.dataset.base = note.textContent;
    if (note) {
      note.hidden = cards ? openSeats < 1 : !onlineNow;
      note.textContent = go && onlineNow
        ? "После создания появится код для второго игрока. Часов на партию нет."
        : cards && openSeats > 0
          ? "Свободные места занимают люди: по коду со страницы стола или кнопкой «Сесть», если стол открыт."
          : note.dataset.base;
    }
    byId("#adult-note").hidden = !grown;
    const durakKind = byId("#durak-kind");
    if (durakKind) durakKind.hidden = !durak;
    const poolPanel = byId("#preferans-pool");
    if (poolPanel) poolPanel.hidden = !preferans;
    const goSize = byId("#go-size");
    if (goSize) goSize.hidden = !go;
    const whiteInput = form.querySelector('input[name="player_side"][value="white"]');
    const blackInput = form.querySelector('input[name="player_side"][value="black"]');
    const whiteSmall = whiteInput?.closest("label")?.querySelector("small");
    const blackSmall = blackInput?.closest("label")?.querySelector("small");
    if (whiteSmall && blackSmall) {
      whiteSmall.textContent = go ? "Ходят вторыми" : "Снизу, ходят первыми";
      blackSmall.textContent = go ? "Ходят первыми" : "Снизу, отвечают на ход";
    }
    if (whiteInput && blackInput) {
      whiteInput.dataset.title = go ? "Белые" : "Белые снизу";
      blackInput.dataset.title = go ? "Чёрные" : "Чёрные снизу";
    }
    byId("#fen-field").hidden = gameValue !== "chess";
    byId("#pgn-field").hidden = gameValue !== "chess";
    byId("#rcp-field").hidden = !checkers;
    byId("#moves-field").hidden = cards;
    const advanced = byId("#advanced");
    advanced.hidden = cards || go;

    const hint = byId("#moves-hint");
    const moves = byId("#moves-field")?.querySelector("textarea");
    if (hint) {
      hint.textContent = checkers
        ? "Ходы шашек, по одному в строке: 22-18 или 21:14:7"
        : "Ходы шахмат в UCI, по одному в строке";
    }
    if (moves) moves.placeholder = checkers ? "22-18" : "e2e4";

    const levelValue = Number(checked("engine_level")?.value || 3);
    for (const input of form.querySelectorAll('input[name="engine_level"]')) {
      const step = input.closest("label");
      const n = Number(input.value);
      step.classList.toggle("is-hot", n <= levelValue);
      step.classList.toggle("is-on", n === levelValue);
    }
    const fill = byId("#meter-fill");
    if (fill) fill.style.width = `${((levelValue - 1) / 4) * 80}%`;

    const parts = [game?.dataset.title];
    if (cards) {
      if (durak) parts.push(checked("durak_kind")?.dataset.title);
      if (preferans) parts.push(checked("pool")?.dataset.title);
      if (computers) parts.push(`компьютеров: ${computers}`);
      if (openSeats) parts.push(`свободных мест: ${openSeats}`);
      if (computers || blackjack) parts.push(checked("engine_level")?.dataset.title);
      parts.push(checked("audience")?.dataset.title);
    } else {
      parts.push(modeNow?.dataset.title, checked("player_side")?.dataset.title);
      if (go) parts.push(checked("board_size")?.dataset.title);
      if (!onlineNow) parts.push(checked("engine_level")?.dataset.title);
      if (shareableNow) parts.push(checked("audience")?.dataset.title);
    }
    const summary = byId("#setup-summary");
    if (summary) summary.textContent = parts.filter(Boolean).join(" · ");

    if (openLesson && modeValue === "lesson" && !cards) {
      advanced.hidden = false;
      advanced.open = true;
      const field = checkers ? byId("#rcp-field") : byId("#pgn-field");
      field?.querySelector("textarea")?.focus();
    }
  }

  form.addEventListener("input", () => sync(false));
  form.addEventListener("change", (event) => {
    sync(event.target?.name === "mode");
  });
  sync(false);
}
