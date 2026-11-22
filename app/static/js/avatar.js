const drop = document.querySelector("#avatar-drop");
const input = document.querySelector("#avatar-file");
const preview = document.querySelector("#avatar-preview");
const note = document.querySelector("#avatar-note");
const clear = document.querySelector("#avatar-clear");
const dialog = document.querySelector("#avatar-crop");
const stage = document.querySelector("#crop-stage");
const image = document.querySelector("#crop-image");
const zoom = document.querySelector("#crop-zoom");
const save = document.querySelector("#crop-save");
const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
const LIMIT = 10 * 1024 * 1024;
const STORED = 512;

let offsetX = 0;
let offsetY = 0;
let dragging = false;
let lastX = 0;
let lastY = 0;

function say(text, failed = false) {
  if (!note) return;
  note.textContent = text;
  note.classList.toggle("is-bad", failed);
}

function paint(src) {
  if (!preview) return;
  preview.replaceChildren();
  if (src) {
    const photo = document.createElement("img");
    photo.alt = "";
    photo.src = src;
    preview.append(photo);
    clear?.removeAttribute("hidden");
    const pill = document.querySelector(".topbar .person-link .avatar");
    if (pill) {
      const next = document.createElement("img");
      next.className = "avatar";
      next.alt = "";
      next.src = src;
      pill.replaceWith(next);
    }
    return;
  }
  const letter = document.createElement("span");
  letter.className = `avatar tone-${preview.dataset.tone || "0"}`;
  letter.textContent = preview.dataset.letter || "?";
  preview.append(letter);
  clear?.setAttribute("hidden", "hidden");
  const photo = document.querySelector(".topbar .person-link img.avatar");
  if (photo) photo.replaceWith(letter.cloneNode(true));
}

function release() {
  if (!image) return;
  image.onload = null;
  image.onerror = null;
  image.removeAttribute("src");
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function frame() {
  if (!stage || !image || !image.naturalWidth) return null;
  const view = stage.clientWidth;
  const cover = Math.max(view / image.naturalWidth, view / image.naturalHeight);
  const factor = cover * Number(zoom?.value || 1);
  const shownW = image.naturalWidth * factor;
  const shownH = image.naturalHeight * factor;
  const limitX = Math.max(0, (shownW - view) / 2);
  const limitY = Math.max(0, (shownH - view) / 2);
  offsetX = clamp(offsetX, -limitX, limitX);
  offsetY = clamp(offsetY, -limitY, limitY);
  const left = view / 2 + offsetX - shownW / 2;
  const top = view / 2 + offsetY - shownH / 2;
  image.style.width = `${shownW}px`;
  image.style.height = `${shownH}px`;
  image.style.left = `${left}px`;
  image.style.top = `${top}px`;
  return { view, shownW, shownH, left, top };
}

function resetFrame() {
  offsetX = 0;
  offsetY = 0;
  if (zoom) zoom.value = "1";
  frame();
}

function openCrop(file) {
  if (!file || !dialog || !image) return;
  const named = /\.(jpe?g|png|webp)$/i.test(file.name);
  const typed = /image\/(jpeg|png|webp)/.test(file.type);
  if (!named && !typed) {
    say("Нужен JPEG, PNG или WebP.", true);
    return;
  }
  if (file.size > LIMIT) {
    say("Файл больше 10 МБ.", true);
    return;
  }
  release();
  const reader = new FileReader();
  reader.onerror = () => say("Это изображение не открывается.", true);
  reader.onload = () => {
    image.onload = () => {
      if (!dialog.open) dialog.showModal();
      resetFrame();
      stage?.focus();
    };
    image.onerror = () => {
      release();
      say("Это изображение не открывается.", true);
    };
    image.src = String(reader.result || "");
  };
  reader.readAsDataURL(file);
}

async function send(file) {
  if (!file) return false;
  say("Загружаем портрет…");
  const body = new FormData();
  body.append("file", file);
  let response;
  try {
    response = await fetch("/settings/avatar", {
      method: "POST",
      headers: { "X-CSRF-Token": token, Accept: "application/json" },
      body,
    });
  } catch {
    say("Не удалось отправить файл.", true);
    return false;
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    say(data.error || "Портрет не принят.", true);
    return false;
  }
  paint(`${data.src}?t=${Date.now()}`);
  if (note) note.textContent = "";
  window.pnToast?.("Портрет сохранён.");
  return true;
}

function squareCanvas(side) {
  const canvas = document.createElement("canvas");
  canvas.width = side;
  canvas.height = side;
  return canvas;
}

async function croppedFile() {
  const placed = frame();
  if (!placed || !image) return null;
  const srcX = (0 - placed.left) / placed.shownW * image.naturalWidth;
  const srcY = (0 - placed.top) / placed.shownH * image.naturalHeight;
  const srcW = placed.view / placed.shownW * image.naturalWidth;
  const srcH = placed.view / placed.shownH * image.naturalHeight;
  const cropEdge = Math.max(1, Math.round(Math.max(srcW, srcH)));
  const extract = Math.min(cropEdge, 2048);
  const cropped = squareCanvas(extract);
  const cropContext = cropped.getContext("2d");
  if (!cropContext) return null;
  cropContext.imageSmoothingEnabled = true;
  cropContext.imageSmoothingQuality = "high";
  cropContext.drawImage(image, srcX, srcY, srcW, srcH, 0, 0, extract, extract);
  const side = Math.min(STORED, extract);
  const stored = side === extract ? cropped : squareCanvas(side);
  if (stored !== cropped) {
    const context = stored.getContext("2d");
    if (!context) return null;
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = "high";
    context.drawImage(cropped, 0, 0, extract, extract, 0, 0, side, side);
  }
  const blob = await new Promise((resolve) => stored.toBlob(resolve, "image/jpeg", 0.86));
  if (!blob) return null;
  return new File([blob], "portrait.jpg", { type: "image/jpeg" });
}

drop?.addEventListener("click", () => input?.click());
drop?.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    input?.click();
  }
});
["dragenter", "dragover"].forEach((name) => {
  drop?.addEventListener(name, (event) => {
    event.preventDefault();
    drop.classList.add("is-over");
  });
});
["dragleave", "drop"].forEach((name) => {
  drop?.addEventListener(name, (event) => {
    event.preventDefault();
    drop.classList.remove("is-over");
  });
});
drop?.addEventListener("drop", (event) => openCrop(event.dataTransfer?.files?.[0]));
input?.addEventListener("change", () => {
  openCrop(input.files?.[0]);
  input.value = "";
});

zoom?.addEventListener("input", () => frame());
stage?.addEventListener("pointerdown", (event) => {
  dragging = true;
  lastX = event.clientX;
  lastY = event.clientY;
  stage.setPointerCapture(event.pointerId);
  stage.classList.add("is-dragging");
});
stage?.addEventListener("pointermove", (event) => {
  if (!dragging) return;
  offsetX += event.clientX - lastX;
  offsetY += event.clientY - lastY;
  lastX = event.clientX;
  lastY = event.clientY;
  frame();
});
function stopDrag() {
  dragging = false;
  stage?.classList.remove("is-dragging");
}
stage?.addEventListener("pointerup", stopDrag);
stage?.addEventListener("pointercancel", stopDrag);
stage?.addEventListener("dblclick", () => resetFrame());
stage?.addEventListener("wheel", (event) => {
  event.preventDefault();
  if (!zoom) return;
  const next = Number(zoom.value) + (event.deltaY < 0 ? 0.08 : -0.08);
  zoom.value = String(clamp(next, 1, 4));
  frame();
}, { passive: false });
stage?.addEventListener("keydown", (event) => {
  const step = event.shiftKey ? 24 : 8;
  if (event.key === "ArrowLeft") offsetX -= step;
  else if (event.key === "ArrowRight") offsetX += step;
  else if (event.key === "ArrowUp") offsetY -= step;
  else if (event.key === "ArrowDown") offsetY += step;
  else if (event.key === "+" || event.key === "=") zoom.value = String(clamp(Number(zoom.value) + 0.08, 1, 4));
  else if (event.key === "-" || event.key === "_") zoom.value = String(clamp(Number(zoom.value) - 0.08, 1, 4));
  else return;
  event.preventDefault();
  frame();
});

document.querySelector("#crop-cancel")?.addEventListener("click", () => dialog?.close());
dialog?.addEventListener("close", release);
save?.addEventListener("click", async () => {
  save.disabled = true;
  try {
    const file = await croppedFile();
    if (!file) {
      say("Не удалось собрать портрет.", true);
      return;
    }
    if (await send(file)) dialog?.close();
  } finally {
    save.disabled = false;
  }
});

clear?.addEventListener("click", async () => {
  say("Убираем портрет…");
  let response;
  try {
    response = await fetch("/settings/avatar/remove", {
      method: "POST",
      headers: { "X-CSRF-Token": token, Accept: "application/json" },
    });
  } catch {
    say("Не удалось убрать портрет.", true);
    return;
  }
  if (!response.ok) {
    say("Не удалось убрать портрет.", true);
    return;
  }
  paint("");
  if (note) note.textContent = "";
  window.pnToast?.("Портрет убран.");
});

window.addEventListener("resize", () => {
  if (dialog?.open) frame();
});
