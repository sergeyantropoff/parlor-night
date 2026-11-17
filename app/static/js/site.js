for (const button of document.querySelectorAll("[data-dialog]")) {
  const dialog = document.getElementById(button.dataset.dialog || "");
  if (!(dialog instanceof HTMLDialogElement)) continue;
  button.addEventListener("click", () => dialog.showModal());
  dialog.querySelector("[data-close]")?.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}
