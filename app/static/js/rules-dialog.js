const dialog = document.querySelector("#rules-dialog");
if (dialog instanceof HTMLDialogElement) {
  const body = dialog.querySelector(".rules-body");
  const heading = dialog.querySelector("#rules-title");

  const open = (key) => {
    if (key) {
      let title = "";
      for (const pane of dialog.querySelectorAll("[data-rules-pane]")) {
        const on = pane.dataset.rulesPane === key;
        pane.hidden = !on;
        if (on) title = pane.dataset.rulesTitle || "";
      }
      if (heading && title) heading.textContent = title;
    }
    if (body) body.scrollTop = 0;
    if (!dialog.open) dialog.showModal();
  };

  document.querySelector("#rules")?.addEventListener("click", () => open(""));
  for (const button of document.querySelectorAll("[data-rules]")) {
    button.addEventListener("click", () => open(button.dataset.rules || ""));
  }
  for (const button of dialog.querySelectorAll("[data-close]")) {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      dialog.close();
    });
  }
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener("close", () => {
    if (body) body.scrollTop = 0;
  });
}
