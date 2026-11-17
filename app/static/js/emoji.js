const FACES = [
  "😊", "😄", "😉", "😁", "😂", "😅", "😍", "😘",
  "😎", "🤔", "😴", "😢", "😡", "👍", "👎", "👏",
  "🙏", "🔥", "❤️", "🎉", "🤝", "👀", "🍀", "☕",
  "♟️", "♠️", "♥️", "♦️", "♣️", "✅",
];

function place(field, face) {
  const start = field.selectionStart ?? field.value.length;
  const end = field.selectionEnd ?? start;
  const limit = Number(field.getAttribute("maxlength")) || 0;
  const next = field.value.slice(0, start) + face + field.value.slice(end);
  field.value = limit > 0 ? next.slice(0, limit) : next;
  const caret = Math.min(start + face.length, field.value.length);
  field.focus();
  field.setSelectionRange(caret, caret);
  field.dispatchEvent(new Event("input", { bubbles: true }));
}

export function mountEmoji(root = document) {
  for (const button of root.querySelectorAll("[data-emoji-for]")) {
    if (!(button instanceof HTMLButtonElement) || button.dataset.emojiReady) continue;
    const field = document.getElementById(button.dataset.emojiFor || "");
    if (!(field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement)) continue;
    button.dataset.emojiReady = "1";
    const pop = document.createElement("div");
    pop.className = "emoji-pop";
    pop.hidden = true;
    pop.setAttribute("role", "listbox");
    pop.setAttribute("aria-label", "Смайлики");
    for (const face of FACES) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "emoji-face";
      item.textContent = face;
      item.setAttribute("role", "option");
      item.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        place(field, face);
        pop.hidden = true;
        button.setAttribute("aria-expanded", "false");
      });
      pop.append(item);
    }
    const host = document.createElement("span");
    host.className = "emoji-host";
    button.replaceWith(host);
    host.append(button, pop);
    const shut = () => {
      pop.hidden = true;
      button.setAttribute("aria-expanded", "false");
    };
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const open = pop.hidden;
      pop.hidden = !open;
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", (event) => {
      if (pop.hidden || !(event.target instanceof Node)) return;
      if (pop.contains(event.target) || button.contains(event.target)) return;
      shut();
    });
  }
}
