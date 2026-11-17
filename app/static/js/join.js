const form = document.querySelector("#join-form");
const paste = document.querySelector("#join-paste");
const code = form?.querySelector("[name=code]");
const go = document.querySelector("#join-go");
const label = document.querySelector("#join-go-label");

const syncWay = () => {
  const watch = form?.querySelector("[name=way]:checked")?.value === "watch";
  if (go) go.formAction = watch ? "/join/watch" : "/join";
  if (label) label.textContent = watch ? "Наблюдать за игрой" : "Сесть за стол";
};

form?.addEventListener("change", syncWay);
syncWay();

paste?.addEventListener("click", async () => {
  if (!(code instanceof HTMLInputElement)) return;
  try {
    const text = await navigator.clipboard.readText();
    const next = text.replace(/[^a-z0-9]/gi, "").slice(0, 8);
    if (next) code.value = next;
  } catch {
    /* Клавиатурная вставка остаётся доступной, если буфер закрыт. */
  }
  code.focus();
});
