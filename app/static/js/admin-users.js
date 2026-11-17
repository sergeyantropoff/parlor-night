import { attachPager } from "./pager.js";

const root = document.querySelector("#guests");
const rows = document.querySelector("#guest-rows");
if (root && rows) {
  const openId = root.dataset.open;
  if (openId) document.getElementById(openId)?.showModal();

  for (const button of root.querySelectorAll("[data-dialog]")) {
    button.addEventListener("click", () => {
      const dialog = document.getElementById(button.dataset.dialog);
      if (!dialog) return;
      dialog.showModal();
      dialog.querySelector("input[name='username']")?.focus();
    });
  }
  for (const dialog of root.querySelectorAll("dialog.social-dialog")) {
    dialog.querySelector("[data-close]")?.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  }

  const search = root.querySelector("#guest-search");
  const range = root.querySelector("#guest-range");
  const empty = root.querySelector("#guest-empty");
  const emptyCell = empty?.querySelector("td");
  const bar = root.querySelector("#guest-pager");
  const size = 20;
  const params = new URLSearchParams(location.search);
  if (search) search.value = params.get("q") || "";

  const fold = (value) => String(value || "").toLocaleLowerCase("ru").replaceAll("ё", "е").replace(/\s+/g, " ").trim();
  const haystack = new Map([...rows.querySelectorAll("[data-page-row]")].map((row) => [row, fold(row.dataset.find)]));
  const match = (row) => {
    const hay = haystack.get(row) || "";
    return fold(search?.value).split(" ").filter(Boolean).every((token) => hay.includes(token));
  };
  const remember = (page) => {
    const query = fold(search?.value);
    const next = new URLSearchParams();
    if (query) next.set("q", query);
    if (page > 1) next.set("page", String(page));
    const tail = next.toString();
    history.replaceState(null, "", tail ? `${location.pathname}?${tail}` : location.pathname);
    for (const field of root.querySelectorAll("[data-keep='q']")) field.value = query;
    for (const field of root.querySelectorAll("[data-keep='page']")) field.value = String(page);
  };
  const paint = attachPager(rows, {
    size,
    label: "Страницы гостей",
    anchor: bar,
    initial: params.has("tail") ? 1_000_000 : Number(params.get("page") || 1),
    match,
    onPaint: ({ page, count }) => {
      const start = count ? (page - 1) * size + 1 : 0;
      const end = Math.min(count, page * size);
      if (range) range.textContent = count ? `${start}–${end} из ${count}` : "";
      if (empty) empty.hidden = count > 0;
      if (emptyCell) {
        emptyCell.textContent = haystack.size && fold(search?.value)
          ? "Никого не нашлось."
          : "Пока никого нет.";
      }
      remember(page);
    },
  });
  if (bar?.nextElementSibling?.classList.contains("pager")) bar.prepend(bar.nextElementSibling);
  search?.addEventListener("input", () => paint({ reset: true }));
  paint();
}
