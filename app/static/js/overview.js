const root = document.querySelector("#overview");
if (root) {
  const names = ["top", "summary", "games", "people", "sessions"];

  const tabs = [...root.querySelectorAll(".settings-tab")];

  function show(name) {
    const tab = names.includes(name) ? name : "top";
    for (const panel of root.querySelectorAll("[data-panel]")) {
      panel.hidden = panel.dataset.panel !== tab;
    }
    for (const button of tabs) {
      const on = button.dataset.tab === tab;
      button.setAttribute("aria-selected", on ? "true" : "false");
      button.tabIndex = on ? 0 : -1;
    }
  }

  root.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("[data-tab]") : null;
    if (!(button instanceof HTMLButtonElement)) return;
    const tab = button.dataset.tab || "top";
    show(tab);
    if (location.hash !== `#${tab}`) history.replaceState(null, "", `#${tab}`);
  });
  root.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const current = event.target instanceof Element ? event.target.closest(".settings-tab") : null;
    if (!(current instanceof HTMLButtonElement)) return;
    event.preventDefault();
    const index = tabs.indexOf(current);
    const next = event.key === "ArrowRight"
      ? tabs[(index + 1) % tabs.length]
      : tabs[(index - 1 + tabs.length) % tabs.length];
    next.focus();
    const tab = next.dataset.tab || "top";
    show(tab);
    if (location.hash !== `#${tab}`) history.replaceState(null, "", `#${tab}`);
  });
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
  show(location.hash.slice(1));

  for (const node of root.querySelectorAll("[data-size]")) {
    const pixels = node.classList.contains("day-bar") || node.parentElement?.classList.contains("strength-col");
    node.style[pixels ? "height" : "width"] = `${node.dataset.size}${pixels ? "px" : "%"}`;
  }
}
