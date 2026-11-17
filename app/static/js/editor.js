async function uploadNewsImage(file) {
  const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/admin/news/images", {
    method: "POST",
    headers: { "X-CSRF-Token": token, Accept: "application/json" },
    body,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "Картинку не удалось сохранить.");
  }
  return payload.src;
}

function escapeAttr(value) {
  return value.replace(/[&"<>]/g, (char) => ({ "&": "&amp;", '"': "&quot;", "<": "&lt;", ">": "&gt;" })[char]);
}

document.querySelectorAll("[data-wysiwyg]").forEach((root) => {
  const sheet = root.querySelector(".wysiwyg-sheet");
  const field = root.querySelector("textarea");
  const form = root.closest("form");
  const picker = root.querySelector("[data-image-file]");
  if (!sheet || !field || !form) return;

  const sync = () => {
    field.value = sheet.innerHTML;
  };

  const insertImage = (src, alt) => {
    const html = `<img src="${escapeAttr(src)}" alt="${escapeAttr(alt)}">`;
    sheet.focus();
    if (!document.execCommand("insertHTML", false, html)) {
      sheet.insertAdjacentHTML("beforeend", html);
    }
    sync();
  };

  root.querySelectorAll("[data-cmd]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      const command = button.getAttribute("data-cmd") || "";
      if (command === "image") {
        picker?.click();
        return;
      }
      sheet.focus();
      if (command === "link") {
        const href = window.prompt("Адрес ссылки", "https://");
        if (!href) return;
        const allowed = /^(https?:\/\/|mailto:|\/(?!\/))/i.test(href.trim());
        if (!allowed) return;
        document.execCommand("createLink", false, href.trim());
      } else if (command === "h2" || command === "h3" || command === "blockquote" || command === "p") {
        document.execCommand("formatBlock", false, command);
      } else {
        document.execCommand(command, false, null);
      }
      sync();
    });
  });

  picker?.addEventListener("change", async () => {
    const file = picker.files && picker.files[0];
    picker.value = "";
    if (!file) return;
    const alt = window.prompt("Подпись к картинке", "");
    if (alt === null) return;
    try {
      const src = await uploadNewsImage(file);
      insertImage(src, alt);
    } catch (error) {
      window.alert(error.message);
    }
  });

  sheet.addEventListener("input", sync);
  form.addEventListener("submit", sync);
  if (!sheet.innerHTML.trim() && field.value.trim()) {
    sheet.innerHTML = field.value;
  }
  sync();
});

document.querySelectorAll("[data-cover-upload]").forEach((root) => {
  const hidden = root.querySelector('input[name="cover_file"]');
  const picker = root.querySelector("[data-cover-file]");
  const preview = root.querySelector("[data-cover-preview]");
  const clear = root.querySelector("[data-cover-clear]");
  const error = root.querySelector("[data-cover-error]");
  const preset = document.querySelector("[data-cover-preset]");
  if (!hidden || !picker || !preview) return;

  const show = (src) => {
    hidden.value = src.split("/").pop() || "";
    preview.src = src;
    preview.hidden = false;
    if (clear) clear.hidden = false;
    if (preset) preset.value = "";
    if (error) error.hidden = true;
  };

  root.querySelector("[data-cover-pick]")?.addEventListener("click", () => picker.click());
  clear?.addEventListener("click", () => {
    hidden.value = "";
    preview.hidden = true;
    preview.removeAttribute("src");
    clear.hidden = true;
  });
  preset?.addEventListener("change", () => {
    if (!preset.value) return;
    hidden.value = "";
    preview.hidden = true;
    if (clear) clear.hidden = true;
  });
  picker.addEventListener("change", async () => {
    const file = picker.files && picker.files[0];
    picker.value = "";
    if (!file) return;
    try {
      show(await uploadNewsImage(file));
    } catch (failure) {
      if (error) {
        error.textContent = failure.message;
        error.hidden = false;
      }
    }
  });
});
