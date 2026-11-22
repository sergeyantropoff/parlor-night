function drawPager(nav, page, pages, choose) {
  nav.replaceChildren();
  nav.hidden = pages <= 1;
  if (pages <= 1) return;
  const back = document.createElement("button");
  back.type = "button";
  back.className = "pager-step";
  back.textContent = "Назад";
  back.disabled = page <= 1;
  if (page <= 1) back.classList.add("is-off");
  else back.addEventListener("click", () => choose(page - 1));
  const list = document.createElement("ol");
  for (const number of links(page, pages)) {
    const item = document.createElement("li");
    if (number == null) {
      item.className = "pager-gap";
      item.setAttribute("aria-hidden", "true");
      item.textContent = "…";
    } else if (number === page) {
      const current = document.createElement("span");
      current.setAttribute("aria-current", "page");
      current.textContent = String(number);
      item.append(current);
    } else {
      const jump = document.createElement("button");
      jump.type = "button";
      jump.textContent = String(number);
      jump.addEventListener("click", () => choose(number));
      item.append(jump);
    }
    list.append(item);
  }
  const forward = document.createElement("button");
  forward.type = "button";
  forward.className = "pager-step";
  forward.textContent = "Дальше";
  forward.disabled = page >= pages;
  if (page >= pages) forward.classList.add("is-off");
  else forward.addEventListener("click", () => choose(page + 1));
  nav.append(back, list, forward);
}

function links(page, pages) {
  if (pages <= 7) return Array.from({ length: pages }, (_, index) => index + 1);
  const wanted = [1, pages, page - 1, page, page + 1].filter((number, index, all) => (
    number >= 1 && number <= pages && all.indexOf(number) === index
  )).sort((left, right) => left - right);
  const out = [];
  let previous = 0;
  for (const number of wanted) {
    if (previous && number - previous > 1) out.push(null);
    out.push(number);
    previous = number;
  }
  return out;
}

export function attachPager(list, {
  size = 8,
  label = "Страницы",
  newest = false,
  match = null,
  anchor = null,
  initial = 0,
  onPaint = null,
} = {}) {
  let page = Number(initial) || 0;
  let follow = Boolean(newest);
  const nav = document.createElement("nav");
  nav.className = "pager";
  nav.setAttribute("aria-label", label);
  (anchor || list).insertAdjacentElement("afterend", nav);

  const paint = ({ reset = false } = {}) => {
    const rows = [...list.querySelectorAll(":scope > [data-page-row]")];
    const visible = match ? rows.filter((row) => match(row)) : rows;
    const pages = Math.max(1, Math.ceil(visible.length / size) || 1);
    if (reset || page === 0 || (follow && newest)) page = newest ? pages : 1;
    page = Math.min(Math.max(page, 1), pages);
    const start = (page - 1) * size;
    const end = start + size;
    const shown = new Set(visible.slice(start, end));
    for (const row of rows) row.hidden = !shown.has(row);
    drawPager(nav, page, pages, (next) => {
      follow = newest && next === pages;
      page = next;
      paint();
    });
    const state = { page, pages, count: visible.length };
    onPaint?.(state);
    return state;
  };
  return paint;
}
