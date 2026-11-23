const tabs = [...document.querySelectorAll("#player-settings .settings-tab")];
const tabNames = tabs.map((tab) => tab.id);
const savedTab = sessionStorage.getItem("pn-settings-tab");
const openPassword = new URLSearchParams(location.search).get("password") === "changed"
  || Boolean(document.querySelector("#password-panel .banner[role='alert']:not([hidden])"));

function showSettingsTab(id) {
  const chosen = tabNames.includes(id) ? id : "tab-personal";
  for (const tab of tabs) {
    const on = tab.id === chosen;
    tab.setAttribute("aria-selected", on ? "true" : "false");
    tab.tabIndex = on ? 0 : -1;
    const panel = document.getElementById(tab.getAttribute("aria-controls") || "");
    if (panel) panel.hidden = !on;
  }
  sessionStorage.setItem("pn-settings-tab", chosen);
}

if (tabs.length) {
  showSettingsTab(openPassword ? "tab-password" : savedTab || "tab-personal");
  for (const tab of tabs) {
    tab.addEventListener("click", () => showSettingsTab(tab.id));
    tab.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
      event.preventDefault();
      const index = tabs.indexOf(tab);
      const next = event.key === "ArrowRight"
        ? tabs[(index + 1) % tabs.length]
        : tabs[(index - 1 + tabs.length) % tabs.length];
      next.focus();
      showSettingsTab(next.id);
    });
  }
}

const form = document.querySelector("#settings");
if (form) {
  const months = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
  ];

  function checked(name) {
    return form.querySelector(`input[name="${name}"]:checked`);
  }

  function yearsWord(years) {
    const tail = years % 10;
    const hundred = years % 100;
    if (tail === 1 && hundred !== 11) return "год";
    if (tail >= 2 && tail <= 4 && (hundred < 12 || hundred > 14)) return "года";
    return "лет";
  }

  function paintRange(input) {
    const readout = document.getElementById(input.dataset.readout || "");
    if (!readout) return;
    const value = Number(input.value);
    readout.textContent = input.dataset.scale === "seconds"
      ? `${(value / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} с`
      : String(value);
  }

  function paintAge() {
    const status = document.querySelector("#age-status");
    const dayField = document.querySelector("#born-day");
    if (!(dayField instanceof HTMLSelectElement)) return "";
    const day = Number(dayField.value);
    const month = Number(document.querySelector("#born-month")?.value);
    const year = Number(document.querySelector("#born-year")?.value);
    if (!status) return "";
    if (!day || !month || !year) {
      status.classList.remove("adult");
      status.textContent = "Укажите день, месяц и год.";
      return "";
    }
    const born = new Date(year, month - 1, day);
    if (born.getFullYear() !== year || born.getMonth() !== month - 1 || born.getDate() !== day) {
      status.classList.add("adult");
      status.textContent = "Такой даты не бывает.";
      return "";
    }
    const today = new Date();
    let years = today.getFullYear() - year;
    const before = today.getMonth() + 1 < month || (today.getMonth() + 1 === month && today.getDate() < day);
    if (before) years -= 1;
    const label = `${day} ${months[month - 1]} ${year} · ${years} ${yearsWord(years)}`;
    const open = years >= 18;
    status.classList.toggle("adult", !open);
    status.textContent = open
      ? `${label} · взрослые игры открыты`
      : `${label} · взрослые игры откроются с 18 лет`;
    return open ? "взрослые игры открыты" : "взрослые игры закрыты";
  }

  function paintLevel() {
    const level = Number(checked("checkers_level")?.value || 3);
    for (const input of form.querySelectorAll('input[name="checkers_level"]')) {
      const step = input.closest("label");
      const n = Number(input.value);
      step.classList.toggle("is-hot", n <= level);
      step.classList.toggle("is-on", n === level);
    }
    const fill = document.querySelector("#meter-fill");
    if (fill) fill.dataset.level = String(level);
  }

  function paintSummary() {
    const summary = document.querySelector("#setup-summary");
    if (!summary) return;
    const parts = ["theme", "board_style", "default_game", "default_side"]
      .map((name) => checked(name)?.dataset.title)
      .filter(Boolean);
    const age = paintAge();
    if (age) parts.push(age);
    summary.textContent = parts.join(" · ");
  }

  function paint() {
    for (const input of form.querySelectorAll('input[type="range"]')) paintRange(input);
    paintLevel();
    paintSummary();
  }

  form.addEventListener("input", (event) => {
    if (event.target?.type === "range") paintRange(event.target);
    paintSummary();
  });
  form.addEventListener("change", () => {
    paintLevel();
    paintSummary();
  });
  form.addEventListener("invalid", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const panel = target.closest("[role='tabpanel']");
    if (!(panel instanceof HTMLElement) || !panel.hidden) return;
    const tab = document.querySelector(`[aria-controls="${panel.id}"]`);
    if (tab instanceof HTMLButtonElement) showSettingsTab(tab.id);
  }, true);
  paint();
}

const passwordForm = document.querySelector("#password-form");
const passwordPanel = document.querySelector("#password-panel");
const passwordNote = document.querySelector("#password-note");

function passwordProblem(value) {
  const minimum = Number(passwordPanel?.dataset.min || 10);
  if (value.length < minimum) return `Пароль должен содержать не меньше ${minimum} символов.`;
  if (value.length > 128) return "Пароль слишком длинный.";
  const chars = [...value];
  if (passwordPanel?.dataset.letter === "1" && !chars.some((char) => /\p{L}/u.test(char))) {
    return "В пароле нужна хотя бы одна буква.";
  }
  if (passwordPanel?.dataset.digit === "1" && !chars.some((char) => /\p{Nd}/u.test(char))) {
    return "В пароле нужна хотя бы одна цифра.";
  }
  return "";
}

if (passwordForm && passwordPanel && passwordNote) {
  passwordForm.addEventListener("submit", (event) => {
    const next = passwordForm.elements.namedItem("new_password");
    const again = passwordForm.elements.namedItem("repeat_password");
    const nextValue = next && "value" in next ? next.value : "";
    const againValue = again && "value" in again ? again.value : "";
    const problem = nextValue !== againValue ? "Новые пароли не совпадают." : passwordProblem(nextValue);
    if (!problem) {
      passwordNote.hidden = true;
      return;
    }
    event.preventDefault();
    passwordNote.hidden = false;
    passwordNote.textContent = problem;
    const field = nextValue !== againValue ? again : next;
    if (field && "focus" in field) field.focus();
  });
}

for (const peek of document.querySelectorAll("[data-peek]")) {
  peek.addEventListener("click", () => {
    const input = peek.parentElement?.querySelector("input");
    if (!input) return;
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    peek.setAttribute("aria-pressed", show ? "true" : "false");
    const label = show ? "Скрыть пароль" : "Показать пароль";
    peek.setAttribute("aria-label", label);
    peek.dataset.tip = label;
  });
}
