function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function paintTheme() {
  const theme = currentTheme();
  document.querySelectorAll("[data-theme-value]").forEach((button) => {
    button.setAttribute("aria-pressed", button.dataset.themeValue === theme ? "true" : "false");
  });
  const label = theme === "dark" ? "Тёмная тема" : "Светлая тема";
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
  });
}

async function setTheme(next) {
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("bm-theme", next);
  paintTheme();
  if (document.documentElement.dataset.signedIn !== "1") return;
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  if (!token) return;
  await fetch("/api/v1/settings/theme", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      "X-CSRF-Token": token,
    },
    body: JSON.stringify({ theme: next }),
  });
}

document.querySelectorAll("[data-theme-value]").forEach((button) => {
  button.addEventListener("click", () => setTheme(button.dataset.themeValue));
});
document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
  button.addEventListener("click", () => setTheme(currentTheme() === "dark" ? "light" : "dark"));
});
paintTheme();

function tipHost(target) {
  if (!(target instanceof Element)) return null;
  const host = target.closest(".tip-host, .icon-tool, .invite-tool");
  return host instanceof HTMLElement ? host : null;
}

function quietTip(target) {
  const host = tipHost(target);
  if (host) host.classList.add("is-tipped");
}

function releaseTip(host, next) {
  if (!(host instanceof HTMLElement)) return;
  if (next instanceof Node && host.contains(next)) return;
  host.classList.remove("is-tipped");
}

document.addEventListener("pointerdown", (event) => quietTip(event.target), true);
document.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") quietTip(event.target);
}, true);
document.addEventListener("pointerout", (event) => {
  releaseTip(tipHost(event.target), event.relatedTarget);
}, true);
document.addEventListener("focusout", (event) => {
  const host = tipHost(event.target);
  if (host instanceof HTMLElement && host.matches(":hover")) return;
  releaseTip(host, event.relatedTarget);
}, true);
