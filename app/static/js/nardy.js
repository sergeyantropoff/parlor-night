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
  let stage = box.querySelector(":scope > .nardy-stage");
  if (!stage || stage.dataset.game !== String(state.id || "")) {
    stage = document.createElement("div");
    stage.className = "nardy-stage";
    stage.dataset.game = String(state.id || "");
    box.replaceChildren(stage);
  }
  const board = ensureBoard(stage);
  const layer = board.querySelector(".nardy-layer");
  layer.className = `nardy-layer${state.black_at_bottom ? " is-flipped" : ""}`;
  const far = seatNode(state, picture, true);
  const near = seatNode(state, picture, false);
  const actions = actionRow(state);
  layoutStage(stage, far, board, actions, near);
  syncCheckers(layer, assign(picture), picture, fresh);
  syncPips(layer, picture);
  syncHud(board.querySelector(".nardy-hud"), state, picture, fresh);
  paintHint(picture);
  paintBadge(state, picture);
}

function layoutStage(stage, far, board, actions, near) {
  const farNow = stage.querySelector(":scope > .nardy-seat.is-far");
  if (farNow) farNow.replaceWith(far);
  else stage.prepend(far);
  if (board.parentElement !== stage) far.after(board);
  const actionsNow = stage.querySelector(":scope > .nardy-actions");
  if (actions) {
    if (actionsNow) actionsNow.replaceWith(actions);
    else board.after(actions);
  } else if (actionsNow) actionsNow.remove();
  const nearNow = stage.querySelector(":scope > .nardy-seat.is-near");
  if (nearNow) nearNow.replaceWith(near);
  else stage.append(near);
}
function ensureBoard(stage) {
  const found = stage.querySelector(".nardy-board");
  if (found) return found;
  const board = document.createElement("div");
  board.className = "nardy-board";
  const cloth = document.createElement("img");
  cloth.className = "nardy-cloth";
  cloth.alt = "";
  cloth.draggable = false;
  cloth.src = api.asset("/static/images/nardy/board.webp");
  const layer = document.createElement("div");
  layer.className = "nardy-layer";
  const hud = document.createElement("div");
  hud.className = "nardy-hud";
  board.append(cloth, layer, hud);
  return board;
}

function syncCheckers(layer, slots, picture, fresh) {
  const live = new Map([...layer.querySelectorAll(".nardy-checker")].map((node) => [node.dataset.id, node]));
  const keep = new Set();
  for (const slot of slots) {
    const id = `${slot.seat[0]}${slot.id}`;
    keep.add(id);
    const at = position(slot, picture.variant, picture);
    let node = live.get(id);
    if (!node) {
      node = checkerNode(slot, picture);
      node.style.left = at.x;
      node.style.top = at.y;
      layer.append(node);
      spots.set(id, at);
      continue;
    }
    dressChecker(node, slot, picture);
    const prev = spots.get(id);
    const shifted = Boolean(fresh && prev && (prev.x !== at.x || prev.y !== at.y));
    node.style.left = at.x;
    node.style.top = at.y;
    if (shifted) glideChecker(node, prev, at);
    spots.set(id, at);
  }
  for (const [id, node] of live) if (!keep.has(id)) node.remove();
}

function glideChecker(node, from, to) {
  const board = node.closest(".nardy-board");
  const width = board instanceof HTMLElement ? board.clientWidth : 0;
  const height = board instanceof HTMLElement ? board.clientHeight : 0;
  if (!width || !height) return;
  const dx = ((parseFloat(from.x) - parseFloat(to.x)) / 100) * width;
  const dy = ((parseFloat(from.y) - parseFloat(to.y)) / 100) * height;
  if (Math.hypot(dx, dy) < 1) return;
  node.getAnimations().forEach((item) => item.cancel());
  node.classList.add("is-gliding");
  const animation = node.animate(
    [
      { transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))` },
      { transform: "translate(-50%, -50%)" },
    ],
    { duration: 1200, easing: "cubic-bezier(.33, .05, .18, 1)", fill: "none" },
  );
  const done = () => node.classList.remove("is-gliding");
  animation.onfinish = done;
  animation.oncancel = done;
}

function paintHint(picture) {
  const hint = api.getHint?.();
  const path = hint?.path || [];
  if (!path.length) return;
  if (path[0] === "dice") {
    document.querySelector(`#card-table [data-nardy="${path[1]}"]`)?.classList.add("is-hint");
    return;
  }
  if (path[0] !== "move") return;
  const from = String(path[1]);
  const matches = [...document.querySelectorAll("#card-table .nardy-checker")].filter((node) => {
    const slot = node.dataset.slot || "";
    return from === "bar" ? slot.startsWith("bar:") : slot.startsWith(`p${from}:`);
  });
  const top = matches.sort((left, right) => Number(right.style.getPropertyValue("--stack")) - Number(left.style.getPropertyValue("--stack")))[0];
  top?.classList.add("is-hint");
  const layer = document.querySelector("#card-table .nardy-layer");
  if (!layer || !hint.to) return;
  const marker = document.createElement("span");
  marker.className = "nardy-hint";
  const at = hint.to === "off"
    ? offPoint(hint.seat, Number(picture.off?.[hint.seat] || 0), picture.variant, picture, Number(picture.off?.[hint.seat] || 0) + 1)
    : hintLanding(hint, picture);
  marker.style.left = at.x;
  marker.style.top = at.y;
  layer.append(marker);
}

function hintLanding(hint, picture) {
  const point = Number(hint.to);
  const count = Math.abs(Number(picture.points?.[point] || 0));
  const depth = hint.hit || count === 0 ? 0 : count;
  return pointAt(point, depth, hint.hit ? 1 : Math.max(count + 1, 1));
}

function syncPips(layer, picture) {
  layer.querySelectorAll(".nardy-pip").forEach((node) => node.remove());
  for (const target of targets(picture)) layer.append(pipNode(target, picture));
}

function syncHud(hud, state, picture, fresh) {
  const offer = rollButton(state);
  const dice = offer ? null : diceNode(picture, fresh, state.version);
  hud.replaceChildren(...[offer, dice, cubeNode(state, picture)].filter(Boolean));
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
  const name = !seat.you && cpu && state.engine_title ? `${seat.name} · ${state.engine_title}` : seat.name;
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

function checkerNode(slot, picture) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `nardy-checker is-${slot.seat}`;
  button.dataset.nardy = "checker";
  button.dataset.id = `${slot.seat[0]}${slot.id}`;
  const image = document.createElement("img");
  image.alt = "";
  image.draggable = false;
  image.src = api.asset(`/static/images/nardy/checker-${slot.seat === "white" ? "light" : "dark"}.webp`);
  button.append(image);
  dressChecker(button, slot, picture);
  return button;
}

function dressChecker(node, slot, picture) {
  const from = slot.where === "point" ? String(slot.point) : "bar";
  node.dataset.from = from;
  node.dataset.slot = slotKey(slot);
  node.style.setProperty("--stack", String(slot.depth));
  const playable = (picture.targets || []).some((item) => item.from === from);
  node.classList.toggle("is-playable", playable);
  node.classList.toggle("is-picked", picked === from && slot.depth === slot.count - 1);
  node.disabled = !playable || api.getBusy();
  node.setAttribute("aria-label", labelOf(slot));
}

function pipNode(target, picture) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "nardy-pip is-on";
  button.dataset.nardy = "pip";
  button.dataset.from = target.from;
  button.dataset.to = target.to;
  const at = target.to === "off"
    ? offPoint(target.seat, Number(picture.off?.[target.seat] || 0), picture.variant, picture, Number(picture.off?.[target.seat] || 0) + 1)
    : landingAt(target, picture);
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
  const label = document.createElement("span");
  label.textContent = "Бросить";
  button.append(label);
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
  const span = tumbling ? boardSpan() : 0;
  if (tumbling) {
    row.classList.add("is-rolling");
    row.dataset.version = String(version);
  }
  shown.forEach((value, index) => {
    const image = document.createElement("img");
    image.className = "nardy-die";
    image.alt = `Кость ${value}`;
    image.draggable = false;
    image.src = dieSrc(tumbling ? ((Number(value) % 6) + 1) : value);
    if (tumbling) armThrow(image, value, index, span);
    row.append(image);
  });
  if (tumbling) {
    const last = row.querySelector(".nardy-die:last-child");
    const stop = () => row.classList.remove("is-rolling");
    last?.addEventListener("animationend", stop, { once: true });
    window.setTimeout(stop, 3400);
  }
  if (picture.motion?.pass) {
    const note = document.createElement("span");
    note.className = "nardy-pass";
    note.textContent = "Хода нет";
    row.append(note);
  }
  return row;
}

function boardSpan() {
  const board = document.querySelector(".nardy-board");
  return board instanceof HTMLElement ? board.clientWidth : 760;
}

function armThrow(image, finalFace, index, span) {
  const track = [
    { x: 0.36, y: -0.01, spin: 420 },
    { x: 0.42, y: 0.012, spin: 320 },
    { x: 0.32, y: -0.014, spin: 480 },
    { x: 0.46, y: 0.016, spin: 280 },
  ][index] || { x: 0.38, y: 0, spin: 360 };
  image.style.animationDelay = `${index * 150}ms`;
  image.style.setProperty("--from-x", `${Math.round(span * track.x)}px`);
  image.style.setProperty("--from-y", `${Math.round(span * track.y)}px`);
  image.style.setProperty("--spin", `${track.spin}deg`);
  image.classList.add("is-roll");
  const order = [1, 3, 5, 2, 4, 6].filter((face) => face !== Number(finalFace));
  let step = 0;
  const timer = window.setInterval(() => {
    if (!image.isConnected || step >= order.length) {
      window.clearInterval(timer);
      image.src = dieSrc(finalFace);
      return;
    }
    image.src = dieSrc(order[step]);
    step += 1;
  }, 200);
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
  badge.hidden = !dice.length && !picture.motion?.pass;
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

function playFrom(from) {
  const picture = api.getState().nardy || {};
  const options = (picture.targets || []).filter((item) => item.from === from);
  if (!options.length || api.getBusy()) return;
  const places = [...new Set(options.map((item) => item.to))];
  if (places.length === 1) {
    const die = options.slice().sort((left, right) => right.die - left.die)[0].die;
    picked = "";
    send(["move", from, String(die)]);
    return;
  }
  picked = picked === from ? "" : from;
  paintNardy(api.getState());
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
  const places = [...new Set(options.map((item) => item.to))];
  const justPicked = places.length > 1 && picked !== from;
  if (justPicked) {
    picked = from;
    paintNardy(api.getState());
  }
  const origin = { x: event.clientX, y: event.clientY };
  let moved = false;
  const ghost = checker.querySelector("img")?.cloneNode(true);
  if (!(ghost instanceof HTMLImageElement)) {
    if (places.length === 1) playFrom(from);
    else if (!justPicked && places.length > 1) {
      picked = "";
      paintNardy(api.getState());
    }
    return;
  }
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
      if (places.length === 1) playFrom(from);
      else if (!justPicked) {
        picked = "";
        paintNardy(api.getState());
      }
      return;
    }
    const hit = document.elementFromPoint(point.clientX, point.clientY);
    const pip = hit instanceof Element ? hit.closest(".nardy-pip") : null;
    if (pip instanceof HTMLElement) land(from, pip.dataset.to || "");
    else if (places.length === 1) playFrom(from);
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
    const state = api.getState();
    if (state?.game_type === "nardy") paintNardy(state);
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
    const orphans = [];
    for (let id = 0; id < prev.length; id += 1) if (prev[id] && !next[id]) orphans.push(id);
    const open = [];
    for (let index = 0; index < mine.length; index += 1) if (!used.has(index)) open.push(index);
    const variant = picture.variant;
    while (orphans.length && open.length) {
      let bestId = orphans[0];
      let bestAt = 0;
      let bestDist = Infinity;
      for (const id of orphans) {
        const from = spots.get(`${seat[0]}${id}`);
        for (let cursor = 0; cursor < open.length; cursor += 1) {
          const dist = from ? pointDistance(from, position(mine[open[cursor]], variant, picture)) : 0;
          if (dist < bestDist) {
            bestDist = dist;
            bestId = id;
            bestAt = cursor;
          }
        }
      }
      const index = open.splice(bestAt, 1)[0];
      orphans.splice(orphans.indexOf(bestId), 1);
      next[bestId] = slotKey(mine[index]);
      mine[index].id = bestId;
    }
    let cursor = 0;
    for (const index of open) {
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

function pointDistance(from, to) {
  const dx = (parseFloat(from.x) - parseFloat(to.x)) * (1024 / 682);
  const dy = parseFloat(from.y) - parseFloat(to.y);
  return dx * dx + dy * dy;
}

function position(slot, variant, picture) {
  if (slot.where === "bar") return barPoint(slot.seat, slot.depth);
  if (slot.where === "off") return offPoint(slot.seat, slot.depth, variant, picture, slot.count);
  return pointAt(slot.point, slot.depth, slot.count);
}

const CHECKER_H = 0.054 * (1024 / 682);

function pointAt(point, depth, count) {
  const top = point >= 12;
  const column = (top ? TOP : BOTTOM).indexOf(point);
  const base = top ? 32 / 682 : 650 / 682;
  const tip = top ? 274 / 682 : 408 / 682;
  const dir = top ? 1 : -1;
  const radius = CHECKER_H / 2;
  const start = base + dir * radius;
  const end = tip - dir * radius;
  const room = Math.abs(end - start);
  const touch = CHECKER_H * 1.04;
  const step = count <= 1 ? 0 : Math.min(touch, room / (count - 1));
  const y = start + dir * depth * step;
  return { x: `${XS[column] * 100}%`, y: `${y * 100}%` };
}

function landingAt(target, picture) {
  const point = Number(target.to);
  const count = Math.abs(Number(picture.points?.[point] || 0));
  const depth = target.hit || count === 0 ? 0 : count;
  return pointAt(point, depth, target.hit ? 1 : count + 1);
}

function barPoint(seat, depth) {
  const y = seat === "white" ? 0.55 + depth * 0.028 : 0.45 - depth * 0.028;
  return { x: "49.9%", y: `${y * 100}%` };
}

function offPoint(seat, depth, variant, picture, total) {
  const left = variant === "long" && seat === "black";
  const fromTop = (variant === "short" && seat === "black") || (variant === "long" && seat === "white");
  const mine = Math.max(1, Number(total || picture?.off?.[seat] || 1));
  const other = variant === "short" ? Number(picture?.off?.[seat === "white" ? "black" : "white"] || 0) : 0;
  const radius = CHECKER_H / 2;
  const touch = CHECKER_H * 1.06;
  const gap = CHECKER_H * 0.4;
  const inner = (650 - 30) / 682 - CHECKER_H;
  const natural = (count) => (count <= 0 ? 0 : count === 1 ? CHECKER_H : CHECKER_H + (count - 1) * touch);
  const need = natural(mine) + natural(other) + (other ? gap : 0);
  const share = other <= 0 ? Math.min(inner, natural(mine)) : need <= inner ? natural(mine) : (inner - gap) * (mine / (mine + other));
  const step = mine <= 1 ? 0 : Math.max(0, (share - CHECKER_H) / (mine - 1));
  const dir = fromTop ? 1 : -1;
  const start = (fromTop ? 30 : 650) / 682 + dir * radius;
  return { x: left ? "5.4%" : "94.7%", y: `${(start + dir * depth * step) * 100}%` };
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
