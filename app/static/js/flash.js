const LIFE = 5000;
const LINES = {
  settings: "Настройки сохранены.",
  password: "Пароль изменён.",
  avatar: "Портрет сохранён.",
  "avatar-off": "Портрет убран.",
  site: "Настройки сохранены.",
  terms: "Условия игр сохранены.",
  sessions: "Все сессии, кроме вашей, завершены.",
  lockouts: "Блокировки входа сняты.",
  "wiped-messages": "Все сообщения удалены.",
  "wiped-games": "Партии очищены. Гости и фишки не изменены.",
  "wiped-stats": "Статистика игр очищена.",
  keys: "Все ключи очищены. Войдите снова.",
  "news-created": "Новость опубликована.",
  "news-saved": "Новость сохранена.",
  "news-removed": "Новость убрана.",
  game: "Партия создана.",
  chips: "Фишки начислены.",
  contact: "Письмо отправлено.",
  broadcast: "Сообщение показано всем.",
  "broadcast-off": "Сообщение убрано.",
};

const stack = document.getElementById("toasts");
const motion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function showToast(text) {
  if (!stack || typeof text !== "string" || !text) return;
  const card = document.createElement("article");
  card.className = "toast toast-flash";
  card.setAttribute("role", "status");
  const mark = document.createElement("span");
  mark.className = "toast-mark";
  mark.setAttribute("aria-hidden", "true");
  mark.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m5 12 4.2 4.2L19 7.5"/></svg>';
  const line = document.createElement("p");
  line.className = "toast-line";
  line.textContent = text;
  const close = document.createElement("button");
  close.type = "button";
  close.className = "toast-x";
  close.setAttribute("aria-label", "Закрыть");
  close.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-x"/></svg>';
  const meter = document.createElement("i");
  meter.className = "toast-meter";
  meter.setAttribute("aria-hidden", "true");
  card.append(mark, line, close, meter);
  const dismiss = () => {
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
  };
  close.addEventListener("click", dismiss);
  let remaining = LIFE;
  let markAt = performance.now();
  let timer = 0;
  let held = false;
  const arm = () => {
    window.clearTimeout(timer);
    if (held) return;
    markAt = performance.now();
    timer = window.setTimeout(finish, remaining);
    card.dataset.timer = String(timer);
  };
  const finish = () => {
    if (card.matches(":hover") || card.matches(":focus-within")) {
      held = true;
      card.classList.add("is-held");
      return;
    }
    dismiss();
  };
  const hold = () => {
    if (held) return;
    held = true;
    remaining = Math.max(0, remaining - (performance.now() - markAt));
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

window.pnToast = showToast;

function readFlash() {
  const part = document.cookie.split("; ").find((item) => item.startsWith("pn_flash="));
  if (!part) return "";
  document.cookie = "pn_flash=; Max-Age=0; Path=/; SameSite=Lax";
  return decodeURIComponent(part.slice("pn_flash=".length));
}

const flashed = LINES[readFlash()];
if (flashed) showToast(flashed);
