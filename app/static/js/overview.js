const root = document.querySelector("#overview");
if (root) {
  const names = ["summary", "games", "people", "sessions"];

  function show(name) {
    const tab = names.includes(name) ? name : "summary";
    for (const panel of root.querySelectorAll("[data-panel]")) {
      panel.hidden = panel.dataset.panel !== tab;
    }
    for (const button of root.querySelectorAll("[data-tab]")) {
      const on = button.dataset.tab === tab;
      button.setAttribute("aria-selected", on ? "true" : "false");
      button.classList.toggle("secondary", !on);
    }
  }

  root.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("[data-tab]") : null;
    if (!(button instanceof HTMLButtonElement)) return;
    const tab = button.dataset.tab || "summary";
    show(tab);
    if (location.hash !== `#${tab}`) history.replaceState(null, "", `#${tab}`);
  });
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
  show(location.hash.slice(1));

  for (const node of root.querySelectorAll("[data-size]")) {
    const pixels = node.classList.contains("day-bar") || node.parentElement?.classList.contains("strength-col");
    node.style[pixels ? "height" : "width"] = `${node.dataset.size}${pixels ? "px" : "%"}`;
  }

  const opener = document.querySelector("#clear-games");
  const dialog = document.querySelector("#clear-dialog");
  const cancel = document.querySelector("#clear-cancel");
  if (opener instanceof HTMLButtonElement && dialog instanceof HTMLDialogElement) {
    opener.addEventListener("click", () => dialog.showModal());
    if (cancel instanceof HTMLButtonElement) cancel.addEventListener("click", () => dialog.close());
  }
}
