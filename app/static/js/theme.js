function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function paintTheme() {
  const theme = currentTheme();
  document.querySelectorAll("[data-theme-value]").forEach((button) => {
    button.setAttribute("aria-pressed", button.dataset.themeValue === theme ? "true" : "false");
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
paintTheme();
