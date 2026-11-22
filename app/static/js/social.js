import { mountEmoji } from "./emoji.js";
import { attachPager } from "./pager.js";

const root = document.querySelector("[data-social]");
if (root) {
  const openId = root.dataset.open;
  if (openId) document.getElementById(openId)?.showModal();

  for (const button of root.querySelectorAll("[data-dialog]")) {
    button.addEventListener("click", () => {
      document.getElementById(button.dataset.dialog)?.showModal();
    });
  }
  for (const dialog of document.querySelectorAll("dialog.social-dialog")) {
    dialog.querySelector("[data-close]")?.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  }

  const rows = [...root.querySelectorAll("[data-friend]")];
  const filters = [...root.querySelectorAll("[data-friend-filter]")];
  const search = root.querySelector("#friend-search");
  const shown = root.querySelector("#friend-shown");
  const empty = root.querySelector("#friend-empty");
  const list = root.querySelector(".directory-body");
  const pageSize = 6;
  let filter = "all";

  const friendMatch = (row) => {
    const term = (search?.value || "").trim().toLowerCase();
    if (term && !(row.dataset.name || "").includes(term)) return false;
    const bucket = row.dataset.bucket;
    if (filter === "requests") return bucket === "incoming";
    if (bucket === "incoming") return false;
    if (filter === "online") return row.dataset.live === "1" && bucket === "accepted";
    return true;
  };

  const paintFriends = list
    ? attachPager(list, {
      size: pageSize,
      label: "Страницы друзей",
      match: friendMatch,
      onPaint: ({ page, count }) => {
        const start = count ? (page - 1) * pageSize + 1 : 0;
        const end = Math.min(count, page * pageSize);
        if (empty) {
          empty.hidden = count > 0;
          empty.textContent = rows.length
            ? "Никого не нашлось."
            : "Пока никого нет. Добавьте игрока по логину.";
        }
        if (shown) {
          shown.textContent = count
            ? `Показано ${start}–${end} из ${count}`
            : "Никого не нашлось";
        }
      },
    })
    : null;

  for (const button of filters) {
    button.addEventListener("click", () => {
      filter = button.dataset.friendFilter || "all";
      for (const item of filters) item.setAttribute("aria-pressed", String(item === button));
      paintFriends?.({ reset: true });
    });
  }
  search?.addEventListener("input", () => paintFriends?.({ reset: true }));
  paintFriends?.();

  const requests = root.querySelector("#request-list");
  if (requests) attachPager(requests, { size: 5, label: "Страницы заявок" })();

  const chatSearch = root.querySelector("#chat-search");
  const inbox = root.querySelector("#inbox-list");
  if (inbox) {
    const paintInbox = attachPager(inbox, {
      size: 8,
      label: "Страницы бесед",
      match: (row) => {
        const term = (chatSearch?.value || "").trim().toLowerCase();
        return !term || (row.dataset.chat || "").includes(term);
      },
    });
    chatSearch?.addEventListener("input", () => paintInbox({ reset: true }));
    paintInbox();
  }

  mountEmoji(root);

  const body = root.querySelector("#chat-body");
  body?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      body.form?.requestSubmit();
    }
  });
  const transcript = root.querySelector("#transcript");
  if (transcript?.querySelector("[data-page-row]")) {
    const paintThread = attachPager(transcript, { size: 20, newest: true, label: "Страницы переписки" });
    const state = paintThread();
    if (state.page === state.pages) transcript.scrollTop = transcript.scrollHeight;
  } else if (transcript) {
    transcript.scrollTop = transcript.scrollHeight;
  }

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    for (const menu of root.querySelectorAll("details[open]")) {
      if (!menu.contains(target)) menu.removeAttribute("open");
    }
  });

  if (location.hash === "#requests") {
    root.querySelector("[data-friend-filter='requests']")?.click();
  }
}
