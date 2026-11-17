let api = null;

export function bindGo(next) {
  api = next;
  const board = document.querySelector("#go-board");
  board?.addEventListener("click", (event) => {
    const point = event.target instanceof Element ? event.target.closest(".go-point") : null;
    if (!(point instanceof HTMLButtonElement) || !api) return;
    const state = api.getState();
    if (state.table !== "go" || api.getBusy()) return;
    const col = Number(point.dataset.col);
    const row = Number(point.dataset.row);
    if (state.status === "scoring" && point.dataset.stone === "1") {
      send("mark", { col, row });
      return;
    }
    if (state.your_turn) send("move", { col, row });
  });
  board?.addEventListener("keydown", (event) => {
    const point = event.target instanceof Element ? event.target.closest(".go-point") : null;
    if (!(point instanceof HTMLButtonElement)) return;
    const step = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key];
    if (!step) return;
    event.preventDefault();
    const col = Number(point.dataset.col) + step[0];
    const row = Number(point.dataset.row) + step[1];
    board.querySelector(`[data-col="${col}"][data-row="${row}"]`)?.focus();
  });
}

export function paintGo(state) {
  const scene = document.querySelector("#go-scene");
  if (!scene) return;
  scene.hidden = state.table !== "go";
  if (state.table !== "go") return;
  const active = document.activeElement;
  const kept = active instanceof HTMLElement && active.classList.contains("go-point")
    ? { col: active.dataset.col, row: active.dataset.row }
    : null;
  const meta = document.querySelector("#go-meta");
  if (meta) {
    const side = state.your_side === "black" ? "чёрными" : state.your_side === "white" ? "белыми" : "";
    const who = side ? `Вы играете ${side}` : "Вы наблюдаете";
    meta.textContent = `Доска ${state.size}×${state.size} · ${who} · Коми ${state.komi}`;
  }
  paintPlayer(document.querySelector("#go-far"), state, state.far_color);
  paintPlayer(document.querySelector("#go-near"), state, state.near_color);
  const note = document.querySelector("#go-note");
  if (note) note.textContent = state.notice || "";
  const error = document.querySelector("#go-error");
  if (error) {
    error.hidden = true;
    error.textContent = "";
  }
  paintBoard(state);
  paintActions(state);
  paintScore(state);
  const points = [...document.querySelectorAll("#go-board .go-point")];
  for (const point of points) point.tabIndex = -1;
  const focused = kept
    ? document.querySelector(`#go-board [data-col="${kept.col}"][data-row="${kept.row}"]`)
    : points[0];
  if (focused instanceof HTMLElement) {
    focused.tabIndex = 0;
    if (kept) focused.focus();
  }
}

function faceMark(file, name, cpu) {
  if (cpu) {
    const image = document.createElement("img");
    image.className = "avatar";
    image.alt = "компьютер";
    image.src = "/static/images/computer-avatar.jpg";
    return image;
  }
  if (/^[0-9a-f]{32}\.(jpg|png|webp)$/.test(String(file || ""))) {
    const image = document.createElement("img");
    image.className = "avatar";
    image.alt = "";
    image.src = `/avatars/${file}`;
    return image;
  }
  const span = document.createElement("span");
  const tone = [...String(name || "")].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 6;
  span.className = `avatar tone-${tone}`;
  span.textContent = String(name || "?").slice(0, 1).toUpperCase();
  return span;
}

function paintPlayer(node, state, color) {
  if (!node || (color !== "black" && color !== "white")) return;
  node.replaceChildren();
  const bowl = document.createElement("img");
  bowl.className = "go-bowl";
  bowl.alt = "";
  bowl.src = asset(color === "black" ? "go-bowl-black.png" : "go-bowl-white.png");
  const text = document.createElement("div");
  const title = document.createElement("p");
  title.className = "go-name";
  const name = color === "black" ? state.black_name : state.white_name;
  const file = color === "black" ? state.black_avatar : state.white_avatar;
  const cpu = state.computer_side === color;
  const label = document.createElement("span");
  label.textContent = name || "Ждём соперника";
  if (name) title.append(faceMark(file, name, cpu));
  title.append(label);
  const meta = document.createElement("p");
  meta.className = "quiet";
  const moving = state.status === "active" && state.side_to_move === color ? " · ходит" : "";
  const rank = cpu && state.engine_title ? ` · ${state.engine_title}` : "";
  meta.textContent = `${color === "black" ? "Чёрные" : "Белые"}${rank}${moving} · Взятия: ${state.captures?.[color] ?? 0}`;
  text.append(title, meta);
  node.append(bowl, text);
}

function paintBoard(state) {
  const board = document.querySelector("#go-board");
  if (!board) return;
  const size = Number(state.size);
  board.dataset.size = String(size);
  board.setAttribute("aria-label", `Доска го ${size} на ${size}`);
  board.replaceChildren();
  const layer = document.createElement("img");
  layer.className = "go-layer";
  layer.alt = `Доска го ${size} на ${size}`;
  layer.src = asset(`go-board-${size}.png`);
  const points = document.createElement("div");
  points.className = "go-points";
  const dead = new Set((state.dead || []).map((point) => `${point[0]}:${point[1]}`));
  const legal = new Set((state.legal || []).map((point) => `${point[0]}:${point[1]}`));
  const territory = new Map((state.tally?.territory || []).map((point) => [`${point.col}:${point.row}`, point.owner]));
  const last = state.last?.kind === "move" ? state.last : null;
  const ghost = state.your_turn ? (state.side_to_move === "white" ? "go-stone-white.png" : "go-stone-black.png") : "";
  for (let row = 0; row < size; row += 1) {
    for (let col = 0; col < size; col += 1) {
      const key = `${col}:${row}`;
      const stone = state.board[row * size + col];
      const button = document.createElement("button");
      button.type = "button";
      button.className = "go-point";
      if (dead.has(key)) button.classList.add("is-dead");
      button.dataset.col = String(col);
      button.dataset.row = String(row);
      button.dataset.stone = stone === "0" ? "0" : "1";
      const place = pointStyle(col, row, size);
      button.style.left = place.left;
      button.style.top = place.top;
      button.style.width = place.width;
      button.style.height = place.width;
      const where = `${columnName(col)}${size - row}`;
      if (stone === "1" || stone === "2") {
        const image = document.createElement("img");
        image.className = "go-stone";
        image.alt = "";
        image.src = asset(stone === "1" ? "go-stone-black.png" : "go-stone-white.png");
        button.append(image);
        button.setAttribute("aria-label", `${where}, ${stone === "1" ? "чёрный" : "белый"} камень${dead.has(key) ? ", мёртвая группа" : ""}`);
      } else {
        button.setAttribute("aria-label", `${where}, пусто`);
      }
      if (ghost && stone === "0" && legal.has(key)) {
        const hover = document.createElement("img");
        hover.className = "go-ghost";
        hover.alt = "";
        hover.src = asset(ghost);
        button.append(hover);
      }
      if (last && last.col === col && last.row === row && (stone === "1" || stone === "2")) {
        const mark = document.createElement("img");
        mark.className = "go-last";
        mark.alt = "";
        mark.src = asset(stone === "1" ? "go-last-on-black.svg" : "go-last-on-white.svg");
        button.append(mark);
      }
      const owner = territory.get(key);
      if ((owner === "black" || owner === "white") && stone === "0") {
        const mark = document.createElement("img");
        mark.className = "go-territory";
        mark.alt = "";
        mark.src = asset(owner === "black" ? "go-territory-black.svg" : "go-territory-white.svg");
        button.append(mark);
      }
      points.append(button);
    }
  }
  board.append(layer, points);
}

function paintActions(state) {
  const box = document.querySelector("#go-actions");
  if (!box) return;
  box.replaceChildren();
  if (!state.watching && state.status !== "waiting" && state.status !== "finished") {
    box.append(
      actionButton("Пас", state.can_pass, () => send("pass")),
      actionButton("Сдаться", state.can_resign, () => resign(), true),
    );
  }
  if (!state.watching && state.status === "scoring") {
    box.append(
      actionButton("Подтвердить результат", state.can_agree, () => send("agree")),
      actionButton("Продолжить игру", state.can_resume, () => send("resume")),
    );
  }
  const sgf = document.createElement("a");
  sgf.className = "button secondary";
  sgf.href = `/api/v1/games/${state.id}/export`;
  sgf.textContent = "Сохранить SGF";
  const rules = document.createElement("a");
  rules.className = "button secondary";
  rules.href = "/rules#go";
  rules.textContent = "Правила";
  box.append(sgf, rules);
}

function paintScore(state) {
  const panel = document.querySelector("#go-score");
  if (!panel) return;
  const show = state.tally && (state.status === "scoring" || state.result_reason === "score");
  panel.hidden = !show;
  if (!show || !state.tally) return;
  const score = state.tally;
  panel.replaceChildren();
  if (state.status === "scoring") {
    const lead = document.createElement("p");
    lead.textContent = "Отметьте мёртвые группы и подтвердите результат. При разногласии продолжите игру.";
    panel.append(lead);
  }
  const list = document.createElement("dl");
  list.className = "go-tally";
  addScore(list, "Чёрные живые", score.black_alive);
  addScore(list, "Чёрная территория", score.black_territory);
  addScore(list, "Чёрные всего", score.black_text);
  addScore(list, "Белые живые", score.white_alive);
  addScore(list, "Белая территория", score.white_territory);
  addScore(list, "Коми", score.komi);
  addScore(list, "Белые всего", score.white_text);
  addScore(list, "Нейтральные", score.neutral);
  panel.append(list);
  const lead = document.createElement("p");
  lead.textContent = state.status === "finished"
    ? (state.result_message || score.lead)
    : score.lead;
  panel.append(lead);
  const agree = document.createElement("p");
  agree.className = "quiet";
  agree.textContent = `Чёрные ${score.black_agreed ? "подтвердили" : "ещё не подтвердили"}. Белые ${score.white_agreed ? "подтвердили" : "ещё не подтвердили"}. Взятия в этот счёт не входят: чёрные сняли ${score.black_captures}, белые сняли ${score.white_captures}.`;
  panel.append(agree);
}

function addScore(list, name, value) {
  const title = document.createElement("dt");
  title.textContent = name;
  const number = document.createElement("dd");
  number.textContent = String(value);
  list.append(title, number);
}

function actionButton(label, enabled, onClick, danger = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = danger ? "is-danger" : "secondary";
  button.textContent = label;
  button.disabled = !enabled || api?.getBusy();
  button.addEventListener("click", onClick);
  return button;
}

async function resign() {
  if (!api || api.getBusy()) return;
  const accepted = await api.ask({
    title: "Сдаться",
    text: "Победа будет засчитана сопернику. Это нельзя отменить.",
    accept: "Сдаться",
    tone: "danger",
  });
  if (accepted) send("resign");
}

async function send(action, extra = {}) {
  if (!api || api.getBusy()) return;
  const state = api.getState();
  api.setBusy(true);
  paintGo(api.getState());
  let note = "";
  try {
    const data = await api.post(`/api/v1/games/${state.id}/go`, {
      command_id: crypto.randomUUID(),
      version: state.version,
      action,
      ...extra,
    });
    await api.apply(data);
  } catch (error) {
    note = error instanceof Error ? error.message : "Запрос не выполнен.";
    try {
      await api.refresh();
    } catch {
      const link = document.querySelector("#go-link");
      if (link) link.textContent = "Нет связи. Ждём снимок партии.";
    }
  } finally {
    api.setBusy(false);
    paintGo(api.getState());
    if (note) {
      api.say(note);
      const error = document.querySelector("#go-error");
      if (error) {
        error.hidden = false;
        error.textContent = note;
      }
    }
    api.onSettled?.();
  }
}

function pointStyle(col, row, size) {
  const step = 864 / (size - 1);
  return {
    left: `${((80 + col * step) / 1024) * 100}%`,
    top: `${((80 + row * step) / 1024) * 100}%`,
    width: `${(step / 1024) * 100}%`,
  };
}

function columnName(col) {
  return String.fromCharCode(col < 8 ? 65 + col : 66 + col);
}

function asset(name) {
  return `/static/images/go/${name}`;
}
