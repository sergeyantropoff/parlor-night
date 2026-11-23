const LIFE = 8000;
const SEEN_KEY = "pn-notice-seen";
const PRIMED_KEY = "pn-notice-primed";
const AVATAR = /^[0-9a-f]{32}\.(jpg|png|webp)$/;

const stack = document.getElementById("toasts");
if (document.documentElement.dataset.signedIn === "1" && stack) {
  const seen = new Set(readSeen());
  let primed = sessionStorage.getItem(PRIMED_KEY) === "1";
  let busy = false;
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function readSeen() {
    try {
      const parsed = JSON.parse(sessionStorage.getItem(SEEN_KEY) || "[]");
      return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
    } catch {
      return [];
    }
  }

  function remember(id) {
    seen.add(id);
    sessionStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-200)));
  }

  function key(item) {
    return `${item.kind}:${item.id}`;
  }

  function safeHref(href) {
    return typeof href === "string" && href.startsWith("/") && !href.startsWith("//") ? href : "/";
  }

  function paintCount(href, count) {
    const link = document.querySelector(`nav.nav a[href="${href}"]`);
    if (!link) return;
    let badge = link.querySelector(".nav-count");
    const value = Number(count) || 0;
    if (value <= 0) {
      badge?.remove();
      return;
    }
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "nav-count";
      link.append(badge);
    }
    badge.textContent = value < 100 ? String(value) : "99+";
  }

  function paintThreads(threads) {
    const list = document.getElementById("inbox-list");
    if (!list) return;
    const counts = new Map();
    if (Array.isArray(threads)) {
      for (const item of threads) {
        if (!item || typeof item.username !== "string") continue;
        counts.set(item.username, Number(item.unread) || 0);
      }
    }
    for (const row of list.querySelectorAll("[data-peer]")) {
      const value = counts.get(row.dataset.peer) || 0;
      row.classList.toggle("is-unread", value > 0);
      let badge = row.querySelector(".inbox-count");
      if (value <= 0) {
        badge?.remove();
        continue;
      }
      const meta = row.querySelector(".inbox-meta");
      if (!meta) continue;
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "inbox-count";
        meta.prepend(badge);
      }
      const label = value < 100 ? String(value) : "99+";
      badge.textContent = label;
      badge.title = `Новых сообщений: ${label}`;
    }
  }

  function chip(name, avatar) {
    const file = String(avatar || "");
    if (AVATAR.test(file)) {
      const img = document.createElement("img");
      img.className = "avatar";
      img.alt = "";
      img.src = `/avatars/${file}`;
      return img;
    }
    const span = document.createElement("span");
    const label = String(name || "?").trim() || "?";
    const tone = [...label].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 6;
    span.className = `avatar tone-${tone}`;
    span.textContent = label.slice(0, 1).toLocaleUpperCase("ru");
    return span;
  }

  function viewing(item) {
    return item.kind === "request" && location.pathname === "/friends" && location.hash === "#requests";
  }

  function dismiss(card) {
    if (!card.isConnected || card.dataset.closing === "1") return;
    card.dataset.closing = "1";
    window.clearTimeout(Number(card.dataset.timer));
    if (motion) {
      card.remove();
      return;
    }
    card.classList.add("is-leaving");
    card.addEventListener("animationend", (event) => {
      if (event.target === card) card.remove();
    });
  }

  function show(item) {
    const id = key(item);
    if (stack.querySelector(`[data-notice="${CSS.escape(id)}"]`)) return;
    while (stack.children.length >= 4) {
      const oldest = [...stack.children].find((node) => !node.matches(":hover") && !node.matches(":focus-within"));
      if (!oldest) break;
      oldest.remove();
    }
    const card = document.createElement("article");
    card.className = "toast";
    card.dataset.notice = id;
    const link = document.createElement("a");
    link.className = "toast-open";
    link.href = safeHref(item.href);
    link.append(chip(item.name, item.avatar));
    const copy = document.createElement("span");
    copy.className = "toast-copy";
    const name = document.createElement("strong");
    name.textContent = item.name || item.username || "";
    const text = document.createElement("span");
    text.className = "toast-text";
    text.textContent = item.text || "";
    const action = document.createElement("span");
    action.className = "toast-go";
    action.textContent = item.action || "Открыть";
    copy.append(name, text, action);
    link.append(copy);
    const close = document.createElement("button");
    close.type = "button";
    close.className = "toast-x";
    close.setAttribute("aria-label", "Закрыть");
    close.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-x"></use></svg>';
    const meter = document.createElement("i");
    meter.className = "toast-meter";
    meter.setAttribute("aria-hidden", "true");
    card.append(link, close, meter);
    close.addEventListener("click", () => dismiss(card));
    let remaining = LIFE;
    let mark = performance.now();
    let timer = 0;
    let held = false;
    const arm = () => {
      window.clearTimeout(timer);
      if (held) return;
      mark = performance.now();
      timer = window.setTimeout(finish, remaining);
      card.dataset.timer = String(timer);
    };
    const finish = () => {
      if (card.matches(":hover") || card.matches(":focus-within")) {
        held = true;
        card.classList.add("is-held");
        return;
      }
      dismiss(card);
    };
    const hold = () => {
      if (held) return;
      held = true;
      remaining = Math.max(0, remaining - (performance.now() - mark));
      window.clearTimeout(timer);
      card.classList.add("is-held");
    };
    const release = () => {
      if (card.matches(":hover") || card.matches(":focus-within")) return;
      held = false;
      card.classList.remove("is-held");
      arm();
    };
    card.addEventListener("pointerenter", hold);
    card.addEventListener("pointerleave", release);
    card.addEventListener("focusin", hold);
    card.addEventListener("focusout", () => window.setTimeout(release, 0));
    arm();
    stack.append(card);
  }

  async function poll() {
    const response = await fetch("/api/v1/notices", { headers: { Accept: "application/json" } });
    if (!response.ok) return;
    const data = await response.json();
    const counts = data.counts || {};
    paintCount("/friends", counts.requests);
    paintCount("/chats", counts.chats);
    paintCount("/live", counts.live);
    paintCount("/lobby", counts.seek);
    paintThreads(data.threads);
    showBroadcast(data.broadcast);
    const items = Array.isArray(data.items) ? data.items : [];
    if (!primed) {
      for (const item of items) {
        if (item && item.kind && item.id) remember(key(item));
      }
      sessionStorage.setItem(PRIMED_KEY, "1");
      primed = true;
      return;
    }
    for (const item of [...items].reverse()) {
      if (!item || (item.kind !== "message" && item.kind !== "request") || item.id == null || item.id === "") continue;
      const id = key(item);
      if (seen.has(id)) continue;
      remember(id);
      if (!viewing(item)) show(item);
    }
  }

  async function tick() {
    if (busy || document.hidden) return;
    busy = true;
    try {
      await poll();
    } catch {
      /* следующий круг повторит запрос */
    } finally {
      busy = false;
    }
  }

  const broadcast = document.getElementById("broadcast");
  const tones = {
    info: "Информация",
    warning: "Внимание",
    ok: "Все хорошо!",
    error: "Критическая ошибка!",
  };
  const titles = {
    info: "Сообщение",
    warning: "Обратите внимание",
    ok: "Хорошая новость",
    error: "Нужно знать",
  };
  const marks = {
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/><path d="M12 11v5M12 8h.01"/></svg>',
    warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 4.5 21 19H3z"/><path d="M12 10v4M12 16.5h.01"/></svg>',
    ok: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/><path d="m8.2 12.2 2.6 2.6 5-5.2"/></svg>',
    error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/><path d="m9 9 6 6M15 9l-6 6"/></svg>',
  };
  let shownRevision = "";
  let dismissing = false;

  function csrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content || "";
  }

  async function dismissBroadcast(revision) {
    if (!revision || dismissing) return;
    dismissing = true;
    try {
      await fetch("/api/v1/broadcast/dismiss", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf(),
        },
        body: JSON.stringify({ revision }),
      });
    } catch {
      dismissing = false;
    }
  }

  function showBroadcast(note) {
    if (!(broadcast instanceof HTMLDialogElement)) return;
    if (!note || typeof note.text !== "string" || !note.text || typeof note.revision !== "string") return;
    if (note.revision === shownRevision || broadcast.open) return;
    if (document.querySelector("dialog[open]")) return;
    const tone = tones[note.tone] ? note.tone : "info";
    broadcast.className = `broadcast-dialog is-${tone}`;
    const mark = broadcast.querySelector(".broadcast-mark");
    if (mark) mark.innerHTML = marks[tone];
    const kicker = document.getElementById("broadcast-kicker");
    const title = document.getElementById("broadcast-title");
    const text = document.getElementById("broadcast-text");
    if (kicker) kicker.textContent = tones[tone];
    if (title) title.textContent = titles[tone];
    if (text) text.textContent = note.text;
    shownRevision = note.revision;
    broadcast.dataset.revision = note.revision;
    dismissing = false;
    broadcast.showModal();
  }

  document.getElementById("broadcast-close")?.addEventListener("click", () => broadcast?.close());
  broadcast?.addEventListener("close", () => {
    dismissBroadcast(broadcast.dataset.revision || "");
  });
  broadcast?.addEventListener("click", (event) => {
    if (event.target === broadcast) broadcast.close();
  });

  tick();
  window.setInterval(tick, 6000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) tick();
  });
}
