const root = document.querySelector("#site-settings");
const tabs = [...document.querySelectorAll("#site-settings .settings-tab")];

function showSiteTab(id) {
  const chosen = tabs.some((tab) => tab.id === id) ? id : "tab-access";
  for (const tab of tabs) {
    const on = tab.id === chosen;
    tab.setAttribute("aria-selected", on ? "true" : "false");
    tab.tabIndex = on ? 0 : -1;
    const panel = document.getElementById(tab.getAttribute("aria-controls") || "");
    if (panel) panel.hidden = !on;
  }
  const field = document.querySelector("#site-return-tab");
  if (field instanceof HTMLInputElement) field.value = chosen.slice(4);
  sessionStorage.setItem("pn-site-tab", chosen);
}

if (tabs.length) {
  const requested = root instanceof HTMLElement ? root.dataset.tab : "";
  const stored = sessionStorage.getItem("pn-site-tab");
  showSiteTab(requested ? `tab-${requested}` : stored || "tab-access");
  for (const tab of tabs) {
    tab.addEventListener("click", () => showSiteTab(tab.id));
    tab.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
      event.preventDefault();
      const index = tabs.indexOf(tab);
      const next = event.key === "ArrowRight"
        ? tabs[(index + 1) % tabs.length]
        : tabs[(index - 1 + tabs.length) % tabs.length];
      next.focus();
      showSiteTab(next.id);
    });
  }
}

const form = document.querySelector("#site-form");
if (form instanceof HTMLFormElement) {
  const summary = document.querySelector("#setup-summary");
  const registration = {
    open: "Регистрация открыта",
    referral: "Только по ссылкам",
    closed: "Регистрация закрыта",
  };

  function plural(count, one, few, many) {
    const mod10 = count % 10;
    const mod100 = count % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
    return many;
  }

  function field(name) {
    const element = form.elements.namedItem(name);
    return element && "value" in element ? String(element.value) : "";
  }

  function checked(name) {
    const element = form.elements.namedItem(name);
    return element instanceof HTMLInputElement && element.checked;
  }

  function sessionPart() {
    const hours = Number(field("session_hours"));
    if (!hours) return "";
    if (hours % 24 === 0) {
      const days = hours / 24;
      return `${days} ${plural(days, "сутки", "суток", "суток")}`;
    }
    return `${hours} ${plural(hours, "час", "часа", "часов")}`;
  }

  function passwordPart() {
    const parts = [`пароль от ${field("password_min")}`];
    const letter = checked("password_needs_letter");
    const digit = checked("password_needs_digit");
    if (letter && digit) parts.push("буква и цифра");
    else if (letter) parts.push("нужна буква");
    else if (digit) parts.push("нужна цифра");
    return parts.join(", ");
  }

  function gamesPart() {
    const closed = [...form.querySelectorAll('input[name="game"]')]
      .filter((box) => box instanceof HTMLInputElement && !box.checked)
      .map((box) => box.dataset.title)
      .filter(Boolean);
    if (!closed.length) return "все игры";
    if (closed.length === 1) return `закрыта ${closed[0]}`;
    if (closed.length <= 3) return `закрыты ${closed.join(", ")}`;
    return `закрыто ${closed.length} ${plural(closed.length, "игра", "игры", "игр")}`;
  }

  function paintSummary() {
    if (!summary) return;
    const mode = form.querySelector('input[name="registration_mode"]:checked');
    const parts = [mode instanceof HTMLInputElement ? registration[mode.value] : ""];
    if (checked("maintenance")) parts.push("на обслуживании");
    parts.push(passwordPart(), sessionPart(), gamesPart());
    summary.textContent = parts.filter(Boolean).join(" · ");
  }

  form.addEventListener("input", paintSummary);
  form.addEventListener("change", paintSummary);
  form.addEventListener("invalid", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const panel = target.closest("[role='tabpanel']");
    if (!(panel instanceof HTMLElement) || !panel.hidden) return;
    const tab = document.querySelector(`[aria-controls="${panel.id}"]`);
    if (tab instanceof HTMLButtonElement) showSiteTab(tab.id);
  }, true);
  paintSummary();
}

for (const button of document.querySelectorAll("[data-dialog]")) {
  const dialog = document.getElementById(button.dataset.dialog || "");
  if (!(dialog instanceof HTMLDialogElement)) continue;
  button.addEventListener("click", () => {
    dialog.showModal();
    dialog.querySelector("input[type='password']")?.focus();
  });
  dialog.querySelector("[data-close]")?.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  if (dialog.dataset.open === "1") dialog.querySelector("input[type='password']")?.focus();
}
