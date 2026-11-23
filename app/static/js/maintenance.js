const bannerOf = () => document.querySelector(".maintenance-banner");

function showMaintenance(text) {
  const message = String(text || "").trim();
  let banner = bannerOf();
  if (!message) {
    banner?.remove();
    return;
  }
  if (!banner) {
    banner = document.createElement("p");
    banner.className = "maintenance-banner";
    banner.setAttribute("role", "status");
    const skip = document.querySelector("body > .skip");
    if (skip) skip.after(banner);
    else document.body.prepend(banner);
  }
  if (banner.textContent !== message) banner.textContent = message;
}

async function watchMaintenance() {
  if (document.hidden) return;
  try {
    const response = await fetch("/api/v1/maintenance", { headers: { Accept: "application/json" } });
    if (!response.ok) return;
    const data = await response.json();
    showMaintenance(data.maintenance ? data.text : "");
  } catch {
    /* следующий круг повторит запрос */
  }
}

watchMaintenance();
window.setInterval(watchMaintenance, 4000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) watchMaintenance();
});
