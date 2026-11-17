import { pokerFace, svgDataUrl, unoFace } from "./cards.mjs";
import { attachPager } from "./pager.js";
import { bindGo, paintGo } from "./go.js";

const source = document.querySelector("#game-state");
let current = JSON.parse(source.textContent);
let prefix = [];
let hintPath = [];
let preview = null;
let captureFocus = null;
let busy = false;
let wildOpen = false;
let bidLevel = "";
let unoArmed = false;
let guestTurned = false;
let moveChain = Promise.resolve();
let skipClick = false;
let cursor = 0;
const board = document.querySelector("#board");
const status = document.querySelector("#status");
const history = document.querySelector("#history");
const lines = document.querySelector("#lines");
const dialog = document.querySelector("#promotion");
const files = "abcdefgh";

function token() {
  return document.querySelector('meta[name="csrf-token"]').content;
}

function say(text) {
  status.textContent = text;
  status.dataset.hint = text;
  const advice = document.querySelector("#table-advice");
  if (advice) paintWinnerLine(advice, text);
  const tone = current.status === "finished" && text === current.status_line ? current.result_tone : "";
  status.classList.toggle("is-you", !tone && text.includes("Ваш ход"));
  status.classList.toggle("is-win", tone === "win");
  status.classList.toggle("is-loss", tone === "loss");
  status.classList.toggle("is-draw", tone === "draw");
  status.classList.toggle("is-stop", tone === "stop");
}

async function post(url, body) {
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRF-Token": token(),
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("Сетевая ошибка. Проверьте соединение и повторите действие.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error?.message || "Запрос не выполнен.");
  }
  return data;
}

function pieceSrc(piece, color) {
  const version = new URL(import.meta.url).searchParams.get("v");
  const side = color === "white" ? "w" : "b";
  const name = current.game_type === "checkers"
    ? `checkers-${side}-${piece === "K" ? "king" : "man"}`
    : `chess-${side}-${String(piece).toLowerCase()}`;
  const file = `/static/images/pieces/${name}.png`;
  return version ? `${file}?v=${version}` : file;
}

function pieceSvg(piece, color) {
  if (current.game_type === "chess" || current.game_type === "checkers") {
    const img = document.createElement("img");
    img.className = "piece piece-img";
    img.alt = "";
    img.draggable = false;
    img.src = pieceSrc(piece, color);
    return img;
  }
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 40 40");
  svg.setAttribute("class", "piece");
  const fill = color === "white" ? "#f8f4ea" : "#1b1b1b";
  const stroke = color === "white" ? "#222" : "#f8f4ea";
  const add = (name, attrs) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    svg.append(node);
  };
  if (piece === "M") {
    add("circle", { cx: "20", cy: "20", r: "12", fill, stroke, "stroke-width": "2" });
  } else if (piece === "K" && current.game_type === "checkers") {
    add("circle", { cx: "20", cy: "22", r: "12", fill, stroke, "stroke-width": "2" });
    add("path", { d: "M12 14h16l-3 6H15z", fill: "#c4a35a", stroke, "stroke-width": "1" });
  } else {
    add("circle", { cx: "20", cy: "24", r: "10", fill, stroke, "stroke-width": "2" });
    const marks = { P: "M20 8a5 5 0 1 1 0 10a5 5 0 0 1 0-10", R: "M10 10h20v6h-4v-3h-3v3h-6v-3h-3v3h-4z", N: "M12 28l6-16 4 4-3 12z", B: "M20 6l8 20H12z", Q: "M8 16h24l-3 12H11z", K: "M18 6h4v6h6v4h-6v6h-4v-6h-6v-4h6z" };
    add("path", { d: marks[piece] || marks.P, fill, stroke, "stroke-width": "2" });
  }
  return svg;
}

function seatLabel(side) {
  const raw = side === "black" ? current.black_name : current.white_name;
  if (!raw) return null;
  const mine = current.your_side === side;
  const cpu = current.computer_side === side;
  const text = mine
    ? `${raw} · вы`
    : cpu && current.engine_title
      ? `${raw} · ${current.engine_title}`
      : raw;
  return {
    text,
    raw,
    cpu,
    letter: raw.slice(0, 1).toUpperCase(),
    tone: toneOf(raw),
    login: side === "black" ? current.black_login : current.white_login,
    avatar: side === "black" ? current.black_avatar : current.white_avatar,
  };
}

function fillSeat(id, seat) {
  const node = document.querySelector(id);
  if (!node) return;
  node.replaceChildren();
  if (!seat) {
    node.hidden = true;
    return;
  }
  node.hidden = false;
  const name = document.createElement("span");
  fillPersonName(name, { name: seat.text, login: seat.login });
  node.append(seat.cpu ? cpuAvatar() : avatarChip(seat.raw || seat.text, seat.avatar), name);
}

function paintSeats() {
  const hint = document.querySelector("#hint");
  if (current.table === "go") {
    const near = document.querySelector("#near-seat");
    const far = document.querySelector("#far-seat");
    if (near) near.hidden = true;
    if (far) far.hidden = true;
    if (hint) hint.hidden = true;
    return;
  }
  if (current.table === "cards") {
    if (hint) hint.hidden = true;
    return;
  }
  hint?.remove();
  const bottomSide = current.black_at_bottom ? "black" : "white";
  const topSide = current.black_at_bottom ? "white" : "black";
  let bottom = seatLabel(bottomSide);
  const top = seatLabel(topSide);
  if (!bottom && !top && current.you_name) {
    bottom = {
      text: `${current.you_name} · вы`,
      raw: current.you_name,
      letter: current.you_name.slice(0, 1).toUpperCase(),
      tone: toneOf(current.you_name),
      login: current.login,
      avatar: current.avatar,
    };
  }
  fillSeat("#near-seat", bottom);
  fillSeat("#far-seat", top);
  if (!hint) return;
  const mineOnTop = current.your_side ? current.your_side === topSide : false;
  const host = document.querySelector(mineOnTop ? "#far-seat" : "#near-seat");
  if (host && !host.hidden) host.append(hint);
  else document.querySelector(".stage")?.append(hint);
}

function rows() {
  const black = current.black_at_bottom;
  const ranks = black ? [0, 1, 2, 3, 4, 5, 6, 7] : [7, 6, 5, 4, 3, 2, 1, 0];
  const fileOrder = black ? [7, 6, 5, 4, 3, 2, 1, 0] : [0, 1, 2, 3, 4, 5, 6, 7];
  return ranks.map((rank) => fileOrder.map((file) => current.cells.find((cell) => cell.file === file && cell.rank === rank)));
}

function targets() {
  if (!prefix.length) return new Set();
  const next = new Set();
  for (const move of current.legal_moves) {
    if (prefix.every((square, index) => move.path[index] === square)) {
      const square = move.path[prefix.length];
      if (square) next.add(square);
    }
  }
  return next;
}

function cellBy(square, cells = current.cells) {
  return (cells || []).find((cell) => cell.square === String(square));
}

function between(from, to, cells = current.cells) {
  const start = cellBy(from, cells);
  const end = cellBy(to, cells);
  if (!start || !end) return [];
  const rankDelta = end.rank - start.rank;
  const fileDelta = end.file - start.file;
  const steps = Math.max(Math.abs(rankDelta), Math.abs(fileDelta));
  if (steps < 2 || Math.abs(rankDelta) !== Math.abs(fileDelta)) return [];
  const rankStep = rankDelta / steps;
  const fileStep = fileDelta / steps;
  const crossed = [];
  for (let index = 1; index < steps; index += 1) {
    const cell = (cells || []).find((item) => item.rank === start.rank + rankStep * index && item.file === start.file + fileStep * index);
    if (cell) crossed.push(cell);
  }
  return crossed;
}

function nextSteps() {
  if (!prefix.length || current.game_type !== "checkers") return [];
  const from = prefix[prefix.length - 1];
  const steps = [];
  for (const move of current.legal_moves || []) {
    if (!prefix.every((square, index) => move.path[index] === square)) continue;
    const landing = move.path[prefix.length];
    if (!landing) continue;
    steps.push({
      landing,
      victims: between(from, landing).filter((cell) => cell.piece).map((cell) => cell.square),
    });
  }
  if (!captureFocus) return steps;
  const narrowed = steps.filter((step) => step.victims.includes(captureFocus));
  return narrowed.length ? narrowed : steps;
}

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function asset(file) {
  const version = new URL(import.meta.url).searchParams.get("v");
  return version ? `${file}?v=${version}` : file;
}

function moveButton(move, index) {
  const control = document.createElement("button");
  control.type = "button";
  control.className = "move";
  if (preview === index) control.classList.add("is-on");
  control.textContent = move.algebraic || move.notation;
  control.addEventListener("click", () => {
    preview = index;
    say(`Просмотр хода ${index + 1}. Нажмите «Продолжить», чтобы вернуться.`);
  });
  return control;
}

let historyPager = null;

function paintHistory() {
  history.replaceChildren();
  for (let index = 0; index < current.moves.length; index += 2) {
    const row = document.createElement("li");
    row.className = "move-row";
    row.dataset.pageRow = "1";
    const number = document.createElement("span");
    number.className = "move-num";
    number.textContent = `${index / 2 + 1}.`;
    row.append(number, moveButton(current.moves[index], index));
    if (current.moves[index + 1]) row.append(moveButton(current.moves[index + 1], index + 1));
    history.append(row);
  }
  if (!historyPager) historyPager = attachPager(history, { size: 12, newest: true, label: "Страницы ходов" });
  historyPager();
}

function paintChrome() {
  const frame = document.querySelector(".board-frame");
  const cardTable = document.querySelector("#card-table");
  const cards = current.table === "cards";
  const go = current.table === "go";
  if (frame) frame.hidden = cards || go;
  if (cardTable) cardTable.hidden = !cards;
  const scene = document.querySelector("#go-scene");
  if (scene) scene.hidden = !go;
  const keys = document.querySelector(".table-core .keys");
  if (keys) keys.hidden = cards || go;
  const flip = document.querySelector("#flip");
  if (flip) flip.hidden = cards || go;
  const hint = document.querySelector("#hint");
  if (hint) hint.hidden = current.table === "cards" || !current.can_hint;
  const invite = document.querySelector("#invite");
  if (invite) invite.hidden = inviteDismissed() || !current.join_code;
  paintSeats();
  const seatName = document.querySelector("#seat-name");
  if (seatName) {
    const crowd = Array.isArray(current.seats) && current.seats.length > 2;
    seatName.textContent = current.opponent_name || (crowd ? "Другие игроки" : "Соперник");
  }
  const seatAvatar = document.querySelector("#seat-avatar");
  if (seatAvatar && current.opponent_name) {
    seatAvatar.textContent = current.opponent_name.slice(0, 1).toUpperCase();
  }
  const engine = document.querySelector("#engine-move");
  if (engine) engine.disabled = !current.can_engine || busy;
  const end = document.querySelector("#end-game");
  const canEnd = (current.status === "active" || current.status === "scoring") && !current.watching && !busy;
  if (end) end.hidden = !canEnd;
  const stop = document.querySelector("#stop-game");
  if (stop) stop.hidden = !current.can_stop || busy;
  const undo = document.querySelector("#undo");
  if (undo) {
    undo.disabled = !current.can_undo || busy;
    undo.hidden = current.table === "go";
  }
  paintWatchTools();
  paintWatchers();
  if (!preview && hintPath.length === 0 && !captureFocus) say(current.status_line);
  paintWinnerLine(status, status.textContent || "");
  paintRematch();
  paintSummary();
}

function paintWatchTools() {
  const watching = Boolean(current.watching);
  for (const tool of document.querySelectorAll(".tool-col .icon-tool")) {
    if (watching && !tool.querySelector("#flip")) tool.hidden = true;
  }
  for (const column of document.querySelectorAll(".tool-col")) {
    const visible = [...column.querySelectorAll(".icon-tool")].some((tool) => {
      if (tool.hidden) return false;
      const control = tool.querySelector("button, a");
      return control ? !control.hidden : true;
    });
    column.classList.toggle("is-quiet", watching && !visible);
  }
}

function watcherKey(people) {
  return (Array.isArray(people) ? people : [])
    .map((person) => `${person.username || ""}:${person.self ? 1 : 0}`)
    .join("|");
}

function watcherTone(value) {
  return [...String(value || "")].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 6;
}

function watcherLink(person) {
  const link = document.createElement("a");
  link.className = "person-link";
  link.href = `/players/${encodeURIComponent(person.username || "")}`;
  const face = person.avatar
    ? document.createElement("img")
    : document.createElement("span");
  face.className = "avatar";
  if (person.avatar) {
    face.src = `/avatars/${person.avatar}`;
    face.alt = "";
  } else {
    face.classList.add(`tone-${watcherTone(person.name || person.username)}`);
    face.textContent = String(person.name || person.username || "?").slice(0, 1).toUpperCase();
  }
  const copy = document.createElement("span");
  copy.className = "person-copy";
  const name = document.createElement("strong");
  name.textContent = person.name || person.username || "";
  copy.append(name);
  if (person.self) {
    const mark = document.createElement("span");
    mark.className = "watcher-you";
    mark.textContent = " · вы";
    copy.append(mark);
  }
  link.append(face, copy);
  return link;
}

let watcherPager = null;

function paintWatchers() {
  const badge = document.querySelector("#watchers");
  if (!badge) return;
  const people = Array.isArray(current.watchers) ? current.watchers : [];
  const open = current.audience === "open" && (current.mode === "online" || current.mode === "vs_computer");
  badge.hidden = !open;
  const count = document.querySelector("#watcher-count");
  if (count) count.textContent = String(people.length);
  const list = document.querySelector("#watcher-list");
  const empty = document.querySelector("#watcher-empty");
  if (list) {
    list.replaceChildren(...people.map((person) => {
      const item = document.createElement("li");
      item.dataset.pageRow = "1";
      item.append(watcherLink(person));
      return item;
    }));
    if (!watcherPager) watcherPager = attachPager(list, { size: 8, label: "Страницы наблюдателей" });
    watcherPager();
  }
  if (empty) empty.hidden = people.length > 0;
}

function ranksButton() {
  const help = document.createElement("button");
  help.type = "button";
  help.setAttribute("aria-label", "Комбинации");
  help.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-info"/></svg><span>Комбинации</span>`;
  help.addEventListener("click", () => document.querySelector("#poker-ranks")?.showModal());
  return anchor(help, 100, 100, "ranks-help");
}

function paintSummary() {
  const dialog = document.querySelector("#poker-summary");
  if (!dialog || !current.summary) return;
  const analysis = document.querySelector(".play")?.hasAttribute("data-analysis");
  if (analysis || preview) return;
  fillSummary(dialog);
  const key = `pn-hand-${current.id}`;
  let seen = false;
  try {
    seen = sessionStorage.getItem(key) === "1";
  } catch {
    seen = false;
  }
  if (seen || dialog.open) return;
  dialog.showModal();
}

function summaryCard(code) {
  const img = document.createElement("img");
  img.alt = cardLabel(code);
  img.src = faceSrc(code);
  return img;
}

function fillSummary(dialog) {
  const data = current.summary || {};
  dialog.classList.toggle("is-board", data.kind === "board");
  const finish = dialog.querySelector("#summary-finish");
  if (finish) finish.textContent = "Остановить";
  if (data.kind === "board") fillBoardSummary(dialog, data);
  else if (data.kind === "parlor") fillParlorSummary(dialog, data);
  else if (current.game_type === "uno" || data.kind === "uno") fillUnoSummary(dialog, data);
  else fillPokerSummary(dialog, data);
  const again = dialog.querySelector("#summary-again");
  if (again) {
    again.hidden = !current.rematch?.available;
    again.textContent = "Играть ещё раз";
  }
}

function fillPokerSummary(dialog, data) {
  const title = dialog.querySelector("#summary-title");
  const line = dialog.querySelector("#summary-line");
  const board = dialog.querySelector("#summary-board");
  const stats = dialog.querySelector("#summary-stats");
  const list = dialog.querySelector("#summary-seats");
  const kicker = dialog.querySelector("#summary-kicker");
  if (kicker) {
    const street = data.reason === "stopped"
      ? "Остановлена"
      : (data.board || []).length >= 5
        ? "Вскрытие"
        : data.reason === "fold"
          ? "Без вскрытия"
          : "Раздача";
    kicker.textContent = street;
  }
  if (title) {
    title.textContent = data.reason === "stopped"
      ? "Партия остановлена"
      : data.winner_name
        ? `${data.winner_name} забирает банк`
        : "Ничья";
    title.classList.toggle("is-win", Boolean(data.winner));
  }
  if (line) line.textContent = data.combination || data.line || "";
  if (board) {
    board.replaceChildren();
    for (const card of data.board || []) board.append(summaryCard(card));
    board.hidden = !(data.board || []).length;
  }
  if (stats) {
    const counts = data.counts || {};
    const raises = Number(counts.raise || 0) + Number(counts.bet || 0);
    stats.replaceChildren();
    const cells = [
      ["Банк", data.pot || 0],
      ["Пас", counts.fold || 0],
      ["Уравняли", counts.call || 0],
      ["Повышения", raises],
      ["Чек", counts.check || 0],
    ];
    for (const [label, value] of cells) {
      const cell = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = String(value);
      const span = document.createElement("span");
      span.textContent = label;
      cell.append(strong, span);
      stats.append(cell);
    }
  }
  if (list) {
    list.replaceChildren();
    for (const seat of data.seats || []) {
      const item = document.createElement("li");
      const tone = seat.winner ? "win" : seat.busted ? "fold" : seat.action === "bet" ? "raise" : seat.action;
      if (tone) item.classList.add(`is-${tone}`);
      const who = document.createElement("div");
      who.className = "summary-who";
      const name = document.createElement("strong");
      const word = seat.busted ? "вне игры" : seat.winner ? "выиграл" : (ACTION_WORD[seat.action] || "ждал");
      fillPersonName(name, seat);
      const act = document.createElement("span");
      act.textContent = word;
        const id = document.createElement("div");
  id.className = "summary-id";
  id.append(name, act);
  who.append(playerFace(seat), id);
      const cards = document.createElement("div");
      cards.className = "summary-cards";
      for (const card of seat.cards || []) cards.append(summaryCard(card));
      if (seat.made) {
        const made = document.createElement("em");
        made.textContent = seat.made;
        cards.append(made);
      }
      const money = document.createElement("div");
      money.className = "summary-money";
      money.append(
        Object.assign(document.createElement("span"), { textContent: `вложил ${seat.invested || 0}` }),
        Object.assign(document.createElement("span"), { textContent: `получил ${seat.payout || 0}` }),
        Object.assign(document.createElement("span"), { textContent: `осталось ${seat.stack ?? "—"}` }),
      );
      item.append(who, cards, money);
      list.append(item);
    }
  }
}

function fillUnoSummary(dialog, data) {
  const title = dialog.querySelector("#summary-title");
  const line = dialog.querySelector("#summary-line");
  const board = dialog.querySelector("#summary-board");
  const stats = dialog.querySelector("#summary-stats");
  const list = dialog.querySelector("#summary-seats");
  const kicker = dialog.querySelector("#summary-kicker");
  if (kicker) {
    kicker.textContent = data.reason === "stopped" ? "Остановлена" : data.reason === "left" ? "Выход из-за стола" : "Партия";
  }
  if (title) {
    title.textContent = data.reason === "stopped"
      ? "Партия остановлена"
      : data.winner_name
        ? `Победитель — ${data.winner_name}`
        : "Партия окончена";
    title.classList.toggle("is-win", Boolean(data.winner));
  }
  if (line) line.textContent = data.line || "";
  if (board) {
    board.replaceChildren();
    for (const card of data.board || []) board.append(summaryCard(card));
    board.hidden = !(data.board || []).length;
  }
  if (stats) {
    const counts = data.counts || {};
    stats.replaceChildren();
    const cells = [
      ["Ходы", counts.play || 0],
      ["Взяли", counts.draw || 0],
      ["УНО", counts.uno || 0],
      ["Штрафы", Number(counts.miss || 0) + Number(counts.draw2 || 0)],
      ["В колоде", data.pot || 0],
    ];
    for (const [label, value] of cells) {
      const cell = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = String(value);
      const span = document.createElement("span");
      span.textContent = label;
      cell.append(strong, span);
      stats.append(cell);
    }
  }
  if (list) {
    list.replaceChildren();
    for (const seat of data.seats || []) {
      const item = document.createElement("li");
      if (seat.winner) item.classList.add("is-win");
      const who = document.createElement("div");
      who.className = "summary-who";
      const name = document.createElement("strong");
      const left = Number(seat.count || 0);
      const word = seat.winner ? "победитель" : `осталось ${left}`;
      fillPersonName(name, seat);
      const act = document.createElement("span");
      act.textContent = seat.said ? `${word} · УНО` : word;
        const id = document.createElement("div");
  id.className = "summary-id";
  id.append(name, act);
  who.append(playerFace(seat), id);
      const cards = document.createElement("div");
      cards.className = "summary-cards";
      for (const card of seat.cards || []) cards.append(summaryCard(card));
      if (!seat.winner && !seat.cards?.length && UNO_WORD[seat.action]) {
        const made = document.createElement("em");
        made.textContent = UNO_WORD[seat.action];
        cards.append(made);
      }
      item.append(who, cards);
      list.append(item);
    }
  }
}

function fillParlorSummary(dialog, data) {
  const title = dialog.querySelector("#summary-title");
  const line = dialog.querySelector("#summary-line");
  const board = dialog.querySelector("#summary-board");
  const stats = dialog.querySelector("#summary-stats");
  const list = dialog.querySelector("#summary-seats");
  const kicker = dialog.querySelector("#summary-kicker");
  if (kicker) kicker.textContent = data.title || "Партия";
  if (title) {
    title.textContent = data.reason === "stopped"
      ? "Партия остановлена"
      : data.headline
        || (data.winner_name ? `Победитель — ${data.winner_name}` : data.line || "Партия окончена");
    title.classList.toggle("is-win", Boolean(data.winner));
  }
  if (line) line.textContent = data.headline ? (data.detail || "") : (data.line || "");
  if (board) {
    board.replaceChildren();
    for (const card of data.board || []) board.append(summaryCard(card));
    board.hidden = !(data.board || []).length;
  }
  if (stats) {
    stats.replaceChildren();
    stats.hidden = true;
  }
  const sheet = data.sheet;
  let pulya = dialog.querySelector("#summary-pulya");
  if (!pulya) {
    pulya = document.createElement("div");
    pulya.id = "summary-pulya";
    list?.before(pulya);
  }
  pulya.replaceChildren();
  if (sheet && Array.isArray(sheet.seats) && sheet.seats.length) pulya.append(pulyaTable(sheet, data.seats));
  pulya.hidden = !pulya.childElementCount;
  if (list) {
    list.replaceChildren();
    for (const seat of data.seats || []) {
      const item = document.createElement("li");
      if (seat.winner) item.classList.add("is-win");
      const who = document.createElement("div");
      who.className = "summary-who";
      const name = document.createElement("strong");
      fillPersonName(name, seat);
      const act = document.createElement("span");
      act.textContent = seat.note || (seat.winner ? "победитель" : "");
        const id = document.createElement("div");
  id.className = "summary-id";
  id.append(name, act);
  who.append(playerFace(seat), id);
      const cards = document.createElement("div");
      cards.className = "summary-cards";
      for (const card of seat.cards || []) cards.append(summaryCard(card));
      item.append(who, cards);
      list.append(item);
    }
  }
}

function pulyaNumber(value) {
  return String(Number(value) || 0).replace("-", "−");
}

function chipWord(count) {
  const number = Math.abs(Number(count) || 0);
  const tail = number % 10;
  const hundred = number % 100;
  if (tail === 1 && hundred !== 11) return "фишка";
  if (tail >= 2 && tail <= 4 && (hundred < 12 || hundred > 14)) return "фишки";
  return "фишек";
}

function chipMark(value) {
  const number = Number(value) || 0;
  if (number > 0) return `+${number}`;
  return pulyaNumber(number);
}

function victoryTarget(seats, total, key) {
  const mine = Number(total[key] ?? 0);
  const others = seats.filter((seat) => seat !== key).map((seat) => Number(total[seat] ?? 0));
  const best = others.length ? Math.max(...others) : mine - 1;
  if (mine > best) return "впереди";
  return pulyaNumber(best + 1);
}

function pulyaTable(sheet, people) {
  const names = new Map((people || []).map((seat) => [seat.key, seat.name]));
  const seats = sheet.seats;
  const pool = Number(sheet.pool) || 0;
  const table = document.createElement("table");
  table.className = "pulya";
  const head = document.createElement("tr");
  head.append(document.createElement("th"));
  for (const key of seats) {
    const cell = document.createElement("th");
    cell.append(document.createTextNode(names.get(key) || key));
    const goal = document.createElement("span");
    goal.className = "pulya-goal";
    goal.textContent = `до ${pool}`;
    cell.append(goal);
    head.append(cell);
  }
  table.append(head);
  const bullet = sheet.bullet || {};
  const mountain = sheet.mountain || {};
  const whists = sheet.whists || {};
  const total = sheet.total || {};
  const totals = Object.keys(total).length > 0;
  const stacks = sheet.stacks || {};
  const chips = sheet.chips || {};
  const unpaid = sheet.unpaid || {};
  const stake = Number(sheet.stake) || 0;
  const rows = [
    { label: "Пуля", value: (key) => `${bullet[key] ?? 0} / ${pool}` },
    { label: "Гора", value: (key) => mountain[key] ?? 0 },
  ];
  for (const other of seats) {
    rows.push({
      label: `Висты на ${names.get(other) || other}`,
      value: (key) => (key === other ? "—" : ((whists[key] || {})[other] ?? 0)),
    });
  }
  if (totals) rows.push({ label: "Итог", kind: "total", value: (key) => pulyaNumber(total[key] ?? 0) });
  if (Object.keys(stacks).length) {
    rows.push({ label: "На столе", kind: "stack", value: (key) => pulyaNumber(stacks[key] ?? 0) });
  }
  if (sheet.closed && Object.keys(chips).length) {
    rows.push({
      label: "Расписка",
      kind: "chips",
      value: (key) => chipMark(chips[key] ?? 0),
      tone: (key) => Number(chips[key] ?? 0),
    });
  }
  if (Object.values(unpaid).some((value) => Number(value) > 0)) {
    rows.push({ label: "Не хватило", kind: "short", value: (key) => pulyaNumber(unpaid[key] ?? 0) });
  }
  if (totals && !sheet.closed) {
    rows.push({ label: "К победе", kind: "goal", value: (key) => victoryTarget(seats, total, key) });
  }
  const bestTotal = totals ? Math.max(...seats.map((key) => Number(total[key] ?? 0))) : 0;
  const leaders = totals ? seats.filter((key) => Number(total[key] ?? 0) === bestTotal) : [];
  for (const rowInfo of rows) {
    const row = document.createElement("tr");
    if (rowInfo.kind) row.className = `is-${rowInfo.kind}`;
    const name = document.createElement("th");
    name.textContent = rowInfo.label;
    row.append(name);
    for (const key of seats) {
      const cell = document.createElement("td");
      cell.textContent = String(rowInfo.value(key));
      if (typeof rowInfo.tone === "function") {
        const tone = rowInfo.tone(key);
        if (tone > 0) cell.classList.add("is-plus");
        if (tone < 0) cell.classList.add("is-minus");
      }
      if (rowInfo.kind === "total" && leaders.length === 1 && leaders[0] === key) cell.classList.add("is-ahead");
      row.append(cell);
    }
    table.append(row);
  }
  const caption = document.createElement("caption");
  const price = stake ? ` Очко стоит ${stake} ${chipWord(stake)}.` : "";
  const rule = `Пуля до ${pool}.${price} Побеждает больший итог.`;
  caption.textContent = sheet.closed ? `Расписка. ${rule}` : rule;
  table.prepend(caption);
  return table;
}

function fillBoardSummary(dialog, data) {
  const chess = data.game === "chess";
  const title = dialog.querySelector("#summary-title");
  const line = dialog.querySelector("#summary-line");
  const board = dialog.querySelector("#summary-board");
  const stats = dialog.querySelector("#summary-stats");
  const list = dialog.querySelector("#summary-seats");
  const kicker = dialog.querySelector("#summary-kicker");
  if (kicker) kicker.textContent = data.reason === "stopped" ? "Остановлена" : chess ? "Шахматы" : "Шашки";
  if (title) {
    title.textContent = data.reason === "stopped"
      ? "Партия остановлена"
      : data.winner_name
        ? `Победитель — ${data.winner_name}`
        : "Ничья";
    title.classList.toggle("is-win", Boolean(data.winner));
  }
  if (line) line.textContent = data.line || "";
  if (board) {
    board.replaceChildren();
    board.hidden = true;
  }
  if (stats) {
    const counts = data.counts || {};
    stats.replaceChildren();
    const cells = chess
      ? [
          ["Ходов", counts.moves || 0],
          ["Взятий", counts.captures || 0],
          ["Шахов", counts.checks || 0],
          ["Белые", counts.white || 0],
          ["Чёрные", counts.black || 0],
        ]
      : [
          ["Ходов", counts.moves || 0],
          ["Взятий", counts.captures || 0],
          ["Дамки", counts.kings || 0],
          ["Белые", counts.white || 0],
          ["Чёрные", counts.black || 0],
        ];
    for (const [label, value] of cells) {
      const cell = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = String(value);
      const span = document.createElement("span");
      span.textContent = label;
      cell.append(strong, span);
      stats.append(cell);
    }
  }
  if (list) {
    list.replaceChildren();
    const noun = chess ? "фигур" : "шашек";
    for (const seat of data.seats || []) {
      const item = document.createElement("li");
      if (seat.winner) item.classList.add("is-win");
      const who = document.createElement("div");
      who.className = "summary-who";
      const name = document.createElement("strong");
      fillPersonName(name, seat);
      const act = document.createElement("span");
      const word = data.reason === "stopped" ? "за столом" : seat.winner ? "победитель" : data.winner ? "проиграл" : "ничья";
      act.textContent = `${seat.side || ""} · ${word}`.replace(/^ · /, "");
        const id = document.createElement("div");
  id.className = "summary-id";
  id.append(name, act);
  who.append(playerFace(seat), id);
      const pieces = document.createElement("div");
      pieces.className = "summary-money";
      pieces.textContent = `${seat.pieces || 0} ${noun}`;
      item.append(who, pieces);
      list.append(item);
    }
  }
}

function rememberSummary() {
  try {
    sessionStorage.setItem(`pn-hand-${current.id}`, "1");
  } catch {
    /* остаётся на этот заход страницы */
  }
}

function paintRematch() {
  const offer = current.rematch || {};
  const analysis = document.querySelector(".play")?.hasAttribute("data-analysis");
  const open = Boolean(offer.available) && !analysis;
  const state = offer.state || "idle";
  const button = document.querySelector("#rematch");
  if (button) {
    button.hidden = !open || state === "incoming" || state === "outgoing" || state === "accepted";
    button.disabled = busy;
    const label = "Играть ещё раз";
    button.setAttribute("aria-label", label);
    const tip = button.parentElement?.querySelector(".tip");
    if (tip) tip.textContent = label;
  }
  const bar = document.querySelector("#rematch-offer");
  const text = document.querySelector("#rematch-text");
  const accept = document.querySelector("#rematch-accept");
  const decline = document.querySelector("#rematch-decline");
  if (!bar) return;
  bar.hidden = !open || !["incoming", "outgoing", "declined"].includes(state);
  if (text) text.textContent = offer.note || "";
  if (accept) accept.hidden = state !== "incoming";
  if (decline) decline.hidden = state !== "incoming";
  if (open && offer.game_id && offer.game_id !== current.id) {
    window.location.assign(`/games/${offer.game_id}`);
  }
}

const SUITS = { S: "♠", H: "♥", D: "♦", C: "♣" };
const UNO_COLOR = { R: "red", Y: "yellow", G: "green", B: "blue" };
const UNO_NAME = { R: "красный", Y: "жёлтый", G: "зелёный", B: "синий" };
const TABLE = "/static/images/tables";

function cardsWord(count) {
  const tens = count % 100;
  const ones = count % 10;
  if (ones === 1 && tens !== 11) return "карта";
  if (ones >= 2 && ones <= 4 && (tens < 12 || tens > 14)) return "карты";
  return "карт";
}

function cardLabel(code) {
  const text = String(code || "");
  if (current.game_type === "uno") {
    const names = { R: "красная", Y: "жёлтая", G: "зелёная", B: "синяя", W: "дикая" };
    if (text === "W" || text.startsWith("W")) return "дикая карта";
    const rank = text.slice(1).replace("S", "пропуск").replace("D", "возьми две");
    return `${names[text[0]] || "карта"} ${rank}`;
  }
  const rank = text[0] === "T" ? "10" : text[0] || "карта";
  return `${rank} ${SUITS[text[1]] || ""}`.trim();
}

function faceSrc(code) {
  if (current.game_type === "uno") {
    if (code === "W" || String(code).startsWith("W")) return svgDataUrl(unoFace({ kind: "wild" }));
    const kind = code[1] === "S" ? "skip" : code[1] === "D" ? "draw2" : "number";
    return svgDataUrl(unoFace({
      color: UNO_COLOR[code[0]] || "red",
      kind,
      number: kind === "number" ? Number(code[1]) : 0,
    }));
  }
  return svgDataUrl(pokerFace({ rank: code[0], suit: code[1] }));
}

function backSrc() {
  const name = current.game_type === "uno" ? "card-back-uno.png" : "card-back-poker.png";
  return asset(`${TABLE}/${name}`);
}

function anchor(node, x, y, className) {
  node.className = `anchor ${className}`.trim();
  node.style.setProperty("--x", String(x));
  node.style.setProperty("--y", String(y));
  return node;
}

function makeCard(src, { alt = "", button = false, key = "", active = false, onClick = null } = {}) {
  const node = document.createElement(button ? "button" : "img");
  node.className = active ? "card is-active" : "card";
  if (button) {
    node.type = "button";
    const img = document.createElement("img");
    img.alt = alt;
    img.draggable = false;
    img.src = src;
    node.append(img);
    node.setAttribute("aria-label", alt);
    if (onClick) node.addEventListener("click", onClick);
  } else {
    node.alt = alt;
    node.draggable = false;
    node.src = src;
  }
  if (key) node.dataset.card = key;
  return node;
}

function fanAngles(count) {
  if (count <= 1) return [0];
  const spread = count >= 7 ? 30 : 24;
  const step = spread / (count - 1);
  return Array.from({ length: count }, (_, index) => Math.round((-spread / 2 + step * index) * 10) / 10);
}

function fitOverlap(count, card, preferred, limit) {
  if (count <= 1) return preferred;
  const width = count * card + (count - 1) * preferred;
  if (width <= limit) return preferred;
  return (limit - count * card) / (count - 1);
}

function cardFan(cards, { x, y, role, angles = null, overlap = null, mid = null }) {
  const row = document.createElement("div");
  anchor(row, x, y, `cards ${role}`);
  if (overlap != null) row.style.setProperty("--overlap", `${overlap}cqw`);
  const middle = Math.floor(cards.length / 2);
  cards.forEach((card, index) => {
    if (mid && index === middle) row.append(mid);
    card.style.zIndex = card.tagName === "BUTTON" ? String(40 + index) : String(index + 1);
    if (angles) card.style.setProperty("--angle", `${angles[index] || 0}deg`);
    row.append(card);
  });
  if (mid && cards.length === 0) row.append(mid);
  return row;
}

const ACTION_WORD = {
  fold: "пас",
  call: "уравнял",
  raise: "повысил",
  bet: "ставка",
  check: "чек",
};

function seatTone(key, folded) {
  const winners = current.summary?.winners;
  if (Array.isArray(winners)) {
    if (winners.includes(key)) return "win";
  } else if (current.summary?.winner === key) return "win";
  const mark = (current.marks || {})[key];
  if (folded || mark === "fold") return "fold";
  if (mark === "raise" || mark === "bet") return "raise";
  if (mark === "call") return "call";
  if (mark === "check") return "check";
  return "";
}

function badgeLabel(name, key, { you = false, folded = false } = {}) {
  const tone = seatTone(key, folded);
  const action = tone === "win" ? "выиграл" : (ACTION_WORD[(current.marks || {})[key]] || (folded ? "пас" : ""));
  const who = you ? `${name} · вы` : name;
  return { text: action ? `${who} · ${action}` : who, tone };
}

function seatBadge(text, x, y, active, tone = "") {
  const node = document.createElement("div");
  const classes = ["badge"];
  if (active) classes.push("is-active");
  if (tone) classes.push(`is-${tone}`);
  anchor(node, x, y, classes.join(" "));
  node.textContent = text;
  return node;
}

function paintWinnerLine(node, text) {
  node.replaceChildren();
  const label = current.summary?.winner_label || "";
  let index = label ? text.lastIndexOf(label) : -1;
  let length = label.length;
  if (index < 0 && label.length >= 4) {
    const stem = label.slice(0, 4).toLocaleLowerCase("ru");
    index = text.toLocaleLowerCase("ru").lastIndexOf(stem);
    length = stem.length;
    while (index >= 0 && index + length < text.length && /\p{L}/u.test(text[index + length])) length += 1;
  }
  if (index < 0) {
    node.textContent = text;
    return;
  }
  node.append(document.createTextNode(text.slice(0, index)));
  const mark = document.createElement("span");
  mark.className = "who-win";
  mark.textContent = text.slice(index, index + length);
  node.append(mark, document.createTextNode(text.slice(index + length)));
}

function shownSide(side) {
  const hands = current.shown || {};
  return Array.isArray(hands[side]) ? hands[side] : [];
}

const RINGS = {
  2: [[50, 91], [50, 7]],
  3: [[50, 91], [88, 12], [12, 12]],
  4: [[50, 91], [90, 66], [50, 7], [10, 66]],
  5: [[50, 92], [91, 74], [82, 8], [18, 8], [9, 74]],
  6: [[50, 92], [91, 76], [86, 8], [50, 5], [14, 8], [9, 76]],
};

function orderedSeats(seats) {
  const index = seats.findIndex((seat) => seat.you);
  if (index <= 0) return seats;
  return seats.slice(index).concat(seats.slice(0, index));
}

function pokerRoster(youName) {
  if (Array.isArray(current.seats) && current.seats.length > 1) return current.seats;
  const yourKey = current.seat_color || current.your_side || "white";
  const otherKey = yourKey === "black" ? "white" : "black";
  const stacks = current.stacks || {};
  const committed = current.committed || {};
  const waiting = current.phase === "waiting";
  const namedRival = otherKey === "black" ? current.black_name : current.white_name;
  const rivalName = namedRival || current.opponent_name || "Соперник";
  return [
    {
      key: yourKey,
      name: youName,
      login: current.login || "",
      avatar: current.avatar || "",
      you: true,
      turn: Boolean(current.your_turn),
      folded: false,
      count: (current.hand || []).length,
      stack: Object.prototype.hasOwnProperty.call(stacks, yourKey) ? stacks[yourKey] : null,
      bet: committed[yourKey] || 0,
      dealer: current.button === yourKey,
      cpu: false,
      kind: "you",
    },
    {
      key: otherKey,
      name: waiting ? "Ждём игрока" : rivalName,
      login: waiting ? "" : (current.opponent_login || ""),
      avatar: waiting ? "" : (current.opponent_avatar || ""),
      you: false,
      turn: !waiting && !current.your_turn && current.status === "active",
      folded: false,
      count: waiting ? 0 : Number(current.opponent_count || 0),
      stack: Object.prototype.hasOwnProperty.call(stacks, otherKey) ? stacks[otherKey] : null,
      bet: committed[otherKey] || 0,
      dealer: current.button === otherKey,
      cpu: Boolean(current.cpu_opponent) || current.mode === "vs_computer",
      kind: current.mode === "vs_computer" ? "computer" : "human",
    },
  ];
}

function inward(x, y, scale) {
  return { x: x + (50 - x) * scale, y: y + (48 - y) * scale };
}

function outward(x, y, scale) {
  return { x: x + (x - 50) * scale, y: y + (y - 48) * scale };
}

function pokerCardPlace(x, y) {
  if (y >= 70) return inward(x, y, 0.26);
  if (y <= 22) return inward(x, y, 0.18);
  return inward(x, y, 0.2);
}

function pokerPlatePlace(x, y) {
  const cards = pokerCardPlace(x, y);
  const dx = x - 50;
  const dy = y - 48;
  if (Math.abs(dy) >= Math.abs(dx)) {
    if (dy >= 0) return { x: cards.x + 10, y: cards.y, side: "right" };
    return { x: cards.x, y: cards.y - 8, side: "top" };
  }
  if (dx >= 0) return { x: cards.x + 7, y: cards.y, side: "right" };
  return { x: cards.x - 7, y: cards.y, side: "left" };
}

function salonCardPlace(x, y) {
  const place = pokerCardPlace(x, y);
  if (y <= 22) return { x: place.x, y: place.y + 4 };
  return place;
}

function salonPlatePlace(x, y, cards, you) {
  if (you) {
    const drop = current.game_type === "preferans" ? 15 : 11;
    return {
      x: cards.x,
      y: Math.min(current.game_type === "preferans" ? 97 : 93, cards.y + drop),
      lift: current.game_type === "preferans" ? 16 : 0,
    };
  }
  if (y > 22) return { x: cards.x, y: Math.max(10, cards.y - 8) };
  return pokerPlatePlace(x, y);
}

const CPU_FACE = "/static/images/computer-avatar.jpg";

function cpuAvatar() {
  const image = document.createElement("img");
  image.className = "avatar";
  image.alt = "компьютер";
  image.src = CPU_FACE;
  return image;
}

function playerFace(seat) {
  const cpu = Boolean(
    seat?.cpu || seat?.kind === "computer" || (current.computer_side && seat?.key === current.computer_side),
  );
  if (cpu) return cpuAvatar();
  return avatarChip(seat?.name || "", seat?.avatar || "");
}

function computerSpeaker() {
  const side = current.computer_side;
  if (side === "white" || side === "black") {
    return side === "black" ? current.black_name : current.white_name;
  }
  const seat = (current.seats || []).find((item) => item.cpu);
  return seat?.name || current.opponent_name || "";
}

function playerPlate(seat, x, y) {
  const tone = seatTone(seat.key, seat.folded);
  const node = document.createElement("div");
  const classes = ["plate"];
  if (seat.turn) classes.push("is-active");
  if (tone) classes.push(`is-${tone}`);
  anchor(node, x, y, classes.join(" "));
  const cpu = Boolean(seat.cpu || seat.kind === "computer");
  if (seat.busted) node.classList.add("is-busted");
  const face = plateFace(seat, cpu);
  const copy = document.createElement("span");
  copy.className = "plate-copy";
  const title = document.createElement("span");
  title.className = "plate-name";
  fillPersonName(title, { name: seat.you ? `${seat.name} · вы` : seat.name, login: seat.login });
  copy.append(title);
  const stack = document.createElement("span");
  stack.className = "plate-stack";
  const known = seat.stack !== undefined && seat.stack !== null && seat.stack !== "";
  stack.textContent = known ? String(seat.stack) : "—";
  copy.append(stack);
  let action = tone === "win" ? "выиграл" : (ACTION_WORD[(current.marks || {})[seat.key]] || "");
  if (seat.busted) action = "вне игры";
  if (action) {
    const mark = document.createElement("span");
    mark.className = "plate-action";
    mark.textContent = action;
    copy.append(mark);
  }
  node.append(face, copy);
  return node;
}

function chipFile(amount) {
  const value = Math.floor(Number(amount));
  if (!Number.isFinite(value) || value < 1) return "";
  const bands = [49, 99, 249, 499, 999, 1999, 3999, 7999, 14999, 29999, 59999];
  const index = bands.findIndex((hi) => value <= hi);
  const n = String((index < 0 ? 12 : index + 1)).padStart(2, "0");
  return `chips-stack-${n}.png`;
}

function purseSpot(cards, plate) {
  const dx = cards.x - plate.x;
  const dy = cards.y - plate.y;
  const len = Math.hypot(dx, dy) || 1;
  const gap = 14;
  return {
    x: Math.min(90, Math.max(10, cards.x + (dx / len) * gap)),
    y: Math.min(88, Math.max(10, cards.y + (dy / len) * gap)),
  };
}

function purseAnchor(seatX, seatY, cards, plate) {
  const hero = seatY > 78 && seatX > 36 && seatX < 64;
  if (hero) return purseSpot(cards, plate);
  if (seatY < 30 && seatX > 64) {
    return { x: Math.min(93, cards.x + 9), y: cards.y + 4 };
  }
  if (seatY < 30) {
    return { x: Math.min(82, Math.max(18, cards.x + 9)), y: Math.min(20, cards.y + 7) };
  }
  if (seatX < 40) {
    return { x: cards.x, y: Math.max(16, cards.y - 13) };
  }
  return { x: cards.x, y: Math.max(16, cards.y - 15) };
}

function purseNode(amount) {
  const file = chipFile(amount);
  if (!file) return null;
  const node = document.createElement("div");
  node.className = "purse";
  const img = document.createElement("img");
  img.alt = "";
  img.draggable = false;
  img.src = asset(`${TABLE}/${file}`);
  node.append(img);
  node.title = `${amount} фишек`;
  node.setAttribute("role", "img");
  node.setAttribute("aria-label", `${amount} фишек`);
  return node;
}

function preferansPurseSpot(seatX, seatY, cards, plate) {
  if (seatY > 70) return { x: Math.min(88, cards.x + 34), y: cards.y + 1 };
  if (seatX > 50) return { x: Math.max(56, cards.x - 10), y: cards.y + 1 };
  return { x: plate.x - 4, y: Math.min(44, plate.y + 13) };
}

function placePurse(box, plate, cards, seatX, seatY, amount) {
  const node = purseNode(amount);
  if (!node) return;
  const spot = purseAnchor(seatX, seatY, cards, plate);
  box.append(anchor(node, spot.x, spot.y, "purse"));
}

function chipBet(amount, spot) {
  const node = document.createElement("div");
  node.textContent = String(amount);
  return anchor(node, spot.x, spot.y, "bet-chip");
}

function dealerMark(x, y) {
  const node = document.createElement("div");
  node.textContent = "Д";
  node.title = "Дилер";
  const dx = x >= 50 ? -10 : 10;
  const dy = y >= 48 ? 9 : -9;
  return anchor(node, x + dx, y + dy, "dealer-btn");
}

function paintPokerRing(box, heroCards) {
  const seats = orderedSeats(pokerRoster(box.dataset.you || "Вы"));
  const spots = RINGS[seats.length] || RINGS[6];
  seats.forEach((seat, index) => {
    const spot = spots[index] || spots[spots.length - 1];
    const x = spot[0];
    const y = spot[1];
    const shown = (current.shown && current.shown[seat.key]) || [];
    const cards = seat.you
      ? heroCards
      : shown.length
        ? shown.map((card) => makeCard(faceSrc(card), { alt: cardLabel(card) }))
        : Array.from({ length: seat.count || 0 }, () => makeCard(backSrc(), { alt: "Закрытая карта" }));
    const place = pokerCardPlace(x, y);
    if (cards.length) {
      box.append(cardFan(cards, {
        x: place.x,
        y: place.y,
        role: seat.you ? "hero" : "opponent",
        angles: fanAngles(cards.length),
        overlap: fitOverlap(cards.length, seat.you ? 7.6 : 4.6, seat.you ? -2.6 : -1.8, seat.you ? 22 : 12),
      }));
    }
    if (Number(seat.bet) > 0) box.append(chipBet(seat.bet, inward(x, y, 0.5)));
    const plate = pokerPlatePlace(x, y);
    const badge = playerPlate(seat, plate.x, plate.y);
    badge.classList.add(`is-${plate.side}`);
    box.append(badge);
    placePurse(box, plate, place, x, y, seat.stack);
    if (seat.dealer) box.append(dealerMark(place.x, place.y));
  });
  const boardCards = Array.isArray(current.board) ? current.board : [];
  if (boardCards.length) {
    const row = document.createElement("div");
    row.className = "board-row";
    for (const card of boardCards) row.append(makeCard(faceSrc(card), { alt: cardLabel(card) }));
    box.append(anchor(row, 50, 50, "board-row"));
  }
  if (current.winner_hand) {
    const made = document.createElement("div");
    paintWinnerLine(made, current.winner_hand);
    box.append(anchor(made, 50, 60, "hand-name"));
  }
  const pot = document.createElement("div");
  anchor(pot, 50, 40, "pot");
  const advice = document.createElement("p");
  advice.id = "table-advice";
  advice.className = "table-advice";
  advice.setAttribute("aria-hidden", "true");
  paintWinnerLine(advice, status?.textContent || current.status_line || "");
  pot.append(advice, document.createTextNode(`Банк: ${current.pot || 0} фишек`));
  box.append(pot, ranksButton());
}

const UNO_WORD = {
  uno: "УНО",
  draw: "взял карту",
  play: "ход",
  wild: "дикая",
  skip: "пропуск",
  draw2: "+2",
  miss: "не сказал УНО",
};

const PREFERANS_WORD = {
  pass: "пас",
  whist: "вист",
  half: "полвиста",
  "pass-whist": "пас на вист",
};

const PREFERANS_TONE = {
  pass: "fold",
  whist: "call",
  half: "raise",
  "pass-whist": "check",
};

function unoRoster(youName) {
  if (Array.isArray(current.seats) && current.seats.length > 1) {
    return current.seats.map((seat) => ({
      ...seat,
      count: seat.you ? (current.hand || []).length : Number(seat.count || 0),
    }));
  }
  const yourKey = current.seat_color || current.your_side || "white";
  const otherKey = yourKey === "black" ? "white" : "black";
  const waiting = current.phase === "waiting";
  const namedRival = otherKey === "black" ? current.black_name : current.white_name;
  const rivalName = namedRival || current.opponent_name || "Соперник";
  return [
    {
      key: yourKey,
      name: youName,
      login: current.login || "",
      avatar: current.avatar || "",
      you: true,
      turn: Boolean(current.your_turn),
      count: (current.hand || []).length,
      cpu: false,
      kind: "you",
    },
    {
      key: otherKey,
      name: waiting ? "Ждём игрока" : rivalName,
      login: waiting ? "" : (current.opponent_login || ""),
      avatar: waiting ? "" : (current.opponent_avatar || ""),
      you: false,
      turn: !waiting && !current.your_turn && current.status === "active",
      count: waiting ? 0 : Number(current.opponent_count || 0),
      cpu: current.mode === "vs_computer",
      kind: current.mode === "vs_computer" ? "computer" : "human",
    },
  ];
}

function unoPlate(seat, x, y) {
  const said = (current.said || []).includes(seat.key);
  const mark = said ? "uno" : ((current.marks || {})[seat.key] || "");
  const won = current.result === `${seat.key}_win`;
  const tone = won ? "win" : (PREFERANS_TONE[mark] || mark);
  const node = document.createElement("div");
  const classes = ["plate"];
  if (seat.turn && current.status === "active") classes.push("is-active");
  if (tone) classes.push(`is-${tone}`);
  anchor(node, x, y, classes.join(" "));
  const cpu = Boolean(seat.cpu || seat.kind === "computer");
  const face = plateFace(seat, cpu);
  const copy = document.createElement("span");
  copy.className = "plate-copy";
  const title = document.createElement("span");
  title.className = "plate-name";
  fillPersonName(title, { name: seat.you ? `${seat.name} · вы` : seat.name, login: seat.login });
  const count = document.createElement("span");
  const cards = Number(seat.count || 0);
  count.textContent = `${cards} ${cardsWord(cards)}`;
  const stackKnown = seat.stack !== undefined && seat.stack !== null && seat.stack !== "";
  copy.append(title);
  if (current.game_type === "preferans" && stackKnown) {
    count.className = "plate-count";
    const stack = document.createElement("span");
    stack.className = "plate-stack";
    stack.textContent = String(seat.stack);
    copy.append(stack);
  } else {
    count.className = "plate-stack";
  }
  copy.append(count);
  const word = won ? "победитель" : (PREFERANS_WORD[mark] || UNO_WORD[tone] || "");
  if (word) {
    const action = document.createElement("span");
    action.className = "plate-action";
    action.textContent = word;
    copy.append(action);
  }
  node.append(face, copy);
  return node;
}

function handControls(drawMove, unoMove) {
  const box = document.createElement("div");
  box.className = "hand-actions";
  if (wildOpen) {
    const colors = [["R", "Красная"], ["Y", "Жёлтая"], ["G", "Зелёная"], ["B", "Синяя"]];
    const palette = document.createElement("div");
    palette.className = "wild-colors";
    palette.setAttribute("role", "group");
    palette.setAttribute("aria-label", "Цвет дикой карты");
    for (const [code, title] of colors) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `swatch is-${code} tip-host`;
      button.dataset.tip = title;
      if (code === "B") button.dataset.tipEdge = "";
      button.setAttribute("aria-label", title);
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const move = (current.legal_moves || []).find((item) => item.path[0] === "play" && item.path[1] === "W" && item.path[2] === code);
        wildOpen = false;
        if (move) submit(calledPlay(move));
      });
      palette.append(button);
    }
    box.append(palette);
  }
  if (unoMove) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = unoArmed ? "is-uno is-on" : "is-uno";
    button.textContent = unoArmed ? "УНО!" : "УНО";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      unoArmed = true;
      button.classList.add("is-on");
      button.textContent = "УНО!";
      submit(unoMove);
    });
    box.append(button);
  }
  if (drawMove) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "is-draw";
    button.textContent = "Взять карту";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      submit(drawMove);
    });
    box.append(button);
  }
  return box;
}

function paintUnoRing(box, youName, heroCards) {
  const seats = orderedSeats(unoRoster(youName));
  const spots = RINGS[seats.length] || RINGS[6];
  const drawMove = (current.legal_moves || []).find((move) => move.path[0] === "draw");
  const unoMove = (current.legal_moves || []).find((move) => move.path[0] === "uno");
  const waiting = current.phase === "waiting";
  seats.forEach((seat, index) => {
    const spot = spots[index] || spots[spots.length - 1];
    const x = spot[0];
    const y = spot[1];
    const shown = (current.shown && current.shown[seat.key]) || [];
    const cards = seat.you
      ? heroCards
      : shown.length
        ? shown.map((card) => makeCard(faceSrc(card), { alt: cardLabel(card) }))
        : Array.from({ length: seat.count || 0 }, () => makeCard(backSrc(), { alt: "Закрытая карта" }));
    const place = inward(x, y, y >= 70 ? 0.18 : y <= 22 ? 0.16 : 0.34);
    if (cards.length) {
      box.append(cardFan(cards, {
        x: place.x,
        y: place.y,
        role: seat.you ? "hero" : "opponent",
        angles: fanAngles(cards.length),
        overlap: fitOverlap(cards.length, seat.you ? 7.2 : 4.2, seat.you ? -2.2 : -2.3, seat.you ? 40 : 16),
      }));
    }
    if (seat.you && (drawMove || unoMove || wildOpen)) {
      const controls = inward(x, y, 0.5);
      box.append(anchor(handControls(drawMove, unoMove), controls.x, controls.y, "hand-actions"));
    }
    const plate = outward(x, y, 0.1);
    box.append(unoPlate(seat, plate.x, plate.y));
  });
  const deck = Number(current.deck || 0);
  if (deck > 1) {
    const under = makeCard(backSrc(), { alt: "" });
    under.classList.add("center-card", "deck-base");
    box.append(anchor(under, 42, 46, under.className));
  }
  if (deck > 0) {
    const top = makeCard(backSrc(), { alt: "Колода" });
    top.classList.add("center-card", "deck-top");
    box.append(anchor(top, 42, 46, top.className));
  }
  if (current.top) {
    const discard = makeCard(faceSrc(current.top), { alt: cardLabel(current.top), key: `pile:${current.top}` });
    discard.classList.add("center-card");
    box.append(anchor(discard, 58, 46, discard.className));
    const arrow = document.createElement("img");
    arrow.alt = "По часовой стрелке";
    arrow.draggable = false;
    arrow.src = asset(`${TABLE}/uno-arrow.svg`);
    box.append(anchor(arrow, 50, 58, "direction"));
  }
  if (current.color && !waiting) {
    const color = document.createElement("div");
    color.textContent = UNO_NAME[current.color] || "цвет";
    box.append(anchor(color, 50, 34, `uno-badge is-color is-${current.color}`));
  }
}

function raisePad(move) {
  const pad = document.createElement("div");
  pad.className = "raise-pad";
  const min = Number(move.min);
  let max = Number(move.max);
  const put = Number(move.put || 0);
  const purse = Number(document.querySelector("#card-table")?.dataset.purse);
  if (Number.isFinite(purse) && purse >= 0) max = Math.min(max, put + purse);
  if (!Number.isFinite(max) || max < min) max = min;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary";
  const field = document.createElement("input");
  field.type = "range";
  field.min = String(min);
  field.max = String(max);
  field.step = "1";
  field.value = String(min);
  field.setAttribute("aria-label", "Размер повышения");
  const read = document.createElement("output");
  const paint = () => {
    const value = Number(field.value);
    const allIn = value >= max;
    button.textContent = allIn ? "Ва-банк" : (move.path[1] === "bet" ? "Ставка" : "Повысить");
    read.textContent = String(value);
  };
  field.addEventListener("input", paint);
  button.addEventListener("click", () => {
    const value = String(field.value);
    const allIn = Number(value) >= max;
    submit({
      path: [...move.path, value],
      notation: allIn ? "Ва-банк" : `${move.path[1] === "bet" ? "Ставка" : "Повысить до"} ${value}`,
      promotion: null,
    });
  });
  paint();
  pad.append(button, field, read);
  return pad;
}

function paintCrowd(box, poker, you, heroCards) {
  const others = (current.seats || []).filter((seat) => !seat.you);
  others.forEach((seat, index) => {
    const x = ((index + 1) / (others.length + 1)) * 100;
    const shown = (current.shown && current.shown[seat.key]) || [];
    const nodes = shown.length
      ? shown.map((card) => makeCard(faceSrc(card), { alt: cardLabel(card) }))
      : Array.from({ length: seat.count || 0 }, () => makeCard(backSrc(), { alt: "Закрытая карта" }));
    if (nodes.length) {
      box.append(cardFan(nodes, {
        x,
        y: poker ? 18 : 16,
        role: "opponent",
        overlap: fitOverlap(nodes.length, poker ? 5 : 6.2, poker ? -0.4 : -2.2, 28),
      }));
    }
    const badge = badgeLabel(seat.name, seat.key, { folded: seat.folded });
    box.append(seatBadge(badge.text, x, poker ? 5 : 4, Boolean(seat.turn), badge.tone));
  });
  if (poker) {
    if (heroCards.length) {
      box.append(cardFan(heroCards, {
        x: 50,
        y: 83,
        role: "hero",
        overlap: fitOverlap(heroCards.length, 8, -1, 72),
      }));
    }
    const hero = (current.seats || []).find((seat) => seat.you);
    const mine = badgeLabel(you, hero?.key || current.seat_color || "", { you: true, folded: hero?.folded });
    box.append(seatBadge(mine.text, 50, 101, current.your_turn, mine.tone));
    const boardCards = Array.isArray(current.board) ? current.board : [];
    if (boardCards.length) {
      const row = document.createElement("div");
      row.className = "board-row";
      for (const card of boardCards) row.append(makeCard(faceSrc(card), { alt: cardLabel(card) }));
      box.append(anchor(row, 50, 50, "board-row"));
    }
    if (current.winner_hand) {
      const made = document.createElement("div");
      paintWinnerLine(made, current.winner_hand);
      box.append(anchor(made, 50, 66, "hand-name"));
    }
    const pot = document.createElement("div");
    anchor(pot, 50, 32, "pot");
    pot.append(document.createTextNode(`Банк: ${current.pot || 0} фишек`));
    box.append(pot);
    return;
  }
  if (heroCards.length) {
    box.append(cardFan(heroCards, {
      x: 50,
      y: 94,
      role: "hero",
      overlap: fitOverlap(heroCards.length, 12.5714286, -4.2857143, 92),
    }));
  }
  box.append(seatBadge(`${you} · вы · ${heroCards.length} ${cardsWord(heroCards.length)}`, 50, 77, false));
  const deck = Number(current.deck || 0);
  if (deck > 0) {
    const top = makeCard(backSrc(), { alt: "Колода" });
    top.classList.add("center-card", "deck-top");
    box.append(anchor(top, 43, 46, top.className));
  }
  if (current.top) {
    const discard = makeCard(faceSrc(current.top), { alt: cardLabel(current.top) });
    discard.classList.add("center-card");
    box.append(anchor(discard, 59, 46, discard.className));
  }
  const marks = document.createElement("div");
  marks.className = "uno-badges";
  if (current.color) {
    const color = document.createElement("div");
    color.className = `uno-badge is-color is-${current.color}`;
    color.textContent = UNO_NAME[current.color] || "цвет";
    marks.append(color);
  }
  const turn = document.createElement("div");
  turn.className = "uno-badge is-turn";
  const mine = (current.seats || []).find((seat) => seat.you);
  const actor = (current.seats || []).find((seat) => seat.turn);
  if (current.your_turn) turn.classList.add("is-active");
  turn.textContent = current.status === "finished"
    ? "Партия окончена"
    : current.phase === "waiting"
      ? "Ждём игроков"
      : current.your_turn
        ? "Ваш ход"
        : `Ход: ${actor?.name || mine?.name || "соперник"}`;
  marks.append(turn);
  box.append(anchor(marks, 50, 64, "uno-badges"));
}

function blackjackSeats(youName) {
  if (Array.isArray(current.seats) && current.seats.length) return current.seats;
  const stacks = current.stacks || {};
  const committed = current.committed || {};
  const key = current.seat_color || current.your_side || Object.keys(stacks)[0] || "white";
  return [{
    key,
    name: youName,
    login: current.login || "",
    avatar: current.avatar || "",
    you: true,
    turn: Boolean(current.your_turn),
    folded: false,
    count: (current.hand || []).length,
    stack: Object.prototype.hasOwnProperty.call(stacks, key) ? stacks[key] : null,
    bet: committed[key] || 0,
    dealer: false,
    cpu: false,
    kind: "you",
  }];
}

function paintBlackjack(box, heroCards) {
  const seats = orderedSeats(blackjackSeats(box.dataset.you || "Вы"));
  const spots = RINGS[seats.length] || RINGS[6];
  seats.forEach((seat, index) => {
    const spot = spots[index] || spots[spots.length - 1];
    const x = spot[0];
    const y = spot[1];
    const shown = (current.shown && current.shown[seat.key]) || [];
    const cards = seat.you
      ? heroCards
      : shown.length
        ? shown.map((card) => makeCard(faceSrc(card), { alt: cardLabel(card), key: `show:${seat.key}:${card}` }))
        : Array.from({ length: seat.count || 0 }, (_, cardIndex) => makeCard(backSrc(), {
          alt: "Закрытая карта",
          key: `back:${seat.key}:${cardIndex}`,
        }));
    const place = pokerCardPlace(x, y);
    if (cards.length) {
      box.append(cardFan(cards, {
        x: place.x,
        y: place.y,
        role: seat.you ? "hero" : "opponent",
        angles: fanAngles(cards.length),
        overlap: fitOverlap(cards.length, seat.you ? 7.2 : 4.6, seat.you ? -2.2 : -1.8, seat.you ? 22 : 12),
      }));
    }
    if (Number(seat.bet) > 0) box.append(chipBet(seat.bet, inward(x, y, 0.5)));
    const plate = pokerPlatePlace(x, y);
    const badge = playerPlate(seat, plate.x, plate.y);
    badge.classList.add(`is-${plate.side}`);
    box.append(badge);
    placePurse(box, plate, place, x, y, seat.stack);
  });
  const board = Array.isArray(current.board) ? current.board : [];
  if (board.length) {
    const dealer = document.createElement("div");
    dealer.className = "uno-badge";
    dealer.textContent = "Дилер";
    box.append(anchor(dealer, 50, 16, "uno-badges"));
    board.forEach((card, index) => {
      const hidden = Boolean(current.hole) && index > 0;
      const node = makeCard(hidden ? backSrc() : faceSrc(card), {
        alt: hidden ? "Закрытая карта" : cardLabel(card),
        key: hidden ? `hole:${index}` : `table:${card}`,
      });
      node.classList.add("center-card");
      const x = 50 + (index - (board.length - 1) / 2) * 8;
      box.append(anchor(node, x, 36, node.className));
    });
  }
  paintTableAdvice(box, 52);
}

function paintDurakStock(box) {
  const deck = Number(current.deck || 0);
  const code = current.trump_card;
  if (!code || deck <= 0) return;
  if (deck === 1) {
    const trump = makeCard(faceSrc(code), { alt: `Козырь ${cardLabel(code)}` });
    box.append(anchor(trump, 16, 44, "trump-card"));
    return;
  }
  const trump = makeCard(faceSrc(code), { alt: `Козырь ${cardLabel(code)}` });
  box.append(anchor(trump, 12, 44, "trump-laid"));
  if (deck > 2) {
    const under = makeCard(backSrc(), { alt: "" });
    box.append(anchor(under, 19, 46, "stock-deck is-under"));
  }
  const top = makeCard(backSrc(), { alt: "Колода", key: "deck:top" });
  top.classList.add("deck-top");
  box.append(anchor(top, 19, 44, "stock-deck"));
}

function paintTableAdvice(box, y, extra = "") {
  const advice = document.createElement("p");
  advice.className = "table-advice";
  advice.textContent = status?.textContent || current.status_line || "";
  box.append(anchor(advice, 50, y, `table-advice${extra}`));
}

function paintSalonPlayers(box, heroCards) {
  const seats = orderedSeats(
    (Array.isArray(current.seats) && current.seats.length)
      ? current.seats
      : pokerRoster(box.dataset.you || "Вы"),
  );
  const spots = RINGS[seats.length] || RINGS[3];
  seats.forEach((seat, index) => {
    const spot = spots[index] || [50, 50];
    const place = salonCardPlace(spot[0], spot[1]);
    let fanY = seat.you ? Math.min(place.y, 86) : place.y;
    if (!seat.you && current.game_type === "preferans" && spot[1] <= 22) fanY += 4;
    if (seat.you) {
      if (heroCards.length) {
        box.append(cardFan(heroCards, {
          x: place.x,
          y: fanY,
          role: "hero",
          angles: fanAngles(heroCards.length),
          overlap: fitOverlap(heroCards.length, 7.2, -2.2, 46),
        }));
      }
    } else {
      const count = Math.max(0, Number(seat.count || 0));
      const backs = Array.from({ length: count }, (_, cardIndex) => makeCard(backSrc(), {
        alt: "Рубашка",
        key: `back:${seat.key}:${cardIndex}`,
      }));
      if (backs.length) {
        box.append(cardFan(backs, {
          x: place.x,
          y: fanY,
          role: "opponent",
          angles: fanAngles(backs.length),
          overlap: fitOverlap(backs.length, 4.6, -1.8, 12),
        }));
      }
    }
    const plate = salonPlatePlace(spot[0], spot[1], { x: place.x, y: fanY }, seat.you);
    const badge = unoPlate(seat, plate.x, plate.y);
    if (plate.lift) badge.style.transform = `translate(-50%, calc(-50% - ${plate.lift}px))`;
    box.append(badge);
    if (current.game_type === "preferans") {
      const node = purseNode(seat.stack);
      if (node) {
        const purse = preferansPurseSpot(spot[0], spot[1], { x: place.x, y: fanY }, plate);
        box.append(anchor(node, purse.x, purse.y, "purse"));
      }
    }
  });
}

function paintSalonTable(box) {
  const held = Boolean(current.held);
  const pairs = current.pairs || [];
  if (current.game_type === "durak" && pairs.length) {
    const row = document.createElement("div");
    row.className = held ? "table-row is-held" : "table-row";
    const rowClass = row.className;
    for (const pair of pairs) {
      const pile = document.createElement("div");
      pile.className = "pair";
      pile.append(makeCard(faceSrc(pair.attack), { alt: cardLabel(pair.attack), key: `table:${pair.attack}` }));
      if (pair.defense) {
        const cover = makeCard(faceSrc(pair.defense), { alt: cardLabel(pair.defense), key: `table:${pair.defense}` });
        cover.classList.add("is-cover");
        pile.append(cover);
      }
      row.append(pile);
    }
    box.append(anchor(row, 50, 46, rowClass));
    return;
  }
  const board = current.board || [];
  board.forEach((card, index) => {
    const node = makeCard(faceSrc(card), { alt: cardLabel(card), key: `table:${card}` });
    node.classList.add("center-card");
    if (held) node.classList.add("is-held");
    const x = 50 + (index - (board.length - 1) / 2) * 9;
    box.append(anchor(node, x, 44, node.className));
  });
}

function dealTone(note) {
  const given = current.note_tone;
  if (given === "made" || given === "miss" || given === "draw") return given;
  const text = String(note || "").toLowerCase();
  if (text.includes("не взят")) return "miss";
  if (text.includes("взят") || text.includes("без розыгрыша")) return "made";
  return "draw";
}

function paintDealBadge() {
  document.querySelector("#deal-badge")?.remove();
  const sheet = current.sheet;
  if (current.game_type !== "preferans" || !current.note || sheet?.closed) return;
  const head = document.querySelector(".stage-head");
  if (!head) return;
  const badge = document.createElement("p");
  badge.id = "deal-badge";
  badge.className = `deal-badge is-${dealTone(current.note)}`;
  const kicker = document.createElement("span");
  kicker.textContent = "Прошлая сдача";
  badge.append(kicker, document.createTextNode(current.note));
  head.append(badge);
}

function paintPreferansSheet() {
  paintDealBadge();
  const old = document.querySelector("#pulya-board");
  const sheet = current.sheet;
  if (current.game_type !== "preferans" || !sheet || !Array.isArray(sheet.seats) || !sheet.seats.length) {
    old?.remove();
    return;
  }
  const table = pulyaTable(sheet, current.seats);
  let board = old;
  if (!board) {
    board = document.createElement("section");
    board.id = "pulya-board";
    board.className = "pulya-board";
    board.setAttribute("aria-live", "polite");
    board.setAttribute("aria-label", "Пуля");
  }
  const stage = document.querySelector(".table-stage");
  if (stage && board.previousElementSibling !== stage) stage.insertAdjacentElement("afterend", board);
  board.replaceChildren(table);
}

function paintSalon(box, heroCards) {
  if (current.game_type === "blackjack") {
    paintBlackjack(box, heroCards);
    return;
  }
  paintSalonPlayers(box, heroCards);
  paintSalonTable(box);
  if (current.game_type === "durak") paintDurakStock(box);
  paintTableAdvice(box, 30, current.game_type === "preferans" ? " is-top" : "");
}

function actionButton(move, extra = "") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `secondary${extra}`;
  button.textContent = move.notation;
  button.addEventListener("click", () => submit(move));
  return button;
}

const BID_SUITS = [
  ["S", "пики"],
  ["C", "трефы"],
  ["D", "бубны"],
  ["H", "черви"],
  ["NT", "без козыря"],
];

function bidLadder(moves) {
  const pad = document.createElement("div");
  pad.className = "bid-pad";
  const pass = moves.find((move) => move.path[1] === "pass");
  const miser = moves.find((move) => move.path[1] === "miser");
  const byLevel = new Map();
  for (const move of moves) {
    if (move.path.length < 3) continue;
    const level = String(move.path[1]);
    if (!byLevel.has(level)) byLevel.set(level, []);
    byLevel.get(level).push(move);
  }
  if (!byLevel.has(bidLevel)) bidLevel = "";
  const steps = document.createElement("div");
  steps.className = "bid-row";
  if (pass) steps.append(actionButton(pass));
  for (const level of byLevel.keys()) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `secondary is-bid${bidLevel === level ? " is-on" : ""}`;
    button.textContent = level;
    button.setAttribute("aria-pressed", bidLevel === level ? "true" : "false");
    button.setAttribute("aria-label", `Заказ ${level}`);
    button.addEventListener("click", () => {
      bidLevel = bidLevel === level ? "" : level;
      render();
    });
    steps.append(button);
  }
  if (miser) steps.append(actionButton(miser, " is-bid"));
  pad.append(steps);
  if (!bidLevel) return pad;
  const suits = document.createElement("div");
  suits.className = "bid-row";
  suits.setAttribute("aria-label", "Масть заказа");
  for (const [code, title] of BID_SUITS) {
    const move = byLevel.get(bidLevel).find((item) => item.path[2] === code);
    if (!move) continue;
    const button = actionButton(move, ` is-bid is-suit${code === "H" || code === "D" ? " is-red" : ""}`);
    button.textContent = title;
    button.setAttribute("aria-label", move.notation);
    suits.append(button);
  }
  pad.append(suits);
  return pad;
}

function salonDock(discardMoves, bidMoves, selected) {
  const dock = document.createElement("div");
  dock.className = "salon-dock";
  if (bidMoves.length) dock.append(bidLadder(bidMoves));
  if (discardMoves.length) {
    const drop = document.createElement("button");
    drop.type = "button";
    drop.className = "secondary";
    drop.textContent = "Сбросить выбранные";
    drop.addEventListener("click", () => {
      const ordered = (current.hand || []).filter((card) => selected.has(card));
      const move = discardMoves.find((item) => {
        const pair = item.path.slice(1);
        return pair.length === ordered.length && pair.every((card) => ordered.includes(card));
      });
      if (move) submit(move);
    });
    dock.append(drop);
  }
  const actRank = { take: 0, pass: 1, yes: 2, half: 3, no: 4, hit: 0, stand: 1, double: 2 };
  const acts = (current.legal_moves || []).filter((move) => !["play", "uno", "discard", "bid"].includes(move.path[0]));
  acts.sort((left, right) => (actRank[left.path[1]] ?? 5) - (actRank[right.path[1]] ?? 5));
  for (const move of acts) dock.append(actionButton(move));
  if (!dock.childElementCount) dock.hidden = true;
  return dock;
}

function renderCards() {
  const box = document.querySelector("#card-table");
  if (!box) return;
  const poker = current.game_type === "poker";
  const salon = ["durak", "blackjack", "preferans"].includes(current.game_type);
  const clothName = poker || current.game_type === "blackjack" ? "table-poker.png" : "table-uno.png";
  box.classList.toggle("oval", poker || current.game_type === "blackjack");
  box.classList.toggle("felt", clothName === "table-uno.png");
  box.replaceChildren();
  const cloth = document.createElement("img");
  cloth.className = "table-texture";
  cloth.alt = "";
  cloth.draggable = false;
  cloth.src = asset(`${TABLE}/${clothName}`);
  box.append(cloth);

  const you = box.dataset.you || "Вы";
  const yourSide = current.seat_color || current.your_side;
  const heroShown = shownSide(yourSide || "white");
  const heroCodes = (current.hand && current.hand.length) ? current.hand : heroShown;

  const drawMoves = poker
    ? (current.legal_moves || []).filter((move) => move.path[0] === "draw" && move.path[1] !== "-")
    : [];
  const discardMoves = salon
    ? (current.legal_moves || []).filter((move) => move.path[0] === "discard")
    : [];
  const bidMoves = salon
    ? (current.legal_moves || []).filter((move) => move.path[0] === "bid")
    : [];
  const selected = new Set();
  const seen = new Map();
  const heroCards = heroCodes.map((card) => {
    const count = (seen.get(card) || 0) + 1;
    seen.set(card, count);
    const wildCard = String(card).startsWith("W");
    const play = !poker && !discardMoves.length && !wildCard
      ? (current.legal_moves || []).find((move) => move.path[0] === "play" && move.path[1] === card)
      : null;
    const wild = !poker && wildCard && (current.legal_moves || []).some((move) => move.path[0] === "play" && move.path[1] === "W");
    const active = Boolean(play) || (wild && wildOpen);
    const node = makeCard(faceSrc(card), {
      alt: cardLabel(card),
      button: Boolean(play) || wild || drawMoves.length > 0 || discardMoves.length > 0,
      key: `hand:${card}#${count}`,
      active,
      onClick: play
        ? () => {
          wildOpen = false;
          submit(calledPlay(play));
        }
        : wild
          ? () => {
            wildOpen = !wildOpen;
            render();
          }
          : null,
    });
    if (drawMoves.length || discardMoves.length) {
      node.addEventListener("click", () => {
        const limit = discardMoves.length ? 2 : 3;
        if (selected.has(card)) selected.delete(card);
        else if (selected.size < limit) selected.add(card);
        node.classList.toggle("is-on", selected.has(card));
      });
    }
    return node;
  });

  if (poker) {
    paintPokerRing(box, heroCards);
  } else if (salon) {
    paintSalon(box, heroCards);
  } else {
    paintUnoRing(box, you, heroCards);
  }

  let actions = document.querySelector("#table-actions");
  if (!actions) {
    actions = document.createElement("div");
    actions.id = "table-actions";
    actions.className = "table-actions";
    box.insertAdjacentElement("afterend", actions);
  }
  actions.replaceChildren();
  paintPreferansSheet();
  if (salon) {
    box.append(salonDock(discardMoves, bidMoves, selected));
    return;
  }
  if (current.shown && Object.keys(current.shown).length) {
    const shown = document.createElement("p");
    shown.className = "showdown";
    const white = (current.shown.white || []).map(cardLabel).join(", ");
    const black = (current.shown.black || []).map(cardLabel).join(", ");
    shown.textContent = `Вскрыто. Белые: ${white}. Чёрные: ${black}.`;
    actions.append(shown);
  }
  if (drawMoves.length) {
    const exchange = document.createElement("button");
    exchange.type = "button";
    exchange.className = "secondary";
    exchange.textContent = "Обменять выбранные";
    exchange.addEventListener("click", () => {
      const ordered = (current.hand || []).filter((card) => selected.has(card));
      const key = ordered.length ? ordered.join(",") : "-";
      const move = current.legal_moves.find((item) => item.path[0] === "draw" && item.path[1] === key);
      if (move) submit(move);
    });
    actions.append(exchange);
  }
  const wager = poker
    ? (current.legal_moves || []).find((move) => move.min != null && move.max != null)
    : null;
  if (discardMoves.length) {
    const drop = document.createElement("button");
    drop.type = "button";
    drop.className = "secondary";
    drop.textContent = "Сбросить выбранные";
    drop.addEventListener("click", () => {
      const ordered = (current.hand || []).filter((card) => selected.has(card));
      const move = discardMoves.find((item) => {
        const pair = item.path.slice(1);
        return pair.length === ordered.length && pair.every((card) => ordered.includes(card));
      });
      if (move) submit(move);
    });
    actions.append(drop);
  }
  if (bidMoves.length > 6) {
    const picker = document.createElement("select");
    picker.setAttribute("aria-label", "Заказ");
    for (const move of bidMoves) {
      const option = document.createElement("option");
      option.value = move.notation;
      option.textContent = move.notation;
      picker.append(option);
    }
    const order = document.createElement("button");
    order.type = "button";
    order.className = "secondary";
    order.textContent = "Заказать";
    order.addEventListener("click", () => {
      const move = bidMoves.find((item) => item.notation === picker.value);
      if (move) submit(move);
    });
    actions.append(picker, order);
  }
  const buttons = (current.legal_moves || []).filter((move) => {
    if (move === wager) return false;
    if (move.path[0] === "play" || move.path[0] === "uno" || move.path[0] === "discard") return false;
    if (move.path[0] === "bid" && bidMoves.length > 6) return false;
    if (!poker && move.path[0] === "draw") return false;
    if (poker && move.path[0] === "draw" && move.path[1] !== "-") return false;
    return true;
  });
  const rank = { call: 0, check: 1, fold: 2 };
  buttons.sort((left, right) => (rank[left.path[1]] ?? 5) - (rank[right.path[1]] ?? 5));
  for (const move of buttons) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = move.notation;
    button.addEventListener("click", () => submit(move));
    actions.append(button);
  }
  if (wager) actions.append(raisePad(wager));
}

function render() {
  paintChrome();
  paintHistory();
  if (current.table === "go") {
    paintGo(current);
    return;
  }
  if (current.table === "cards") {
    renderCards();
    return;
  }
  document.querySelector("#table-actions")?.remove();
  const grid = rows();
  board.replaceChildren();
  document.querySelector("#ranks").replaceChildren();
  document.querySelector("#files").replaceChildren();
  const target = targets();
  const steps = nextSteps();
  const landings = new Set(steps.map((step) => step.landing));
  const victims = new Set(steps.flatMap((step) => step.victims));
  const flight = new Set();
  if (prefix.length && steps.length) {
    const from = prefix[prefix.length - 1];
    for (const step of steps) {
      for (const cell of between(from, step.landing)) {
        if (!cell.piece) flight.add(cell.square);
      }
    }
  }
  const mover = prefix.length > 1 ? cellBy(prefix[0]) : null;
  grid.forEach((row, rowIndex) => {
    const rankLabel = document.createElement("span");
    rankLabel.textContent = String(row[0].rank + 1);
    document.querySelector("#ranks").append(rankLabel);
    row.forEach((cell, column) => {
      if (rowIndex === grid.length - 1) {
        const fileLabel = document.createElement("span");
        fileLabel.textContent = files[cell.file];
        document.querySelector("#files").append(fileLabel);
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = `sq${cell.dark ? " sq-dark" : ""}`;
      button.dataset.square = cell.square;
      button.setAttribute("role", "gridcell");
      button.setAttribute("aria-label", cell.aria);
      button.id = `sq-${cell.square}`;
      if ((current.last_move || []).includes(cell.square)) button.classList.add("sq-last");
      if (hintPath.includes(cell.square)) button.classList.add("sq-hint");
      if (prefix.includes(cell.square)) button.classList.add("sq-selected");
      if (current.game_type === "checkers" && prefix.length) {
        if (landings.has(cell.square)) button.classList.add("sq-target");
        else if (victims.has(cell.square)) button.classList.add("sq-capture");
        else if (flight.has(cell.square)) button.classList.add("sq-flight");
      } else if (target.has(cell.square)) button.classList.add(cell.piece ? "sq-capture" : "sq-target");
      if (current.check_square === cell.square) button.classList.add("sq-check");
      if (rowIndex * 8 + column === cursor) board.setAttribute("aria-activedescendant", button.id);
      let shown = cell.piece ? { piece: cell.piece, color: cell.color } : null;
      if (mover?.piece) {
        if (cell.square === prefix[0]) shown = null;
        if (cell.square === prefix[prefix.length - 1] && !cell.piece) shown = { piece: mover.piece, color: mover.color };
      }
      if (shown) button.append(pieceSvg(shown.piece, shown.color));
      button.addEventListener("click", () => {
        if (skipClick) return;
        choose(cell.square);
      });
      button.addEventListener("pointerdown", (event) => startDrag(event, cell.square));
      board.append(button);
    });
  });
}

function choose(square) {
  if (!current.can_move || busy || preview !== null) return;
  if (current.game_type === "checkers" && prefix.length) {
    const steps = nextSteps();
    const through = steps.filter((step) => step.victims.includes(square));
    if (through.length && !steps.some((step) => step.landing === square)) {
      const landings = [...new Set(through.map((step) => step.landing))];
      if (landings.length === 1) {
        captureFocus = null;
        choose(landings[0]);
        return;
      }
      captureFocus = square;
      render();
      say("Выберите поле за этой шашкой.");
      return;
    }
  }
  if (!prefix.length) {
    const starts = current.legal_moves.some((move) => move.path[0] === square);
    if (!starts) return;
    captureFocus = null;
    prefix = [square];
    render();
    return;
  }
  const next = prefix.concat(square);
  const matching = current.legal_moves.filter((move) => next.every((value, index) => move.path[index] === value));
  if (!matching.length) {
    captureFocus = null;
    prefix = current.legal_moves.some((move) => move.path[0] === square) ? [square] : [];
    render();
    return;
  }
  captureFocus = null;
  const finished = matching.filter((move) => move.path.length === next.length);
  const allComplete = matching.every((move) => move.path.length === next.length);
  if (finished.length && allComplete) {
    if (finished.some((move) => move.promotion)) {
      askPromotion(finished).then((move) => move && submit(move));
      return;
    }
    submit(finished[0]);
    return;
  }
  prefix = next;
  render();
}

function askPromotion(options) {
  const side = current.side_to_move === "black" ? "black" : "white";
  dialog.querySelectorAll("[data-piece]").forEach((button) => {
    button.querySelector("img")?.setAttribute("src", pieceSrc(button.dataset.piece, side));
  });
  dialog.showModal();
  return new Promise((resolve) => {
    const onClick = (event) => {
      const button = event.target.closest("button");
      const piece = button?.dataset?.piece;
      if (!piece && button?.id !== "promotion-cancel") return;
      dialog.close();
      dialog.removeEventListener("click", onClick);
      resolve(piece ? options.find((move) => move.promotion === piece) : null);
    };
    dialog.addEventListener("click", onClick);
  });
}

function calledPlay(move) {
  if (!unoArmed || current.game_type !== "uno" || (current.hand || []).length !== 2) return move;
  if (move.path[0] !== "play" || move.path.at(-1) === "uno") return move;
  return { ...move, path: [...move.path, "uno"] };
}

function submit(move) {
  const job = moveChain.then(() => sendMove(move));
  moveChain = job.catch(() => {});
  return job;
}

async function sendMove(move) {
  busy = true;
  render();
  let note = "";
  try {
    const data = await post(`/api/v1/games/${current.id}/moves`, {
      version: current.version,
      path: move.path,
      promotion: move.promotion,
    });
    await apply(data.state);
    note = data.engine_error || "";
  } catch (error) {
    note = error.message;
    await refresh();
  } finally {
    busy = false;
    prefix = [];
    hintPath = [];
    captureFocus = null;
    render();
    if (note) say(note);
  }
  maybeEngine();
}

let motionQueue = Promise.resolve();

function apply(next) {
  const job = motionQueue.then(() => present(next));
  motionQueue = job.catch(() => {});
  return job;
}

async function present(next) {
  const plan = motionPlan(current, next);
  const shot = plan ? snapshotMotion(plan) : null;
  const cards = next.table === "cards" && current.table === "cards" && next.version !== current.version
    ? rememberCards()
    : null;
  const spoken = next.moves?.at(-1);
  const added = (next.moves?.length || 0) > (current.moves?.length || 0);
  const changed = next.version !== current.version || next.status !== current.status;
  current = next;
  if (guestTurned) current.black_at_bottom = !current.black_at_bottom;
  if ((current.hand || []).length !== 2 || !current.your_turn || current.status !== "active" || current.game_type !== "uno") {
    unoArmed = false;
  }
  if (changed) {
    prefix = [];
    hintPath = [];
    preview = null;
    captureFocus = null;
    wildOpen = false;
    bidLevel = "";
  }
  render();
  const engineMove = added && spoken?.by === "engine" && (shot || cards || next.table === "go");
  if (engineMove) {
    const who = computerSpeaker();
    say(who ? `${who}: ${spoken.algebraic || spoken.notation || "ход"}` : (spoken.algebraic || spoken.notation || "ход"));
  }
  if (shot) await runMotion(shot);
  if (cards) await flipCards(cards);
  if (engineMove) say(current.status_line);
}

async function refresh() {
  const response = await fetch(`/api/v1/games/${current.id}`, { headers: { Accept: "application/json" } });
  if (response.ok) await apply(await response.json());
}

async function act(path, body, key) {
  if (busy) return;
  busy = true;
  let note = "";
  try {
    const data = await post(`/api/v1/games/${current.id}/${path}`, body);
    if (key === "hint") {
      if (data.version !== current.version) {
        await refresh();
        note = "Позиция уже изменилась.";
        return;
      }
      hintPath = data.lines?.[0]?.path || [];
      const box = document.querySelector("#lines");
      box.replaceChildren();
      for (const line of data.lines || []) {
        const row = document.createElement("p");
        row.className = "engine-line";
        const score = document.createElement("span");
        score.className = "score";
        const value = line.score_white;
        score.textContent = typeof value === "number" && value > 0 ? `+${value}` : String(value ?? "");
        const text = document.createElement("span");
        text.textContent = line.notation || "";
        row.append(score, text);
        box.append(row);
      }
      render();
      return;
    }
    if (key === "save") {
      note = "Партия сохранена.";
      return;
    }
    await apply(data.state || data);
  } catch (error) {
    note = error.message;
  } finally {
    busy = false;
    render();
    if (note) say(note);
    if (key !== "hint" && key !== "save" && !(key === "engine-move" && note)) maybeEngine();
  }
}

function squareBox(square) {
  const node = board.querySelector(`#sq-${CSS.escape(String(square))}`);
  if (!node) return null;
  const root = board.getBoundingClientRect();
  const rect = node.getBoundingClientRect();
  return { x: rect.left - root.left, y: rect.top - root.top, w: rect.width, h: rect.height };
}

function motionPlan(prev, next) {
  if (!prev || prev.table === "cards" || next.table === "cards" || reducedMotion() || document.hidden) return null;
  const path = (next.last_move || []).map(String);
  if (path.length < 2 || next.version === prev.version) return null;
  const origin = cellBy(path[0], prev.cells);
  if (!origin?.piece) return null;
  const slides = [{ path, piece: origin.piece, color: origin.color }];
  if (prev.game_type === "chess" && path.length === 2) {
    const from = cellBy(path[0], prev.cells);
    const to = cellBy(path[1], prev.cells);
    if (from && to && origin.piece === "K" && Math.abs(to.file - from.file) === 2) {
      const rookFile = to.file > from.file ? 7 : 0;
      const rookTo = to.file > from.file ? 5 : 3;
      const rook = (prev.cells || []).find((cell) => cell.rank === from.rank && cell.file === rookFile && cell.piece === "R" && cell.color === origin.color);
      const dest = (prev.cells || []).find((cell) => cell.rank === from.rank && cell.file === rookTo);
      if (rook && dest) slides.push({ path: [rook.square, dest.square], piece: "R", color: origin.color });
    }
  }
  const victims = [];
  for (const slide of slides) {
    for (let index = 1; index < slide.path.length; index += 1) {
      for (const cell of between(slide.path[index - 1], slide.path[index], prev.cells)) {
        if (cell.piece && cell.color !== slide.color) {
          victims.push({ square: cell.square, piece: cell.piece, color: cell.color, step: index, owner: slide.path[0] });
        }
      }
    }
  }
  if (prev.game_type === "chess") {
    for (const cell of prev.cells || []) {
      if (!cell.piece) continue;
      if (slides.some((slide) => slide.path[0] === cell.square)) continue;
      const stayed = (next.cells || []).some((item) => item.square === cell.square && item.piece);
      if (!stayed && !victims.some((victim) => victim.square === cell.square)) {
        victims.push({ square: cell.square, piece: cell.piece, color: cell.color, step: 1, owner: slides[0].path[0] });
      }
    }
  }
  return { slides, victims };
}

function snapshotMotion(plan) {
  const slides = plan.slides.map((slide) => ({ ...slide, steps: slide.path.map((square) => squareBox(square)) }));
  if (slides.some((slide) => slide.steps.some((box) => !box))) return null;
  const victims = plan.victims.map((victim) => ({ ...victim, at: squareBox(victim.square) })).filter((victim) => victim.at);
  return { slides, victims };
}

function hopDuration(from, to) {
  const squares = from.w ? Math.max(1, Math.round(Math.max(Math.abs(to.x - from.x), Math.abs(to.y - from.y)) / from.w)) : 1;
  return 260 + squares * 80;
}

async function glide(layer, slide, victims) {
  const ghost = pieceSvg(slide.piece, slide.color);
  ghost.classList.add("piece-flight");
  const first = slide.steps[0];
  ghost.style.width = `${first.w}px`;
  ghost.style.height = `${first.h}px`;
  ghost.style.transform = `translate(${first.x}px, ${first.y}px)`;
  layer.append(ghost);
  for (let index = 1; index < slide.steps.length; index += 1) {
    const from = slide.steps[index - 1];
    const to = slide.steps[index];
    for (const victim of victims.filter((item) => item.owner === slide.path[0] && item.step === index)) {
      const mark = pieceSvg(victim.piece, victim.color);
      mark.classList.add("piece-flight");
      mark.style.width = `${victim.at.w}px`;
      mark.style.height = `${victim.at.h}px`;
      mark.style.transform = `translate(${victim.at.x}px, ${victim.at.y}px)`;
      layer.append(mark);
      mark.animate(
        [
          { opacity: 1, transform: `translate(${victim.at.x}px, ${victim.at.y}px) scale(1)` },
          { opacity: 0, transform: `translate(${victim.at.x}px, ${victim.at.y}px) scale(0.72)` },
        ],
        { duration: 220, easing: "ease-in", fill: "forwards" },
      );
    }
    const anim = ghost.animate(
      [
        { transform: `translate(${from.x}px, ${from.y}px)` },
        { transform: `translate(${to.x}px, ${to.y}px)` },
      ],
      { duration: hopDuration(from, to), easing: "cubic-bezier(.22,.7,.2,1)", fill: "forwards" },
    );
    await anim.finished.catch(() => {});
    ghost.style.transform = `translate(${to.x}px, ${to.y}px)`;
  }
}

async function runMotion(shot) {
  const hidden = [];
  for (const slide of shot.slides) {
    const dest = board.querySelector(`#sq-${CSS.escape(slide.path.at(-1))} .piece`);
    if (dest) {
      dest.classList.add("is-quiet");
      hidden.push(dest);
    }
  }
  const layer = document.createElement("div");
  layer.className = "flight-layer";
  board.append(layer);
  try {
    await Promise.all(shot.slides.map((slide) => glide(layer, slide, shot.victims)));
  } finally {
    layer.remove();
    for (const node of hidden) node.classList.remove("is-quiet");
  }
}

function cardShot(node) {
  const rect = node.getBoundingClientRect();
  const img = node.tagName === "IMG" ? node : node.querySelector("img");
  return { left: rect.left, top: rect.top, width: rect.width, height: rect.height, src: img?.currentSrc || img?.src || "" };
}

function rememberCards() {
  const boxes = new Map();
  document.querySelectorAll("[data-card]").forEach((node) => {
    boxes.set(node.dataset.card, cardShot(node));
  });
  const deck = document.querySelector(".deck-top");
  boxes.set("__deck", deck ? cardShot(deck) : null);
  return boxes;
}

function earlierCard(before, key) {
  const direct = before.get(key);
  if (direct) return { shot: direct, source: key };
  const code = key.startsWith("table:") ? key.slice(6) : key.startsWith("pile:") ? key.slice(5) : "";
  if (code) {
    const fromHand = [...before.entries()].find(([name]) => name.startsWith(`hand:${code}#`) || name === `table:${code}`);
    if (fromHand) return { shot: fromHand[1], source: fromHand[0] };
  }
  if (key.startsWith("hand:") || key.startsWith("back:")) return { shot: before.get("__deck"), source: "__deck" };
  return { shot: null, source: "" };
}

async function flipCards(before) {
  if (reducedMotion()) return;
  const jobs = [];
  const seen = new Set();
  document.querySelectorAll("[data-card]").forEach((node) => {
    const key = node.dataset.card;
    seen.add(key);
    const found = earlierCard(before, key);
    if (found.source) seen.add(found.source);
    const prev = found.shot;
    const next = node.getBoundingClientRect();
    if (!prev || !next.width) {
      node.animate(
        [{ opacity: 0, transform: "translateY(-18px) scale(0.94)" }, { opacity: 1, transform: "none" }],
        { duration: 420, easing: "cubic-bezier(.16,.84,.24,1)" },
      );
      return;
    }
    const dx = prev.left - next.left;
    const dy = prev.top - next.top;
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
    jobs.push(node.animate(
      [
        { transform: `translate(${dx}px, ${dy}px) scale(0.96)` },
        { transform: "translate(0, 0) scale(1)" },
      ],
      { duration: 620, easing: "cubic-bezier(.16,.84,.24,1)" },
    ).finished.catch(() => {}));
  });
  const host = document.querySelector("#card-table");
  if (host) {
    const hostRect = host.getBoundingClientRect();
    for (const [key, prev] of before) {
      if (!prev?.width || seen.has(key) || key === "__deck" || key === "deck:top") continue;
      if (!key.startsWith("table:") && !key.startsWith("hand:") && !key.startsWith("pile:")) continue;
      if (!prev.src) continue;
      const ghost = document.createElement("img");
      ghost.className = "card card-ghost";
      ghost.alt = "";
      ghost.src = prev.src;
      ghost.style.left = `${prev.left - hostRect.left}px`;
      ghost.style.top = `${prev.top - hostRect.top}px`;
      ghost.style.width = `${prev.width}px`;
      host.append(ghost);
      jobs.push(ghost.animate(
        [
          { opacity: 1, transform: "translate(0, 0) scale(1)" },
          { opacity: 0, transform: "translate(0, 28px) scale(0.8)" },
        ],
        { duration: 720, easing: "cubic-bezier(.4,0,.2,1)", fill: "forwards" },
      ).finished.catch(() => {}).finally(() => ghost.remove()));
    }
  }
  await Promise.all(jobs);
}

function startDrag(event, square) {
  if (!current.can_move || busy || !event.target.closest(".sq")?.querySelector(".piece")) return;
  dragFrom = square;
}

let dragFrom = null;
board.addEventListener("pointerup", (event) => {
  if (!dragFrom) return;
  const from = dragFrom;
  dragFrom = null;
  const element = document.elementFromPoint(event.clientX, event.clientY);
  const target = element?.closest?.(".sq")?.dataset.square;
  if (!target || target === from) return;
  skipClick = true;
  window.setTimeout(() => { skipClick = false; }, 40);
  if (!(prefix.length && prefix[prefix.length - 1] === from)) {
    prefix = [from];
    captureFocus = null;
  }
  choose(target);
});

board.addEventListener("keydown", (event) => {
  const key = event.key;
  if (key === "Escape") {
    prefix = [];
    hintPath = [];
    captureFocus = null;
    render();
    return;
  }
  if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(key)) {
    event.preventDefault();
    const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -8, ArrowDown: 8 }[key];
    cursor = Math.max(0, Math.min(63, cursor + delta));
    render();
    return;
  }
  if (key === "Enter") {
    const cells = rows().flat();
    choose(cells[cursor].square);
  }
});

document.querySelector("#rematch")?.addEventListener("click", () => offerRematch());
document.querySelector("#rematch-accept")?.addEventListener("click", () => offerRematch());
document.querySelector("#rematch-decline")?.addEventListener("click", () => declineRematch());
document.querySelector("#hint")?.addEventListener("click", () => act("hint", { version: current.version }, "hint"));
const summaryDialog = document.querySelector("#poker-summary");
summaryDialog?.addEventListener("close", rememberSummary);
summaryDialog?.addEventListener("click", (event) => {
  if (event.target === summaryDialog) summaryDialog.close();
});
summaryDialog?.querySelector("#summary-finish")?.addEventListener("click", () => {
  rememberSummary();
  window.location.assign("/");
});
summaryDialog?.querySelector("#summary-again")?.addEventListener("click", () => {
  rememberSummary();
  summaryDialog.close();
  offerRematch();
});
const ranksDialog = document.querySelector("#poker-ranks");
ranksDialog?.querySelector("[data-close]")?.addEventListener("click", () => ranksDialog.close());
ranksDialog?.addEventListener("click", (event) => {
  if (event.target === ranksDialog) ranksDialog.close();
});
document.querySelector("#engine-move")?.addEventListener("click", () => act("engine-move", { version: current.version }));
document.querySelector("#undo")?.addEventListener("click", () => act("undo", { version: current.version }));
function ask({ title, text, accept, tone }) {
  const dialog = document.querySelector("#confirm-dialog");
  const heading = document.querySelector("#confirm-title");
  const body = document.querySelector("#confirm-text");
  const ok = document.querySelector("#confirm-ok");
  const cancel = document.querySelector("#confirm-cancel");
  if (!dialog || !ok || !cancel || dialog.open) return Promise.resolve(false);
  heading.textContent = title;
  body.textContent = text;
  ok.textContent = accept;
  ok.classList.toggle("is-danger", tone === "danger");
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      ok.removeEventListener("click", onOk);
      cancel.removeEventListener("click", onCancel);
      dialog.removeEventListener("close", onClose);
      dialog.removeEventListener("click", onBackdrop);
      if (dialog.open) dialog.close();
      resolve(value);
    };
    const onOk = () => finish(true);
    const onCancel = () => finish(false);
    const onClose = () => finish(false);
    const onBackdrop = (event) => {
      if (event.target === dialog) finish(false);
    };
    ok.addEventListener("click", onOk);
    cancel.addEventListener("click", onCancel);
    dialog.addEventListener("close", onClose);
    dialog.addEventListener("click", onBackdrop);
    dialog.showModal();
  });
}

document.querySelector("#end-game")?.addEventListener("click", async () => {
  const cards = current.table === "cards";
  const accepted = await ask({
    title: cards ? "Выйти из-за стола" : "Сдаться",
    text: cards ? "Партия закончится." : "Победа будет засчитана сопернику.",
    accept: cards ? "Выйти" : "Сдаться",
    tone: "danger",
  });
  if (!accepted) return;
  act("resign", { version: current.version });
});
document.querySelector("#stop-game")?.addEventListener("click", async () => {
  if (busy || current.status === "finished") return;
  const accepted = await ask({
    title: "Остановить партию",
    text: current.waiting
      ? "Никто больше не сядет за этот стол."
      : "Победителя не будет, стол просто закроется.",
    accept: "Остановить",
  });
  if (!accepted) return;
  act("stop", { version: current.version });
});
document.querySelector("#flip")?.addEventListener("click", () => {
  if (current.watching) {
    guestTurned = !guestTurned;
    current.black_at_bottom = !current.black_at_bottom;
    render();
    return;
  }
  act("orientation", {});
});
document.querySelector("#watchers")?.addEventListener("click", () => {
  paintWatchers();
  document.querySelector("#watcher-dialog")?.showModal();
});
document.querySelector("#watcher-close")?.addEventListener("click", () => {
  document.querySelector("#watcher-dialog")?.close();
});
document.querySelector("#save")?.addEventListener("click", () => act("save", {}, "save"));
document.querySelector("#continue")?.addEventListener("click", () => {
  preview = null;
  prefix = [];
  render();
});
function inviteDismissed() {
  if (!current?.id) return false;
  try {
    return sessionStorage.getItem(`invite-off:${current.id}`) === "1";
  } catch {
    return false;
  }
}

document.querySelector("#copy-code")?.addEventListener("click", async () => {
  const code = document.querySelector("#join-code")?.textContent || "";
  const button = document.querySelector("#copy-code");
  const tip = button?.parentElement?.querySelector(".tip");
  try {
    await navigator.clipboard.writeText(code);
    say("Код скопирован.");
    if (tip) tip.textContent = "Скопировано";
    const icon = button?.querySelector("use");
    icon?.setAttribute("href", "#i-check");
    window.setTimeout(() => {
      if (tip) tip.textContent = "Скопировать код";
      icon?.setAttribute("href", "#i-copy");
    }, 1400);
  } catch {
    say(`Код приглашения: ${code}`);
  }
});

document.querySelector("#invite-close")?.addEventListener("click", () => {
  try {
    sessionStorage.setItem(`invite-off:${current.id}`, "1");
  } catch {
    /* закрытие всё равно скроет полоску в этой вкладке */
  }
  const invite = document.querySelector("#invite");
  if (invite) invite.hidden = true;
});

const inviteDialog = document.querySelector("#invite-dialog");
const inviteForm = document.querySelector("#invite-form");
const inviteQuery = document.querySelector("#invite-query");
const inviteResults = document.querySelector("#invite-results");
const inviteEmpty = document.querySelector("#invite-empty");
const inviteSend = document.querySelector("#invite-send");
let invitePick = "";
let inviteTimer = 0;
let inviteSearch = 0;

function inviteReady() {
  if (inviteSend) inviteSend.disabled = !invitePick;
}

function paintInviteResults(players, query) {
  if (!inviteResults || !inviteQuery) return;
  inviteResults.replaceChildren();
  const known = players.some((player) => player.username === invitePick);
  if (!known) invitePick = "";
  for (const player of players) {
    const item = document.createElement("li");
    const choice = document.createElement("button");
    choice.type = "button";
    choice.setAttribute("role", "option");
    choice.dataset.username = player.username;
    if (player.username === invitePick) choice.classList.add("is-on");
    const name = document.createElement("span");
    const at = player.username.indexOf(query);
    if (at >= 0) {
      name.append(player.username.slice(0, at));
      const mark = document.createElement("mark");
      mark.textContent = player.username.slice(at, at + query.length);
      name.append(mark, player.username.slice(at + query.length));
    } else {
      name.textContent = player.username;
    }
    if (player.name && player.name !== player.username) {
      const full = document.createElement("span");
      full.className = "quiet";
      full.textContent = ` · ${player.name}`;
      name.append(full);
    }
    choice.append(name);
    if (player.live) {
      const live = document.createElement("span");
      live.className = "invite-live";
      live.textContent = "в сети";
      choice.append(live);
    }
    choice.addEventListener("click", () => {
      invitePick = player.username;
      inviteQuery.value = player.username;
      paintInviteResults(players, query);
      inviteReady();
    });
    item.append(choice);
    inviteResults.append(item);
  }
  const show = players.length > 0;
  inviteResults.hidden = !show;
  if (inviteEmpty) inviteEmpty.hidden = show || !query;
  inviteQuery.setAttribute("aria-expanded", show ? "true" : "false");
  inviteReady();
}

async function searchPlayers(query) {
  const ticket = ++inviteSearch;
  const response = await fetch(`/api/v1/players?q=${encodeURIComponent(query)}`, {
    headers: { Accept: "application/json" },
  });
  const data = await response.json().catch(() => ({}));
  if (ticket !== inviteSearch) return;
  paintInviteResults(Array.isArray(data.players) ? data.players : [], query);
}

document.querySelector("#invite-player")?.addEventListener("click", () => {
  if (!(inviteDialog instanceof HTMLDialogElement)) return;
  invitePick = "";
  inviteSearch += 1;
  if (inviteQuery) {
    inviteQuery.value = "";
    inviteQuery.setAttribute("aria-expanded", "false");
  }
  if (inviteResults) {
    inviteResults.replaceChildren();
    inviteResults.hidden = true;
  }
  if (inviteEmpty) inviteEmpty.hidden = true;
  inviteReady();
  inviteDialog.showModal();
  inviteQuery?.focus();
});

document.querySelector("#invite-cancel")?.addEventListener("click", () => {
  if (inviteDialog instanceof HTMLDialogElement) inviteDialog.close();
});
inviteDialog?.addEventListener("click", (event) => {
  if (event.target === inviteDialog && inviteDialog instanceof HTMLDialogElement) inviteDialog.close();
});
inviteQuery?.addEventListener("input", () => {
  const query = inviteQuery.value.trim().toLowerCase();
  if (invitePick && invitePick !== query) invitePick = "";
  inviteReady();
  window.clearTimeout(inviteTimer);
  if (!query) {
    inviteSearch += 1;
    paintInviteResults([], "");
    return;
  }
  inviteTimer = window.setTimeout(() => {
    searchPlayers(query).catch(() => paintInviteResults([], query));
  }, 160);
});
inviteForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!invitePick || !inviteSend) return;
  inviteSend.disabled = true;
  try {
    const data = await post(`/api/v1/games/${current.id}/invite`, { username: invitePick });
    if (inviteDialog instanceof HTMLDialogElement) inviteDialog.close();
    say(`Приглашение отправлено ${data.sent || invitePick}.`);
  } catch (error) {
    say(error.message);
    inviteReady();
  }
});

async function offerRematch() {
  if (busy) return;
  busy = true;
  try {
    const data = await post(`/api/v1/games/${current.id}/rematch`, {});
    if (data.game_id) {
      window.location.assign(`/games/${data.game_id}`);
      return;
    }
    current.rematch = data.rematch || current.rematch;
    render();
  } catch (error) {
    say(error.message);
  } finally {
    busy = false;
    paintRematch();
  }
}

async function declineRematch() {
  if (busy) return;
  busy = true;
  try {
    const data = await post(`/api/v1/games/${current.id}/rematch/decline`, {});
    current.rematch = data.rematch || current.rematch;
    render();
  } catch (error) {
    say(error.message);
  } finally {
    busy = false;
    paintRematch();
  }
}

let watchingLive = true;

function watchRoom() {
  return Boolean(current?.watching) && current.audience === "open"
    && (current.mode === "online" || current.mode === "vs_computer");
}

function arriveWatch() {
  if (!watchingLive || !watchRoom()) return;
  post(`/api/v1/games/${current.id}/watch/arrive`, {}).catch(() => {});
}

function beatWatch() {
  if (!watchingLive || !watchRoom()) return;
  post(`/api/v1/games/${current.id}/watch/arrive`, {}).catch(() => {});
}

function leaveWatch() {
  if (!watchRoom()) return;
  const body = new URLSearchParams({ csrf_token: token() });
  fetch(`/api/v1/games/${current.id}/watch/leave`, {
    method: "POST",
    keepalive: true,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  }).catch(() => {});
}

function keepWatchers() {
  if (!watchRoom()) return;
  arriveWatch();
  window.setInterval(beatWatch, 4000);
  window.addEventListener("pagehide", (event) => {
    if (event.persisted) return;
    leaveWatch();
  });
  window.addEventListener("pageshow", () => {
    watchingLive = true;
    arriveWatch();
  });
}

async function pollWatchers() {
  const open = current.audience === "open" && (current.mode === "online" || current.mode === "vs_computer");
  if (!open || document.hidden) return;
  try {
    const response = await fetch(`/api/v1/games/${current.id}/watchers`, { headers: { Accept: "application/json" } });
    if (!response.ok) return;
    const data = await response.json();
    if (watcherKey(data.watchers) === watcherKey(current.watchers)) return;
    current.watchers = Array.isArray(data.watchers) ? data.watchers : [];
    paintWatchers();
  } catch {
    /* следующий опрос повторит */
  }
}

async function poll() {
  if (!current.live || busy || document.hidden) return;
  try {
    const response = await fetch(`/api/v1/games/${current.id}`, { headers: { Accept: "application/json" } });
    if (!response.ok) return;
    const next = await response.json();
    const offerChanged = JSON.stringify(next.rematch || null) !== JSON.stringify(current.rematch || null);
    const watchersChanged = watcherKey(next.watchers) !== watcherKey(current.watchers);
    if (next.version !== current.version || next.status !== current.status || offerChanged) {
      const before = current.moves.length;
      await apply(next);
      if (next.moves.length !== before && next.moves.at(-1)?.by !== "engine") say(next.status_line);
    } else if (watchersChanged) {
      current.watchers = Array.isArray(next.watchers) ? next.watchers : [];
      paintWatchers();
    }
    const link = document.querySelector("#go-link");
    if (link && current.table === "go") link.textContent = "";
  } catch {
    const link = document.querySelector("#go-link");
    if (link && current.table === "go") link.textContent = "Нет связи. Ждём снимок партии.";
    say("Сетевая ошибка. Проверьте соединение и повторите действие.");
  }
}

const quietKey = "pn-quiet";
function applyQuiet() {
  document.body.classList.toggle("quiet-play", localStorage.getItem(quietKey) === "1");
}
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && document.querySelector(".side-panel.is-open")) {
    setDrawer("");
    return;
  }
  if (event.altKey && event.shiftKey && event.code === "KeyH") {
    event.preventDefault();
    localStorage.setItem(quietKey, localStorage.getItem(quietKey) === "1" ? "0" : "1");
    applyQuiet();
  }
});
applyQuiet();

function toneOf(name) {
  return [...String(name || "")].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 6;
}

const AVATAR_FILE = /^[0-9a-f]{32}\.(jpg|png|webp)$/;
const LOGIN_NAME = /^[a-z0-9_-]{3,32}$/;

function avatarChip(name, file) {
  if (AVATAR_FILE.test(String(file || ""))) {
    const image = document.createElement("img");
    image.className = "avatar";
    image.alt = "";
    image.src = `/avatars/${file}`;
    return image;
  }
  const span = document.createElement("span");
  span.className = `avatar tone-${toneOf(name)}`;
  span.textContent = String(name || "?").slice(0, 1).toUpperCase();
  return span;
}

function fillPersonName(node, seat) {
  const label = String(seat?.name || "");
  const login = String(seat?.login || "");
  node.replaceChildren();
  if (!LOGIN_NAME.test(login)) {
    node.textContent = label;
    return;
  }
  const link = document.createElement("a");
  link.className = "person-link";
  link.href = `/players/${login}`;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = label;
  node.append(link);
}

function plateFace(seat, cpu) {
  const face = document.createElement("span");
  face.className = "plate-face";
  if (cpu) {
    const image = document.createElement("img");
    image.alt = "компьютер";
    image.src = CPU_FACE;
    face.append(image);
  } else if (AVATAR_FILE.test(String(seat.avatar || ""))) {
    const image = document.createElement("img");
    image.alt = "";
    image.src = `/avatars/${seat.avatar}`;
    face.append(image);
  } else {
    face.textContent = String(seat.name || "?").slice(0, 1).toUpperCase();
  }
  return face;
}

function clock(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

let tableChatPager = null;

async function loadChat() {
  const log = document.querySelector("#chat-log");
  if (!log) return;
  const response = await fetch(`/api/v1/games/${current.id}/chat`, { headers: { Accept: "application/json" } });
  if (!response.ok) return;
  const data = await response.json();
  const stamp = JSON.stringify(data.messages || []);
  if (log.dataset.stamp === stamp) return;
  log.dataset.stamp = stamp;
  log.replaceChildren();
  for (const message of data.messages || []) {
    const item = document.createElement("li");
    item.className = "chat-line";
    item.dataset.pageRow = "1";
    const avatar = avatarChip(message.username, message.avatar);
    const body = document.createElement("div");
    const head = document.createElement("p");
    head.className = "chat-head";
    const who = document.createElement("strong");
    fillPersonName(who, { name: message.username, login: message.login });
    const time = document.createElement("time");
    time.textContent = clock(message.at);
    const text = document.createElement("p");
    text.textContent = message.body;
    head.append(who, time);
    body.append(head, text);
    item.append(avatar, body);
    log.append(item);
  }
  if (!tableChatPager) tableChatPager = attachPager(log, { size: 12, newest: true, label: "Страницы сообщений стола" });
  const shown = tableChatPager();
  if (shown.page === shown.pages) log.scrollTop = log.scrollHeight;
}

document.querySelector("#chat-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#chat-body");
  const body = input.value.trim();
  if (!body) return;
  await post(`/api/v1/games/${current.id}/chat`, { body });
  input.value = "";
  await loadChat();
});

const peers = new Map();
let localStream = null;
let callSocket = null;
let camOn = false;
let micOn = false;
let blurOn = false;

function sendSignal(message) {
  if (callSocket && callSocket.readyState === WebSocket.OPEN) callSocket.send(JSON.stringify(message));
}

function peerIdentity(id) {
  const roster = Array.isArray(current.call_roster) ? current.call_roster : [];
  const found = roster.find((item) => item && item.id === id);
  return {
    name: found?.name || current.opponent_name || "Игрок",
    login: found?.login || current.opponent_login || "",
  };
}

function peerName(id) {
  return peerIdentity(id).name;
}

function videoFor(id) {
  const box = document.querySelector("#call-tiles");
  if (!box) return null;
  let tile = box.querySelector(`[data-tile="${id}"]`);
  if (!tile) {
    tile = document.createElement("article");
    tile.className = "call-tile";
    tile.dataset.tile = id;
    const frame = document.createElement("div");
    frame.className = "tile-frame";
    const video = document.createElement("video");
    video.dataset.peer = id;
    video.autoplay = true;
    video.playsInline = true;
    const pin = document.createElement("button");
    pin.type = "button";
    pin.className = "tile-pin";
    pin.dataset.pin = id;
    pin.textContent = "Главное";
    const name = document.createElement("p");
    name.className = "tile-name";
    fillPersonName(name, peerIdentity(id));
    frame.append(video, pin);
    tile.append(frame, name);
    box.append(tile);
    applyFeature();
  }
  return tile.querySelector("video");
}

let featured = "";

function applyFeature() {
  const board = document.querySelector("#call-board");
  board?.classList.toggle("has-featured", Boolean(featured));
  for (const tile of document.querySelectorAll(".call-tile")) {
    const on = tile.dataset.tile === featured;
    tile.classList.toggle("is-featured", on);
    const pin = tile.querySelector(".tile-pin");
    if (pin) {
      pin.textContent = on ? "Обычный размер" : "Главное";
      pin.setAttribute("aria-pressed", on ? "true" : "false");
    }
  }
}

function feature(id) {
  featured = featured === id ? "" : id;
  applyFeature();
}

function makePeer(id) {
  const existing = peers.get(id);
  if (existing) return existing;
  const pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
  pc.onicecandidate = (event) => {
    if (event.candidate) sendSignal({ type: "signal", to: id, data: { kind: "ice", candidate: event.candidate } });
  };
  pc.ontrack = (event) => {
    const video = videoFor(id);
    if (!video) return;
    video.muted = false;
    video.srcObject = event.streams[0] || new MediaStream([event.track]);
    video.classList.add("is-live");
    video.play().catch(() => {});
  };
  peers.set(id, pc);
  return pc;
}

async function offerTo(id) {
  const pc = makePeer(id);
  if (localStream) {
    for (const track of localStream.getTracks()) {
      if (!pc.getSenders().some((sender) => sender.track === track)) pc.addTrack(track, localStream);
    }
  }
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  sendSignal({ type: "signal", to: id, data: { kind: "offer", sdp: pc.localDescription } });
}

async function onSignal(message) {
  if (message.type === "peers") {
    for (const id of message.ids || []) if (String(current.you) < String(id)) await offerTo(id);
    return;
  }
  if (message.type === "peer-joined") {
    if (String(current.you) < String(message.id)) await offerTo(message.id);
    return;
  }
  if (message.type === "peer-left") {
    peers.get(message.id)?.close();
    peers.delete(message.id);
    document.querySelector(`#call-tiles [data-tile="${message.id}"]`)?.remove();
    if (featured === message.id) feature("");
    return;
  }
  if (message.type !== "signal") return;
  const data = message.data || {};
  const pc = makePeer(message.from);
  if (data.kind === "offer") {
    if (pc.signalingState === "have-local-offer" && String(current.you) > String(message.from)) {
      await pc.setLocalDescription({ type: "rollback" });
    }
    await pc.setRemoteDescription(data.sdp);
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    sendSignal({ type: "signal", to: message.from, data: { kind: "answer", sdp: pc.localDescription } });
  } else if (data.kind === "answer") {
    await pc.setRemoteDescription(data.sdp);
  } else if (data.kind === "ice" && data.candidate) {
    await pc.addIceCandidate(data.candidate);
  }
}

let cameraStream = null;
let blurTimer = 0;
let sourceVideo = null;
const blurLayers = new Map();

function stopMedia() {
  if (blurTimer) cancelAnimationFrame(blurTimer);
  blurTimer = 0;
  const seen = new Set();
  for (const stream of [cameraStream, localStream]) {
    stream?.getTracks().forEach((track) => {
      if (seen.has(track)) return;
      seen.add(track);
      track.stop();
    });
  }
  cameraStream = null;
  localStream = null;
  if (sourceVideo) sourceVideo.srcObject = null;
}

function blurLayer(name, width, height) {
  let canvas = blurLayers.get(name);
  if (!canvas) {
    canvas = document.createElement("canvas");
    blurLayers.set(name, canvas);
  }
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  return canvas;
}

function paintBlur(video, canvas, mask) {
  const width = canvas.width;
  const height = canvas.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const soft = blurLayer("soft", width, height);
  const sharp = blurLayer("sharp", width, height);
  const softCtx = soft.getContext("2d");
  const sharpCtx = sharp.getContext("2d");
  if (!softCtx || !sharpCtx) return;
  softCtx.filter = "blur(18px)";
  softCtx.drawImage(video, 0, 0, width, height);
  softCtx.filter = "none";
  sharpCtx.clearRect(0, 0, width, height);
  sharpCtx.drawImage(video, 0, 0, width, height);
  sharpCtx.globalCompositeOperation = "destination-in";
  sharpCtx.save();
  sharpCtx.translate(mask.cx, mask.cy);
  sharpCtx.scale(mask.rx, mask.ry);
  const shade = sharpCtx.createRadialGradient(0, 0, 0.42, 0, 0, 1);
  shade.addColorStop(0, "rgba(0,0,0,1)");
  shade.addColorStop(0.78, "rgba(0,0,0,0.92)");
  shade.addColorStop(1, "rgba(0,0,0,0)");
  sharpCtx.fillStyle = shade;
  sharpCtx.beginPath();
  sharpCtx.arc(0, 0, 1, 0, Math.PI * 2);
  sharpCtx.fill();
  sharpCtx.restore();
  sharpCtx.globalCompositeOperation = "source-over";
  ctx.drawImage(soft, 0, 0);
  ctx.drawImage(sharp, 0, 0);
}

function faceMask(box, width, height, scaleX, scaleY) {
  const faceW = box.width * scaleX;
  const faceH = box.height * scaleY;
  const cx = (box.x + box.width / 2) * scaleX;
  const cy = (box.y + box.height * 0.35) * scaleY + faceH * 0.85;
  return {
    cx,
    cy,
    rx: Math.min(width * 0.48, Math.max(faceW * 1.35, width * 0.22)),
    ry: Math.min(height * 0.48, Math.max(faceH * 2.4, height * 0.28)),
  };
}

async function withBlur(raw) {
  if (!sourceVideo) {
    sourceVideo = document.createElement("video");
    sourceVideo.className = "call-source";
    sourceVideo.muted = true;
    sourceVideo.autoplay = true;
    sourceVideo.playsInline = true;
    document.body.append(sourceVideo);
  }
  sourceVideo.srcObject = new MediaStream(raw.getVideoTracks());
  await sourceVideo.play();
  const canvas = blurLayer("out", 640, 480);
  const stream = canvas.captureStream(15);
  for (const track of raw.getAudioTracks()) stream.addTrack(track);
  const detector = "FaceDetector" in window ? new FaceDetector({ fastMode: true, maxDetectedFaces: 1 }) : null;
  let lastMask = null;
  let looking = false;
  let seenAt = 0;
  const tick = (now) => {
    blurTimer = requestAnimationFrame(tick);
    if (!blurOn || sourceVideo.readyState < 2 || !sourceVideo.videoWidth) return;
    if (now - seenAt < 70) return;
    seenAt = now;
    const height = Math.max(1, Math.round(640 * sourceVideo.videoHeight / sourceVideo.videoWidth));
    if (canvas.width !== 640 || canvas.height !== height) {
      canvas.width = 640;
      canvas.height = height;
    }
    if (detector && !looking) {
      looking = true;
      detector.detect(sourceVideo).then((faces) => {
        const box = faces[0]?.boundingBox;
        lastMask = box
          ? faceMask(box, canvas.width, canvas.height, canvas.width / sourceVideo.videoWidth, canvas.height / sourceVideo.videoHeight)
          : null;
      }).catch(() => {
        lastMask = null;
      }).finally(() => {
        looking = false;
      });
    }
    paintBlur(sourceVideo, canvas, lastMask || { cx: canvas.width / 2, cy: canvas.height * 0.46, rx: canvas.width * 0.34, ry: canvas.height * 0.42 });
  };
  blurTimer = requestAnimationFrame(tick);
  return stream;
}

async function refreshMedia() {
  const status = document.querySelector("#call-status");
  try {
    stopMedia();
    if (!camOn && !micOn) {
      const self = document.querySelector("#self-video");
      if (self) {
        self.srcObject = null;
        self.classList.remove("is-live");
      }
      if (status) status.textContent = "Камера и микрофон выключены.";
      return;
    }
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: camOn ? { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } } : false,
      audio: micOn,
    });
    localStream = camOn && blurOn ? await withBlur(cameraStream) : cameraStream;
    const self = document.querySelector("#self-video");
    self.srcObject = localStream;
    self.muted = true;
    self.classList.toggle("is-live", localStream.getVideoTracks().some((track) => track.readyState === "live"));
    await self.play().catch(() => {});
    for (const id of peers.keys()) await offerTo(id);
    if (status) {
      status.textContent = blurOn && camOn
        ? "Фон размыт. Связь идёт напрямую между браузерами."
        : "Связь включена на этом устройстве.";
    }
  } catch {
    if (status) status.textContent = "Камера или микрофон не разрешены в браузере.";
  }
}

function startCall() {
  if (!current.in_call || !document.querySelector("#table-call")) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  callSocket = new WebSocket(`${proto}://${location.host}/ws/tables/${current.id}`);
  callSocket.onmessage = (event) => {
    onSignal(JSON.parse(event.data)).catch(() => {});
  };
}

document.querySelector("#cam")?.addEventListener("click", () => {
  camOn = !camOn;
  document.querySelector("#cam")?.classList.toggle("is-on", camOn);
  document.querySelector("#cam")?.setAttribute("aria-pressed", camOn ? "true" : "false");
  refreshMedia();
});
document.querySelector("#mic")?.addEventListener("click", () => {
  micOn = !micOn;
  document.querySelector("#mic")?.classList.toggle("is-on", micOn);
  document.querySelector("#mic")?.setAttribute("aria-pressed", micOn ? "true" : "false");
  refreshMedia();
});
document.querySelector("#blur")?.addEventListener("click", () => {
  blurOn = !blurOn;
  document.querySelector("#blur")?.classList.toggle("is-on", blurOn);
  document.querySelector("#blur")?.setAttribute("aria-pressed", blurOn ? "true" : "false");
  if (camOn) refreshMedia();
});
document.querySelector("#call-board")?.addEventListener("click", (event) => {
  const tile = event.target instanceof Element ? event.target.closest(".call-tile") : null;
  if (!tile) return;
  feature(tile.dataset.tile || "");
});

let engineTicket = 0;
function maybeEngine() {
  const ticket = ++engineTicket;
  const scoring = current.table === "go" && current.status === "scoring";
  const auto = current.can_engine && !busy
    && (scoring || (current.status === "active" && (current.mode === "vs_computer" || current.computer_turn)));
  if (!auto) return;
  window.setTimeout(() => {
    if (ticket !== engineTicket || busy || !current.can_engine) return;
    const still = current.table === "go" && current.status === "scoring";
    if (!still && current.status !== "active") return;
    act("engine-move", { version: current.version });
  }, 480);
}

function setDrawer(name) {
  const open = name || "";
  for (const panel of document.querySelectorAll(".side-panel")) {
    const on = panel.dataset.drawer === open;
    panel.classList.toggle("is-open", on);
    panel.setAttribute("aria-hidden", on ? "false" : "true");
  }
  document.querySelector("#notes-backdrop")?.classList.toggle("is-open", Boolean(open));
  for (const button of document.querySelectorAll("[data-drawer-open]")) {
    button.setAttribute("aria-expanded", button.dataset.drawerOpen === open ? "true" : "false");
  }
}
document.querySelector(".play")?.addEventListener("click", (event) => {
  if (!(event.target instanceof Element)) return;
  const open = event.target.closest("[data-drawer-open]");
  if (open instanceof HTMLElement) {
    const name = open.dataset.drawerOpen || "";
    const already = document.querySelector(`.side-panel[data-drawer="${name}"]`)?.classList.contains("is-open");
    setDrawer(already ? "" : name);
    return;
  }
  if (event.target.closest("[data-drawer-close]") || event.target.closest("#notes-backdrop")) setDrawer("");
});

bindGo({
  post,
  say,
  apply,
  ask,
  refresh,
  getState: () => current,
  getBusy: () => busy,
  setBusy(value) {
    busy = value;
  },
  onSettled() {
    maybeEngine();
  },
});
render();
maybeEngine();
setInterval(poll, 1500);
setInterval(pollWatchers, 2000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) pollWatchers();
});
keepWatchers();
if (current.mode !== "vs_computer") {
  setInterval(() => loadChat().catch(() => {}), 2000);
  loadChat().catch(() => {});
}
startCall();
