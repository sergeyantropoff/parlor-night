let api = null;
let picked = "";
let gameId = "";
let seenVersion = -1;
const spots = new Map();
const placed = { white: [], black: [] };
const XS = [131, 194, 257, 320, 384, 447, 575, 639, 703, 767, 831, 894].map((value) => value / 1024);
const TOP = [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23];
const BOTTOM = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0];

export function bindNardy(next) {
  api = next;
  const root = document.querySelector(".play-nardy") || document.querySelector("#card-table");
  root?.addEventListener("click", (event) => {
    if (!api || api.getState().game_type !== "nardy") return;
    const button = event.target instanceof Element ? event.target.closest("[data-nardy]") : null;
    if (!(button instanceof HTMLElement) || button.disabled) return;
    const kind = button.dataset.nardy;
    if (kind === "roll" || kind === "double" || kind === "take" || kind === "drop") {
      send(["dice", kind]);
      return;
    }
    if (kind === "pip") land(button.dataset.from || "", button.dataset.to || "");
  });
  const table = document.querySelector("#card-table");
  table?.addEventListener("pointerdown", (event) => {
    const checker = event.target instanceof Element ? event.target.closest(".nardy-checker.is-playable") : null;
    if (!(checker instanceof HTMLElement) || !api || event.button !== 0) return;
    drag(checker, event);
  });
}

export function paintNardy(state) {
  const box = document.querySelector("#card-table");
  if (!box || !api) return;
  const picture = state.nardy || {};
  if (state.id !== gameId) {
    gameId = state.id || "";
    picked = "";
    spots.clear();
    placed.white = [];
    placed.black = [];
    seenVersion = -1;
  }
  const fresh = state.version !== seenVersion;
  seenVersion = state.version;
  if (picked && !(picture.targets || []).some((item) => item.from === picked)) picked = "";
  box.classList.remove("oval");
  box.classList.add("is-nardy");
  const stage = document.createElement("div");
  stage.className = "nardy-stage";
  const far = seatNode(state, picture, true);
  const board = document.createElement("div");
  board.className = "nardy-board";
  const cloth = document.createElement("img");
  cloth.className = "nardy-cloth";
  cloth.alt = "";
  cloth.draggable = false;
  cloth.src = api.asset("/static/images/nardy/board.webp");
  const layer = document.createElement("div");
  layer.className = `nardy-layer${state.black_at_bottom ? " is-flipped" : ""}`;
  const slots = assign(picture);
  for (const slot of slots) layer.append(checkerNode(slot, picture, fresh));
  for (const target of targets(picture)) layer.append(pipNode(target, picture));
  const hud = document.createElement("div");
  hud.className = "nardy-hud";
  const offer = rollButton(state);
  if (offer) hud.append(offer);
  else hud.append(diceNode(picture, fresh, state.version));
  hud.append(cubeNode(state, picture));
  board.append(cloth, layer, hud);
  const near = seatNode(state, picture, false);
  const actions = actionRow(state);
  stage.append(far, board);
  if (actions) stage.append(actions);
  stage.append(near);
  box.replaceChildren(stage);
  paintBadge(state, picture);
}

function seatNode(state, picture, far) {
  const side = far ? (state.black_at_bottom ? "white" : "black") : (state.black_at_bottom ? "black" : "white");
  const seat = (state.seats || []).find((item) => item.key === side);
  const wrap = document.createElement("div");
  wrap.className = `nardy-seat${far ? " is-far" : " is-near"}`;
  if (!seat) return wrap;
  const won = state.result === `${seat.key}_win`;
  const node = document.createElement("div");
  node.className = "plate";
  if (seat.turn && state.status === "active") node.classList.add("is-active");
  if (won) node.classList.add("is-win");
  const cpu = Boolean(seat.cpu || seat.kind === "computer");
  const copy = document.createElement("span");
  copy.className = "plate-copy";
  const title = document.createElement("span");
  title.className = "plate-name";
  const name = seat.you ? `${seat.name} · вы` : cpu && state.engine_title ? `${seat.name} · ${state.engine_title}` : seat.name;
  api.fillPersonName(title, { name, login: seat.login });
  const left = document.createElement("span");
  left.className = "plate-stack";
  const bar = Number(picture.bar?.[seat.key] || 0);
  const bits = [`${Number(seat.count || 0)} на доске`];
  if (bar) bits.push(`${bar} на баре`);
  if (seat.mark) bits.push(seat.mark);
  left.textContent = bits.join(" · ");
  copy.append(title, left);
  node.append(api.plateFace(seat, cpu), copy);
  wrap.append(node);
  return wrap;
}

function checkerNode(slot, picture, fresh) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `nardy-checker is-${slot.seat}`;
  button.dataset.nardy = "checker";
  button.dataset.id = `${slot.seat[0]}${slot.id}`;
  button.dataset.from = slot.where === "point" ? String(slot.point) : "bar";
  const playable = (picture.targets || []).some((item) => item.from === button.dataset.from);
  button.classList.toggle("is-playable", playable);
  button.classList.toggle("is-picked", picked === button.dataset.from && slot.depth === slot.count - 1);
  button.disabled = !playable || api.getBusy();
  button.setAttribute("aria-label", labelOf(slot));
  const image = document.createElement("img");
  image.alt = "";
  image.draggable = false;
  image.src = api.asset(`/static/images/nardy/checker-${slot.seat === "white" ? "light" : "dark"}.webp`);
  button.append(image);
  moveNode(button, position(slot, picture.variant), fresh);
  return button;
}

function pipNode(target, picture) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "nardy-pip is-on";
  button.dataset.nardy = "pip";
  button.dataset.from = target.from;
  button.dataset.to = target.to;
  const at = target.to === "off" ? offPoint(target.seat, 0, 1, picture.variant) : pointAt(Number(target.to), 0, 1);
  button.style.left = at.x;
  button.style.top = at.y;
  button.setAttribute("aria-label", target.to === "off" ? "Снять шашку" : `Поле ${Number(target.to) + 1}`);
  return button;
}

function dieSrc(face) {
  return api.asset(`/static/images/nardy/die-${face}.webp`);
}

function rollMove(state) {
  return (state.legal_moves || []).find((move) => move.path?.[0] === "dice" && move.path?.[1] === "roll") || null;
}

function rollButton(state) {
  if (!rollMove(state)) return null;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "nardy-roll";
  button.dataset.nardy = "roll";
  button.disabled = api.getBusy();
  button.setAttribute("aria-label", "Бросить кости");
  const pair = document.createElement("span");
  pair.className = "nardy-roll-pair";
  for (const face of [5, 3]) {
    const image = document.createElement("img");
    image.className = "nardy-die";
    image.alt = "";
    image.draggable = false;
    image.src = dieSrc(face);
    pair.append(image);
  }
  const label = document.createElement("span");
  label.textContent = "Бросить";
  button.append(pair, label);
  return button;
}

function diceNode(picture, fresh, version) {
  const live = document.querySelector("#card-table .nardy-dice.is-rolling");
  if (live && live.dataset.version === String(version)) return live;
  const row = document.createElement("div");
  row.className = "nardy-dice";
  const dice = picture.dice || [];
  if (!dice.length) {
    row.hidden = true;
    return row;
  }
  const tumbling = fresh && picture.motion?.kind === "dice" && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const shown = Number(dice[0]) === Number(dice[1]) ? [dice[0], dice[0], dice[0], dice[0]] : dice;
  if (tumbling) {
    row.classList.add("is-rolling");
    row.dataset.version = String(version);
  }
  shown.forEach((value, index) => {
    const image = document.createElement("img");
    image.className = tumbling ? "nardy-die is-roll" : "nardy-die";
    image.alt = `Кость ${value}`;
    image.draggable = false;
    image.style.animationDelay = `${index * 90}ms`;
    image.src = dieSrc(tumbling ? 1 + Math.floor(Math.random() * 6) : value);
    if (tumbling) spinFace(image, value, index);
    row.append(image);
  });
  if (tumbling) {
    const last = row.querySelector(".nardy-die:last-child");
    const stop = () => row.classList.remove("is-rolling");
    last?.addEventListener("animationend", stop, { once: true });
    window.setTimeout(stop, 1600);
  }
  if (picture.motion?.pass) {
    const note = document.createElement("span");
    note.className = "nardy-pass";
    note.textContent = "Хода нет";
    row.append(note);
  }
  return row;
}

function spinFace(image, finalFace, index) {
  const steps = 10;
  let step = 0;
  const timer = window.setInterval(() => {
    step += 1;
    if (!image.isConnected || step >= steps) {
      window.clearInterval(timer);
      image.src = dieSrc(finalFace);
      return;
    }
    let face = 1 + Math.floor(Math.random() * 6);
    if (String(face) === image.dataset.face) face = (face % 6) + 1;
    image.dataset.face = String(face);
    image.src = dieSrc(face);
  }, 78 + index * 12);
}

function paintBadge(state, picture) {
  const head = document.querySelector(".stage-head");
  if (!head) return;
  let badge = document.querySelector("#nardy-badge");
  if (!badge) {
    badge = document.createElement("div");
    badge.id = "nardy-badge";
    badge.className = "deal-badge throw-badge nardy-badge";
    head.append(badge);
  }
  badge.replaceChildren();
  const dice = picture.dice || [];
  const kicker = document.createElement("span");
  kicker.textContent = "Бросок";
  badge.append(kicker);
  if (dice.length) {
    const text = document.createElement("strong");
    text.textContent = Number(dice[0]) === Number(dice[1]) ? `Дубль ${dice[0]}` : `${dice[0]} и ${dice[1]}`;
    badge.append(text);
  } else if (picture.phase === "roll") {
    badge.append(document.createTextNode("Кости ещё не брошены"));
  }
  if (picture.motion?.pass) {
    const note = document.createElement("em");
    note.textContent = "Хода нет";
    badge.append(note);
  }
  const roll = rollMove(state);
  if (roll) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.nardy = "roll";
    button.textContent = "Бросить";
    button.disabled = api.getBusy();
    badge.append(button);
  }
  badge.hidden = picture.phase === "waiting" || (picture.phase === "done" && !dice.length);
}

function cubeNode(state, picture) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "nardy-cube";
  const value = Number(picture.cube || 1);
  const face = value <= 1 ? 64 : value;
  const image = document.createElement("img");
  image.alt = value <= 1 ? "Куб удвоения" : `Куб ${value}`;
  image.draggable = false;
  image.src = api.asset(`/static/images/nardy/cube-${face}.webp`);
  button.append(image);
  const short = picture.variant === "short" && state.status !== "finished";
  button.hidden = picture.variant !== "short";
  button.classList.toggle("is-idle", value <= 1);
  const offered = (state.legal_moves || []).some((move) => move.path?.[0] === "dice" && move.path?.[1] === "double");
  button.dataset.nardy = offered ? "double" : "";
  button.disabled = !offered;
  if (short && picture.cube_owner) button.title = picture.cube_owner === "white" ? "Куб у белых" : "Куб у чёрных";
  return button;
}

function actionRow(state) {
  const moves = (state.legal_moves || []).filter((move) => move.path?.[0] === "dice" && move.path?.[1] !== "roll");
  if (!moves.length) return null;
  const row = document.createElement("div");
  row.className = "nardy-actions";
  for (const move of moves) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = move.path[1] === "drop" ? "secondary" : "";
    button.dataset.nardy = move.path[1];
    button.textContent = move.notation;
    row.append(button);
  }
  return row;
}

function targets(picture) {
  if (!picked) return [];
  const found = [];
  const seen = new Set();
  for (const item of picture.targets || []) {
    if (item.from !== picked || seen.has(item.to)) continue;
    seen.add(item.to);
    found.push({ ...item, seat: item.from === "bar" ? ownerOf(picture, "bar") : signOf(picture, Number(item.from)) });
  }
  return found;
}

function choose(from) {
  const state = api.getState();
  const picture = state.nardy || {};
  const options = (picture.targets || []).filter((item) => item.from === from);
  if (!options.length || api.getBusy()) return;
  if (options.length === 1) {
    send(["move", from, String(options[0].die)]);
    return;
  }
  picked = picked === from ? "" : from;
  paintNardy(state);
}

function land(from, to) {
  const picture = api.getState().nardy || {};
  const options = (picture.targets || []).filter((item) => item.from === from && item.to === to);
  if (!options.length) return;
  const die = options.slice().sort((left, right) => right.die - left.die)[0].die;
  picked = "";
  send(["move", from, String(die)]);
}

function drag(checker, event) {
  const from = checker.dataset.from || "";
  const picture = api.getState().nardy || {};
  const options = (picture.targets || []).filter((item) => item.from === from);
  if (!options.length) return;
  event.preventDefault();
  const shown = options.length > 1 && picked === from;
  if (options.length > 1 && picked !== from) {
    picked = from;
    paintNardy(api.getState());
  }
  const origin = { x: event.clientX, y: event.clientY };
  let moved = false;
  const ghost = checker.querySelector("img")?.cloneNode(true);
  if (!(ghost instanceof HTMLImageElement)) return;
  ghost.className = "nardy-ghost";
  ghost.hidden = true;
  document.body.append(ghost);
  const moveGhost = (point) => {
    if (Math.hypot(point.clientX - origin.x, point.clientY - origin.y) > 5) moved = true;
    ghost.hidden = !moved;
    ghost.style.left = `${point.clientX}px`;
    ghost.style.top = `${point.clientY}px`;
  };
  const finish = (point) => {
    ghost.remove();
    window.removeEventListener("pointermove", moveGhost);
    window.removeEventListener("pointerup", finish);
    if (!moved) {
      if (options.length === 1) send(["move", from, String(options[0].die)]);
      else if (shown) {
        picked = "";
        paintNardy(api.getState());
      }
      return;
    }
    const hit = document.elementFromPoint(point.clientX, point.clientY);
    const pip = hit instanceof Element ? hit.closest(".nardy-pip") : null;
    if (pip instanceof HTMLElement) land(from, pip.dataset.to || "");
  };
  window.addEventListener("pointermove", moveGhost);
  window.addEventListener("pointerup", finish);
}

async function send(path) {
  if (!api || api.getBusy()) return;
  const state = api.getState();
  api.setBusy(true);
  picked = "";
  try {
    const data = await api.post(`/api/v1/games/${state.id}/moves`, { version: state.version, path });
    await api.apply(data.state);
  } catch (error) {
    api.say(error.message || "Ход не прошёл.");
    await api.refresh();
  } finally {
    api.setBusy(false);
    api.onSettled();
  }
}

function assign(picture) {
  const slots = [];
  const points = picture.points || [];
  for (let point = 0; point < 24; point += 1) {
    const value = Number(points[point] || 0);
    const seat = value > 0 ? "white" : value < 0 ? "black" : "";
    const count = Math.abs(value);
    for (let depth = 0; depth < count; depth += 1) slots.push({ seat, where: "point", point, depth, count });
  }
  for (const seat of ["white", "black"]) {
    const bar = Number(picture.bar?.[seat] || 0);
    for (let depth = 0; depth < bar; depth += 1) slots.push({ seat, where: "bar", depth, count: bar });
    const off = Number(picture.off?.[seat] || 0);
    for (let depth = 0; depth < off; depth += 1) slots.push({ seat, where: "off", depth, count: off });
  }
  for (const seat of ["white", "black"]) {
    const mine = slots.filter((slot) => slot.seat === seat);
    const prev = placed[seat];
    const next = Array(15).fill("");
    const used = new Set();
    for (let id = 0; id < prev.length; id += 1) {
      const old = prev[id];
      if (!old) continue;
      const index = mine.findIndex((slot, order) => !used.has(order) && slotKey(slot) === old);
      if (index < 0) continue;
      used.add(index);
      next[id] = slotKey(mine[index]);
      mine[index].id = id;
    }
    let cursor = 0;
    for (let index = 0; index < mine.length; index += 1) {
      if (used.has(index)) continue;
      while (cursor < 15 && next[cursor]) cursor += 1;
      next[cursor] = slotKey(mine[index]);
      mine[index].id = cursor;
      cursor += 1;
    }
    placed[seat] = next;
  }
  return slots.filter((slot) => slot.id !== undefined);
}

function slotKey(slot) {
  return slot.where === "point" ? `p${slot.point}:${slot.depth}` : `${slot.where}:${slot.depth}`;
}

function moveNode(node, at, fresh) {
  const id = node.dataset.id;
  const prev = spots.get(id);
  node.style.left = at.x;
  node.style.top = at.y;
  if (fresh && prev && (prev.x !== at.x || prev.y !== at.y)) {
    node.style.transition = "none";
    node.style.left = prev.x;
    node.style.top = prev.y;
    requestAnimationFrame(() => {
      node.style.transition = "";
      node.style.left = at.x;
      node.style.top = at.y;
    });
  }
  spots.set(id, at);
}

function position(slot, variant) {
  if (slot.where === "bar") return barPoint(slot.seat, slot.depth);
  if (slot.where === "off") return offPoint(slot.seat, slot.depth, slot.count, variant);
  return pointAt(slot.point, slot.depth, slot.count);
}

function pointAt(point, depth, count) {
  const top = point >= 12;
  const column = (top ? TOP : BOTTOM).indexOf(point);
  const base = top ? 26 / 682 : 653 / 682;
  const tip = top ? 278 / 682 : 391 / 682;
  const span = Math.abs(tip - base);
  const step = Math.min(0.024, (span - 0.03) / Math.max(count - 1, 1));
  const y = base + (top ? 1 : -1) * (0.02 + depth * step);
  return { x: `${XS[column] * 100}%`, y: `${y * 100}%` };
}

function barPoint(seat, depth) {
  const y = seat === "white" ? 0.55 + depth * 0.028 : 0.45 - depth * 0.028;
  return { x: "49.9%", y: `${y * 100}%` };
}

function offPoint(seat, depth, count, variant) {
  const left = variant === "long" && seat === "black";
  const fromTop = (variant === "short" && seat === "black") || (variant === "long" && seat === "white");
  const step = Math.min(0.016, 0.22 / Math.max(count, 1));
  const y = fromTop ? 0.12 + depth * step : 0.88 - depth * step;
  return { x: left ? "4.4%" : "95.6%", y: `${y * 100}%` };
}

function labelOf(slot) {
  if (slot.where === "bar") return "Шашка на баре";
  if (slot.where === "off") return "Снятая шашка";
  return `Поле ${slot.point + 1}`;
}

function signOf(picture, point) {
  return Number(picture.points?.[point] || 0) > 0 ? "white" : "black";
}

function ownerOf(picture, where) {
  if (where !== "bar") return "white";
  if (Number(picture.bar?.white || 0) > 0) return "white";
  return "black";
}
