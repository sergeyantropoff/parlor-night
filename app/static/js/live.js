import { attachPager } from "./pager.js";

const root = document.querySelector("#live");
if (root) {
  const search = root.querySelector("#table-search");
  const game = root.querySelector("#table-game");
  const link = document.querySelector("#live-link");
  const linkText = document.querySelector("#live-link-text");
  const storageKey = "parlor-live";
  let audience = "all";
  let cards = [];
  let buttons = [];
  let empty = null;
  let paintPage = null;
  let refreshing = false;

  const termOf = () => (search instanceof HTMLInputElement ? search.value : "").trim().toLowerCase();
  const kindOf = () => (game instanceof HTMLSelectElement ? game.value : "all");

  const word = (count) => {
    const tail = count % 10;
    const hundred = count % 100;
    if (tail === 1 && hundred !== 11) return "стол";
    if (tail >= 2 && tail <= 4 && (hundred < 12 || hundred > 14)) return "стола";
    return "столов";
  };

  const remember = () => {
    sessionStorage.setItem(storageKey, JSON.stringify({
      audience,
      term: search instanceof HTMLInputElement ? search.value : "",
      kind: kindOf(),
    }));
  };

  const narrowed = (card) => {
    const term = termOf();
    const kind = kindOf();
    return (kind === "all" || card.dataset.game === kind)
      && (!term || (card.dataset.find || "").includes(term));
  };

  const inAudience = (card) => {
    if (audience === "mine") return card.dataset.mine === "1";
    return audience === "all" || card.dataset.audience === audience;
  };

  const bind = () => {
    const grid = root.querySelector("#floor-grid");
    root.querySelector(".pager")?.remove();
    cards = grid ? [...grid.querySelectorAll("[data-audience]")] : [];
    buttons = [...root.querySelectorAll("[data-filter]")];
    empty = root.querySelector("#live-none");
    paintPage = grid
      ? attachPager(grid, {
        size: 6,
        label: "Страницы столов",
        match: (card) => narrowed(card) && inAudience(card),
      })
      : null;
  };

  const apply = ({ reset = false } = {}) => {
    const matched = cards.filter(narrowed);
    const counts = { all: matched.length, mine: 0, open: 0, closed: 0 };
    for (const card of matched) {
      counts[card.dataset.audience === "closed" ? "closed" : "open"] += 1;
      if (card.dataset.mine === "1") counts.mine += 1;
    }
    const shown = paintPage ? paintPage({ reset }) : null;
    const visible = shown
      ? shown.count
      : matched.filter(inAudience).length;
    for (const button of buttons) {
      button.setAttribute("aria-pressed", button.dataset.filter === audience ? "true" : "false");
      const slot = button.querySelector("[data-count]");
      if (slot) slot.textContent = String(counts[button.dataset.filter] || 0);
    }
    const total = root.querySelector("#live-total");
    const totalWord = root.querySelector("#live-total-word");
    if (total) total.textContent = String(visible);
    if (totalWord) totalWord.textContent = word(visible);
    if (empty) empty.hidden = visible > 0 || cards.length === 0;
    remember();
  };

  const setLink = (state, text) => {
    if (!(link instanceof HTMLElement) || !linkText) return;
    link.dataset.state = state;
    linkText.textContent = text;
  };

  const syncNav = (doc) => {
    const currentLink = document.querySelector('.nav a[href="/live"]');
    const freshLink = doc.querySelector('.nav a[href="/live"]');
    if (!currentLink || !freshLink) return;
    const current = currentLink.querySelector(".nav-count");
    const fresh = freshLink.querySelector(".nav-count");
    if (fresh && current) current.textContent = fresh.textContent;
    else if (fresh) currentLink.append(fresh.cloneNode(true));
    else current?.remove();
  };

  const takeBoard = (doc) => {
    const next = doc.querySelector("#live-board");
    const board = root.querySelector("#live-board");
    if (!next || !board) return false;
    const nextGrid = next.querySelector("#floor-grid");
    const grid = board.querySelector("#floor-grid");
    if (nextGrid && grid) {
      const focused = document.activeElement;
      if (focused instanceof HTMLElement && grid.contains(focused)) return true;
      grid.replaceChildren(...nextGrid.children);
      cards = [...grid.querySelectorAll("[data-audience]")];
      apply();
      return true;
    }
    const focused = document.activeElement;
    board.replaceWith(next);
    bind();
    apply({ reset: true });
    if (focused instanceof HTMLElement && focused.id) document.getElementById(focused.id)?.focus();
    return true;
  };

  const refresh = async () => {
    if (refreshing || document.visibilityState !== "visible" || !navigator.onLine) return;
    refreshing = true;
    try {
      const response = await fetch("/live", { headers: { Accept: "text/html" }, cache: "no-store" });
      if (response.redirected && new URL(response.url, window.location.origin).pathname.startsWith("/login")) {
        window.location.assign(response.url);
        return;
      }
      if (!response.ok) throw new Error("status");
      const doc = new DOMParser().parseFromString(await response.text(), "text/html");
      if (!takeBoard(doc)) throw new Error("board");
      syncNav(doc);
      setLink("live", "Обновляется автоматически");
    } catch {
      setLink(navigator.onLine ? "retry" : "down", navigator.onLine ? "Переподключение" : "Связь потеряна");
    } finally {
      refreshing = false;
    }
  };

  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || "");
    if (saved && typeof saved === "object") {
      if (search instanceof HTMLInputElement && typeof saved.term === "string") search.value = saved.term;
      if (game instanceof HTMLSelectElement && typeof saved.kind === "string" && [...game.options].some((option) => option.value === saved.kind)) {
        game.value = saved.kind;
      }
      if (saved.audience === "open" || saved.audience === "closed" || saved.audience === "mine" || saved.audience === "all") audience = saved.audience;
    }
  } catch {
    /* сохранённый фильтр необязателен */
  }

  bind();
  root.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target?.closest("[data-filter]");
    if (button instanceof HTMLButtonElement) {
      audience = button.dataset.filter || "all";
      apply({ reset: true });
      return;
    }
    if (target?.closest("#live-reset")) {
      if (search instanceof HTMLInputElement) search.value = "";
      if (game instanceof HTMLSelectElement) game.value = "all";
      audience = "all";
      apply({ reset: true });
      search?.focus();
    }
  });
  search?.addEventListener("input", () => apply({ reset: true }));
  game?.addEventListener("change", () => apply({ reset: true }));
  apply();

  window.addEventListener("offline", () => setLink("down", "Связь потеряна"));
  window.addEventListener("online", () => {
    setLink("live", "Обновляется автоматически");
    void refresh();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") void refresh();
  });
  if (!navigator.onLine) setLink("down", "Связь потеряна");
  window.setInterval(() => { void refresh(); }, 20000);
}
