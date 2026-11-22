for (const dialog of document.querySelectorAll("dialog[data-open='1']")) {
  if (dialog instanceof HTMLDialogElement && !dialog.open) dialog.showModal();
}

for (const opener of document.querySelectorAll("[data-open-dialog]")) {
  opener.addEventListener("click", () => {
    const dialog = document.getElementById(opener.getAttribute("data-open-dialog") || "");
    if (dialog instanceof HTMLDialogElement && !dialog.open) dialog.showModal();
  });
}

for (const closer of document.querySelectorAll("[data-close]")) {
  closer.addEventListener("click", () => {
    const dialog = closer.closest("dialog");
    if (dialog instanceof HTMLDialogElement) dialog.close();
  });
}

const intake = document.querySelector("#intake-dialog");
if (intake instanceof HTMLDialogElement) {
  intake.addEventListener("cancel", (event) => event.preventDefault());
}
const dialog = document.querySelector("#age-dialog");
const text = document.querySelector("#age-text");

function showAge(message) {
  if (!(dialog instanceof HTMLDialogElement) || !(text instanceof HTMLElement)) return;
  text.textContent = message;
  if (!dialog.open) dialog.showModal();
}

if (dialog instanceof HTMLDialogElement && dialog.dataset.open) {
  showAge(text instanceof HTMLElement ? text.textContent || "" : "");
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const trigger = target.closest("[data-age]");
  if (!(trigger instanceof HTMLElement)) return;
  event.preventDefault();
  showAge(trigger.dataset.age || "");
});

document.querySelector("#age-close")?.addEventListener("click", () => {
  if (dialog instanceof HTMLDialogElement) dialog.close();
});
