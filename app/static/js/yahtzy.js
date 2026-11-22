let reeling = false;
let api = null;
let gameId = "";
let picked = "";
let ready = false;
let shownPly = 0;
let shownFaces = null;
let reelPly = 0;
let gate = Promise.resolve();
const holds = new Set();
let pendingHeld = null;

const UPPER = [
  ["ones", 1, "Единицы"],
  ["twos", 2, "Двойки"],
  ["threes", 3, "Тройки"],
  ["fours", 4, "Четвёрки"],
  ["fives", 5, "Пятёрки"],
  ["sixes", 6, "Шестёрки"],
];
const LOWER = [
  ["three", "Три одинаковых"],
  ["four", "Четыре одинаковых"],
  ["house", "Фул-хаус 25"],
  ["small", "Малый стрит 30"],
  ["large", "Большой стрит 40"],
  ["yahtzy", "Яцзы 50"],
  ["chance", "Шанс"],
];
const SPIN_MS = 1380;
const STAGGER_MS = 80;
const READ_MS = 720;

export function yahtzySettled() {
  return gate;
}

export function bindYahtzy(next) {
  api = next;
  const table = document.querySelector("#card-table");
  table?.addEventListener("click", (event) => {
    if (!api || api.getState().game_type !== "yahtzy") return;
    const button = event.target instanceof Element ? event.target.closest("[data-yahtzy]") : null;
    if (!(button instanceof HTMLButtonElement) || button.disabled) return;
    const kind = button.dataset.yahtzy;
    if (kind === "hold") toggleHold(button);
    else if (kind === "roll") sendRoll();
    else if (kind === "pick" && button.dataset.box) choose(button.dataset.box);
    else if (kind === "commit" && picked) send(["score", picked]);
  });
}

export function paintYahtzy(state) {
  const box = document.querySelector("#card-table");
  if (!box || !api) return;
  if (state.id !== gameId) {
    gameId = state.id || "";
    ready = false;
    shownPly = 0;
    shownFaces = null;
    reelPly = 0;
    holds.clear();
    picked = "";
  }
  const picture = state.yahtzy || {};
  box.classList.remove("oval", "felt", "is-domino", "is-nardy");
  box.classList.add("is-yahtzy");
  const stage = stageOf(box, state);
  const felt = feltOf(stage);
  if (!ready) {
    ready = true;
    shownPly = lastPly(state);
    shownFaces = (picture.dice || []).length === 5 ? picture.dice.map(Number) : null;
    if (!offer(picture, picked)) picked = bestOffer(picture);
    paintHead(felt, state, picture);
    paintDice(felt, shownFaces, false);
    armDice(felt, state, picture, shownFaces);
    paintRoll(felt, state, picture, false);
    paintSheet(stage, state, picture);
    return;
  }
  const rolls = unseenRolls(state);
  if (rolls.length && rolls.at(-1).ply !== reelPly) {
    const held = pendingHeld;
    pendingHeld = null;
    reelPly = rolls.at(-1).ply;
    holds.clear();
    picked = "";
    beginReel(felt, stage, state, picture, rolls, held);
    return;
  }
  if (reelPly && lastPly(state) < reelPly) return;
  if (!offer(picture, picked)) picked = bestOffer(picture);
  paintHead(felt, state, picture);
  const faces = (picture.dice || []).length === 5 ? picture.dice.map(Number) : null;
  if (!felt.querySelector(".yahtzy-dice.is-spinning")) {
    paintDice(felt, faces, false);
    armDice(felt, state, picture, faces);
    shownFaces = faces;
  }
  paintRoll(felt, state, picture, Boolean(felt.querySelector(".yahtzy-dice.is-spinning")));
  paintSheet(stage, state, picture);
  shownPly = lastPly(state);
}

function stageOf(box, state) {
  let stage = box.querySelector(":scope > .yahtzy-stage");
  if (!stage || stage.dataset.game !== String(state.id || "")) {
    stage = document.createElement("div");
    stage.className = "yahtzy-stage";
    stage.dataset.game = String(state.id || "");
    box.replaceChildren(stage);
  }
  return stage;
}

function beginReel(felt, stage, state, picture, rolls, held) {
  let resolve;
  const pending = new Promise((done) => { resolve = done; });
  gate = pending;
  playRolls(felt, stage, state, picture, rolls, held).finally(resolve);
}

async function playRolls(felt, stage, state, picture, rolls, held) {
  const token = reelPly;
  reeling = true;
  let prior = shownFaces;
  try {
    for (let index = 0; index < rolls.length; index += 1) {
      const roll = rolls[index];
      if (reelPly !== token) return;
      paintHead(felt, state, picture, roll);
      paintRoll(felt, state, picture, true);
      const kept = index === 0 && held ? held : heldFromMotion(picture, roll.faces, index === rolls.length - 1);
      await spinTo(felt, roll.faces, prior, kept);
      if (reelPly !== token) return;
      prior = roll.faces;
      shownFaces = roll.faces;
      shownPly = roll.ply;
      await wait(READ_MS);
    }
    if (reelPly !== token) return;
    const finalFaces = (picture.dice || []).length === 5 ? picture.dice.map(Number) : null;
    if (!finalFaces && shownFaces) await releaseDice(felt);
    reeling = false;
    if (!offer(picture, picked)) picked = bestOffer(picture);
    paintHead(felt, state, picture);
    paintDice(felt, finalFaces, false);
    armDice(felt, state, picture, finalFaces);
    paintRoll(felt, state, picture, false);
    paintSheet(stage, state, picture);
    shownFaces = finalFaces;
    shownPly = lastPly(state);
  } finally {
    reeling = false;
    if (reelPly === token) reelPly = 0;
  }
}

function feltOf(stage) {
  let tray = stage.querySelector(":scope > .yahtzy-tray");
  if (!tray) {
    tray = document.createElement("div");
    tray.className = "yahtzy-tray";
    const felt = document.createElement("div");
    felt.className = "yahtzy-felt";
    tray.append(felt);
    stage.prepend(tray);
  }
  return tray.querySelector(".yahtzy-felt");
}

function paintHead(felt, state, picture, roll) {
  let head = felt.querySelector(".yahtzy-head");
  if (!head) {
    head = document.createElement("div");
    head.className = "yahtzy-head";
    felt.prepend(head);
  }
  head.replaceChildren();
  const title = document.createElement("p");
  title.className = "yahtzy-title";
  title.textContent = roll ? rollHeadline(state, roll) : headline(state, picture);
  const meta = document.createElement("p");
  meta.className = "yahtzy-meta";
  meta.textContent = roll ? `Бросок ${throwNumber(state, roll.ply)} из 3` : metaLine(picture);
  head.append(title, meta);
}

function paintDice(felt, faces, spinning) {
  const previous = felt.querySelector(".yahtzy-dice");
  if (!faces || faces.length !== 5) {
    previous?.remove();
    return null;
  }
  let row = previous;
  if (!row || row.children.length !== 5 || !row.querySelector("canvas")) {
    row = document.createElement("div");
    row.className = "yahtzy-dice";
    for (let index = 0; index < 5; index += 1) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "yahtzy-die";
      button.dataset.yahtzy = "hold";
      button.dataset.index = String(index);
      button.style.setProperty("--i", String(index));
      const canvas = document.createElement("canvas");
      canvas.width = 256;
      canvas.height = 256;
      canvas.className = "yahtzy-die-canvas";
      button.append(canvas);
      row.append(button);
    }
    if (previous) previous.replaceWith(row);
    else felt.querySelector(".yahtzy-head")?.after(row);
  }
  row.classList.toggle("is-spinning", spinning);
  const images = cubeTextures();
  const pending = images.some((image) => !image.complete);
  [...row.children].forEach((button, index) => {
    const canvas = button.querySelector("canvas");
    if (canvas && !spinning) drawFace(canvas, faces[index]);
    if (!spinning) markHold(button, holds.has(index), faces[index], false);
  });
  if (pending) {
    Promise.all(images.map((image) => image.decode().catch(() => {}))).then(() => {
      if (!row.isConnected || row.classList.contains("is-spinning")) return;
      [...row.children].forEach((button, index) => {
        const canvas = button.querySelector("canvas");
        if (canvas) drawFace(canvas, faces[index]);
      });
    });
  }
  return row;
}

function paintRoll(felt, state, picture, tumbling) {
  let actions = felt.querySelector(".yahtzy-actions");
  if (!actions) {
    actions = document.createElement("div");
    actions.className = "yahtzy-actions";
    felt.append(actions);
  }
  const dice = felt.querySelector(".yahtzy-dice");
  if (dice) dice.after(actions);
  actions.replaceChildren();
  if (reeling) return;
  const yours = Boolean(state.your_turn) && state.status === "active" && !api.getBusy();
  const faces = picture.dice || [];
  if (!yours || Number(picture.rolls_left) <= 0) return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "yahtzy-roll";
  button.dataset.yahtzy = "roll";
  button.disabled = tumbling;
  button.append(diceIcon(), document.createTextNode(rollLabel(faces.length === 5)));
  actions.append(button);
}

function paintSheet(stage, state, picture) {
  let sheet = stage.querySelector(":scope > .yahtzy-sheet");
  if (!sheet) {
    sheet = document.createElement("div");
    sheet.className = "yahtzy-sheet";
    stage.append(sheet);
  }
  const columns = picture.columns || [];
  const offers = new Map((picture.offers || []).map((item) => [item.category, Number(item.points)]));
  const actor = String(picture.actor || "");
  const yours = Boolean(state.your_turn) && state.status === "active" && !api.getBusy();
  const head = document.createElement("div");
  head.className = "yahtzy-sheet-head";
  const title = document.createElement("h2");
  title.textContent = "Лист счёта";
  head.append(title);
  const chosen = offer(picture, picked);
  if (yours && chosen) {
    const commit = document.createElement("button");
    commit.type = "button";
    commit.className = "yahtzy-commit";
    commit.dataset.yahtzy = "commit";
    commit.append(checkIcon(), document.createTextNode(`Записать ${pointsPhrase(chosen.points)}`));
    head.append(commit);
  }
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const titleRow = document.createElement("tr");
  const corner = document.createElement("th");
  corner.textContent = "Комбинация";
  titleRow.append(corner);
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.className = "is-player";
    cell.append(playerCard(state, column));
    titleRow.append(cell);
  }
  thead.append(titleRow);
  table.append(thead);
  const body = document.createElement("tbody");
  body.append(sectionRow(columns.length, "Верх"));
  for (const [key, face, label] of UPPER) body.append(scoreRow(columns, key, faceLabel(face, label), offers, actor, yours));
  body.append(valueRow(columns, "Сумма", (column) => (filledUpper(column) ? column.upper : null)));
  body.append(valueRow(columns, "Бонус 35 при сумме от 63", (column) => column.bonus));
  body.append(valueRow(columns, "Итого верх", (column) => (filledUpper(column) || column.bonus != null ? column.upper_total : null), "is-sum"));
  body.append(sectionRow(columns.length, "Низ"));
  for (const [key, label] of LOWER) body.append(scoreRow(columns, key, textLabel(label), offers, actor, yours));
  body.append(valueRow(columns, "Бонус Яцзы 100", (column) => (column.yahtzy_bonus ? column.yahtzy_bonus : null)));
  body.append(valueRow(columns, "Итого низ", (column) => (filledLower(column) || column.yahtzy_bonus ? column.lower_total : null), "is-sum"));
  body.append(valueRow(columns, "Всего", (column) => column.grand, "is-grand"));
  table.append(body);
  sheet.replaceChildren(head, table);
}

function sectionRow(width, label) {
  const row = document.createElement("tr");
  row.className = "is-section";
  const cell = document.createElement("th");
  cell.colSpan = width + 1;
  cell.textContent = label;
  row.append(cell);
  return row;
}

function scoreRow(columns, key, label, offers, actor, yours) {
  const row = document.createElement("tr");
  const name = document.createElement("th");
  name.append(label);
  row.append(name);
  for (const column of columns) {
    const cell = document.createElement("td");
    const written = Object.prototype.hasOwnProperty.call(column.scores || {}, key);
    if (written) {
      cell.textContent = String(column.scores[key]);
    } else if (yours && column.key === actor && offers.has(key)) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "yahtzy-cell";
      button.dataset.yahtzy = "pick";
      button.dataset.box = key;
      const selected = key === picked;
      if (selected) {
        cell.classList.add("is-pick");
        button.textContent = String(offers.get(key));
      }
      button.setAttribute("aria-pressed", selected ? "true" : "false");
      button.setAttribute("aria-label", `Выбрать «${boxName(key)}», ${pointsPhrase(offers.get(key))}`);
      cell.append(button);
    }
    row.append(cell);
  }
  return row;
}

function valueRow(columns, label, read, className) {
  const row = document.createElement("tr");
  if (className) row.className = className;
  const name = document.createElement("th");
  name.textContent = label;
  row.append(name);
  for (const column of columns) {
    const cell = document.createElement("td");
    const value = read(column);
    cell.textContent = value == null ? "" : String(value);
    row.append(cell);
  }
  return row;
}

function faceLabel(face, title) {
  const wrap = document.createElement("span");
  wrap.className = "yahtzy-face";
  const image = document.createElement("img");
  image.src = dieSrc(face);
  image.alt = "";
  const text = document.createElement("span");
  text.textContent = title;
  wrap.append(image, text);
  return wrap;
}

function textLabel(title) {
  const text = document.createElement("span");
  text.textContent = title;
  return text;
}

function filledUpper(column) {
  return UPPER.some(([key]) => Object.prototype.hasOwnProperty.call(column.scores || {}, key));
}

function filledLower(column) {
  return LOWER.some(([key]) => Object.prototype.hasOwnProperty.call(column.scores || {}, key));
}

function boxName(key) {
  return {
    ones: "Единицы",
    twos: "Двойки",
    threes: "Тройки",
    fours: "Четвёрки",
    fives: "Пятёрки",
    sixes: "Шестёрки",
    three: "Три одинаковых",
    four: "Четыре одинаковых",
    house: "Фул-хаус",
    small: "Малый стрит",
    large: "Большой стрит",
    yahtzy: "Яцзы",
    chance: "Шанс",
  }[key] || key;
}

function playerCard(state, column) {
  const seat = (state.seats || []).find((item) => item.key === column.key) || {
    key: column.key,
    name: seatName(state, column.key),
  };
  const card = document.createElement("div");
  card.className = "yahtzy-player";
  if (seat.you) card.classList.add("is-you");
  if (seat.turn && state.status === "active") card.classList.add("is-turn");
  const cpu = Boolean(seat.cpu || seat.kind === "computer");
  const face = api.plateFace(seat, cpu);
  const copy = document.createElement("span");
  copy.className = "yahtzy-player-copy";
  const title = document.createElement("span");
  title.className = "yahtzy-player-name";
  api.fillPersonName(title, seat);
  const note = document.createElement("span");
  note.className = "yahtzy-player-note";
  const bits = [];
  if (seat.turn && state.status === "active") bits.push("ходит");
  bits.push(String(column.grand ?? 0));
  note.textContent = bits.join(" · ");
  copy.append(title, note);
  card.append(face, copy);
  return card;
}

function seatName(state, key) {
  const found = (state.seats || []).find((item) => item.key === key);
  if (found?.name) return found.name;
  if (key === "white") return "Белые";
  if (key === "black") return "Чёрные";
  const number = Number(String(key).slice(1));
  return Number.isInteger(number) ? `Игрок ${number + 1}` : key;
}

function headline(state, picture) {
  if (picture.phase === "done" || state.status === "finished") return "Партия окончена";
  if (picture.phase === "waiting" || state.status === "waiting") return "Ждём игроков";
  if (state.your_turn) return "Ваш ход";
  const name = seatName(state, picture.actor);
  return name ? `Ход — ${name}` : "Ход соперника";
}

function metaLine(picture) {
  if (picture.phase !== "play") return "";
  const actor = (picture.columns || []).find((item) => item.key === picture.actor);
  const filled = actor ? Object.keys(actor.scores || {}).length : 0;
  const round = Math.min(13, filled + 1);
  const thrown = Math.min(3, Math.max(1, 3 - Number(picture.rolls_left || 0)));
  return `Раунд ${round} из 13 · Бросок ${thrown} из 3`;
}

function offer(picture, category) {
  return (picture.offers || []).find((item) => item.category === category) || null;
}

function bestOffer(picture) {
  const offers = picture.offers || [];
  if (!offers.length) return "";
  return [...offers].sort((left, right) => Number(right.points) - Number(left.points))[0].category;
}

function rollLabel(reroll) {
  if (!reroll) return "Бросить кости";
  const loose = 5 - holds.size;
  if (!loose) return "Оставить кости";
  return `Перебросить ${loose} ${bonesWord(loose)}`;
}

function bonesWord(count) {
  const tail = count % 100;
  const last = tail % 10;
  if (tail > 10 && tail < 20) return "костей";
  if (last === 1) return "кость";
  if (last >= 2 && last <= 4) return "кости";
  return "костей";
}

function pointsPhrase(count) {
  const value = Number(count) || 0;
  const tail = Math.abs(value) % 100;
  const last = tail % 10;
  let word = "очков";
  if (!(tail > 10 && tail < 20)) {
    if (last === 1) word = "очко";
    else if (last >= 2 && last <= 4) word = "очка";
  }
  return `${value} ${word}`;
}

function canHold(state, picture) {
  return Boolean(state.your_turn)
    && state.status === "active"
    && !api.getBusy()
    && (picture.dice || []).length === 5
    && Number(picture.rolls_left) > 0;
}

function toggleHold(button) {
  const index = Number(button.dataset.index);
  if (holds.has(index)) holds.delete(index);
  else holds.add(index);
  paintYahtzy(api.getState());
}

function choose(category) {
  picked = category;
  paintYahtzy(api.getState());
}

function sendRoll() {
  const picture = api.getState().yahtzy || {};
  const kept = (picture.dice || []).length === 5 ? [...holds].sort((left, right) => left - right) : [];
  pendingHeld = new Set(kept);
  send(["roll", ...kept.map(String)]);
}

function send(path) {
  if (!api || api.getBusy()) return;
  api.setBusy(true);
  api.post(`/api/v1/games/${api.getState().id}/moves`, {
    version: api.getState().version,
    path,
  }).then(async (data) => {
    await api.apply(data.state);
  }).catch(async (error) => {
    pendingHeld = null;
    api.say(error.message);
    await api.refresh();
  }).finally(() => {
    api.setBusy(false);
    paintYahtzy(api.getState());
    api.onSettled();
  });
}

function armDice(felt, state, picture, faces) {
  const row = felt.querySelector(".yahtzy-dice");
  if (!row || !faces) return;
  const playable = canHold(state, picture);
  [...row.children].forEach((button, index) => {
    if (!(button instanceof HTMLButtonElement)) return;
    button.classList.remove("is-tumbling");
    markHold(button, holds.has(index), faces[index], playable);
  });
}

function heldFromMotion(picture, faces, last) {
  if (!last) return null;
  const motion = picture?.motion;
  if (!motion || motion.kind !== "dice" || !Array.isArray(motion.kept) || !Array.isArray(motion.dice)) return null;
  if (motion.dice.length !== faces.length || motion.dice.some((face, index) => Number(face) !== faces[index])) return null;
  return new Set(motion.kept.map(Number));
}

async function spinTo(felt, faces, prior, held) {
  const row = paintDice(felt, faces, true);
  if (!row) return;
  await Promise.all(cubeTextures().map((image) => image.decode().catch(() => {})));
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const jobs = [];
  [...row.children].forEach((button, index) => {
    if (!(button instanceof HTMLButtonElement)) return;
    const still = held ? held.has(index) : Array.isArray(prior) && prior[index] === faces[index];
    const canvas = button.querySelector("canvas");
    button.classList.toggle("is-tumbling", !still && !reduce);
    button.disabled = true;
    button.querySelector(".yahtzy-lock")?.remove();
    if (!canvas) return;
    if (still || reduce) drawFace(canvas, faces[index]);
    else jobs.push(spinCanvas(canvas, prior?.[index] || faces[index], faces[index], index));
  });
  await Promise.all(jobs);
  [...row.children].forEach((button, index) => {
    button.classList.remove("is-tumbling");
    const canvas = button.querySelector("canvas");
    if (canvas) drawFace(canvas, faces[index]);
  });
  row.classList.remove("is-spinning");
}

async function releaseDice(felt) {
  const row = felt.querySelector(".yahtzy-dice");
  if (!row) return;
  row.classList.add("is-leaving");
  await wait(280);
  if (row.isConnected) row.remove();
}

function markHold(button, held, face, playable) {
  button.classList.toggle("is-held", held);
  button.disabled = !playable;
  button.setAttribute("aria-pressed", held ? "true" : "false");
  button.setAttribute("aria-label", held ? `Кость ${face}, бросить снова` : `Кость ${face}, оставить`);
  const lock = button.querySelector(".yahtzy-lock");
  if (held && !lock) button.append(lockBadge());
  if (!held && lock) lock.remove();
}

function lockBadge() {
  const badge = document.createElement("span");
  badge.className = "yahtzy-lock";
  badge.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="11" width="12" height="9" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8.5 11V8.2a3.5 3.5 0 0 1 7 0V11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  return badge;
}

function diceIcon() {
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  icon.innerHTML = '<rect x="4" y="4" width="16" height="16" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="8.5" cy="8.5" r="1.2" fill="currentColor"/><circle cx="15.5" cy="15.5" r="1.2" fill="currentColor"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/>';
  return icon;
}

function checkIcon() {
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  icon.innerHTML = '<path d="M5 12.5 9.2 17 19 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>';
  return icon;
}

const RAD = Math.PI / 180;
const CUBE_SIDES = [
  { value: 1, normal: [0, 0, 1], right: [1, 0, 0], down: [0, 1, 0] },
  { value: 6, normal: [0, 0, -1], right: [-1, 0, 0], down: [0, 1, 0] },
  { value: 2, normal: [1, 0, 0], right: [0, 0, -1], down: [0, 1, 0] },
  { value: 5, normal: [-1, 0, 0], right: [0, 0, 1], down: [0, 1, 0] },
  { value: 3, normal: [0, -1, 0], right: [1, 0, 0], down: [0, 0, 1] },
  { value: 4, normal: [0, 1, 0], right: [1, 0, 0], down: [0, 0, -1] },
];
const CUBE_POSES = [null, [0, 0], [0, -90], [-90, 0], [90, 0], [0, 90], [0, 180]];
let cubeImages = null;

function cubeTextures() {
  if (!cubeImages) {
    cubeImages = [1, 2, 3, 4, 5, 6].map((face) => {
      const image = new Image();
      image.src = dieSrc(face);
      return image;
    });
  }
  return cubeImages;
}

function pose(value) {
  const [pitch, yaw] = CUBE_POSES[value] || [0, 0];
  return [pitch * RAD, yaw * RAD];
}

function drawFace(canvas, face) {
  canvas.dataset.face = String(face);
  drawCube(canvas, ...pose(face));
}

function drawCube(canvas, pitch, yaw) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const images = cubeTextures();
  const sx = Math.sin(pitch);
  const cx = Math.cos(pitch);
  const sy = Math.sin(yaw);
  const cy = Math.cos(yaw);
  const rotate = ([x, y, z]) => {
    const horizontal = x * cy + z * sy;
    const depth = z * cy - x * sy;
    return [horizontal, y * cx - depth * sx, y * sx + depth * cx];
  };
  const size = canvas.width;
  const scale = size * 0.29;
  ctx.resetTransform();
  ctx.clearRect(0, 0, size, size);
  const outline = [];
  for (const x of [-0.89, 0.89]) {
    for (const y of [-0.89, 0.89]) {
      for (const z of [-0.89, 0.89]) outline.push(rotate([x, y, z]).slice(0, 2));
    }
  }
  outline.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const hullHalf = (points) => {
    const hull = [];
    for (const point of points) {
      while (hull.length >= 2) {
        const a = hull.at(-2);
        const b = hull.at(-1);
        if ((b[0] - a[0]) * (point[1] - a[1]) > (b[1] - a[1]) * (point[0] - a[0])) break;
        hull.pop();
      }
      hull.push(point);
    }
    hull.pop();
    return hull;
  };
  const hull = hullHalf(outline).concat(hullHalf([...outline].reverse()));
  ctx.setTransform(scale, 0, 0, scale, size / 2, size / 2);
  ctx.beginPath();
  hull.forEach(([x, y], index) => (index ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.closePath();
  ctx.fillStyle = "#ddbf8d";
  ctx.strokeStyle = "#ddbf8d";
  ctx.lineJoin = "round";
  ctx.lineWidth = 0.22;
  ctx.fill();
  ctx.stroke();
  for (const side of CUBE_SIDES) {
    const n = rotate(side.normal);
    if (n[2] < 0.00001) continue;
    const right = rotate(side.right);
    const down = rotate(side.down);
    const image = images[side.value - 1];
    ctx.setTransform(
      2 * scale * right[0],
      2 * scale * right[1],
      2 * scale * down[0],
      2 * scale * down[1],
      size / 2 + scale * (n[0] - right[0] - down[0]),
      size / 2 + scale * (n[1] - right[1] - down[1]),
    );
    ctx.beginPath();
    ctx.roundRect(0, 0, 1, 1, 0.09);
    ctx.fillStyle = "#dfc595";
    ctx.fill();
    if (!image?.complete || !image.naturalWidth) continue;
    ctx.save();
    ctx.clip();
    ctx.drawImage(image, 14, 14, 355, 359, 0, 0, 1, 1);
    const shade = Math.min(0.42, Math.max(0, 0.3 * (1 - n[2]) + 0.1 * n[1] - 0.05 * n[0]));
    ctx.fillStyle = `rgba(50, 29, 10, ${shade})`;
    ctx.fillRect(0, 0, 1, 1);
    ctx.restore();
  }
}

function spinCanvas(canvas, fromFace, toFace, index) {
  const [fromX, fromY] = pose(fromFace);
  const [toX, toY] = pose(toFace);
  const start = performance.now() + index * STAGGER_MS;
  const turn = Math.PI * 2;
  const dx = -turn - ((fromX - toX + turn) % turn);
  const dy = Math.atan2(Math.sin(toY - fromY), Math.cos(toY - fromY));
  return new Promise((resolve) => {
    const frame = (now) => {
      const t = Math.max(0, Math.min(1, (now - start) / SPIN_MS));
      if (t === 1) {
        drawFace(canvas, toFace);
        resolve();
        return;
      }
      const p = t * t * t * (10 + t * (-15 + 6 * t));
      drawCube(canvas, fromX + dx * p, fromY + dy * p + 0.3 * Math.sin(Math.PI * p));
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  });
}

function unseenRolls(state) {
  return (state.moves || []).flatMap((move) => {
    if (!move || move.ply <= shownPly || move.path?.[0] !== "dice" || move.path.length < 6) return [];
    const faces = move.path.slice(1, 6).map(Number);
    if (faces.some((face) => !Number.isInteger(face) || face < 1 || face > 6)) return [];
    return [{ ply: move.ply, faces }];
  });
}

function lastPly(state) {
  return (state.moves || []).reduce((max, move) => Math.max(max, Number(move?.ply) || 0), 0);
}

function throwNumber(state, ply) {
  let count = 0;
  for (const move of state.moves || []) {
    if (move.ply > ply) break;
    if (move.path?.[0] === "score") count = 0;
    else if (move.path?.[0] === "dice") count += 1;
  }
  return Math.min(3, Math.max(1, count));
}

function rollHeadline(state, roll) {
  const move = (state.moves || []).find((item) => item.ply === roll.ply);
  const seat = String(move?.seat || "");
  if (seat && seat !== state.your_side) return `Ход — ${seatName(state, seat)}`;
  return "Ваш ход";
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function dieSrc(face) {
  return api.asset(`/static/images/yahtzy/die-${face}.webp`);
}
