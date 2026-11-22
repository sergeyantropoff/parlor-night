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

const SOURCE_LIMIT = 10 * 1024 * 1024;
const cropDialog = document.querySelector("#news-crop");
const cropStage = document.querySelector("#news-crop-stage");
const cropImage = document.querySelector("#news-crop-image");
const cropZoom = document.querySelector("#news-crop-zoom");
const cropTitle = document.querySelector("#news-crop-title");
const cropNote = document.querySelector("[data-news-crop-note]");
const cropSave = document.querySelector("#news-crop-save");
const cropError = document.querySelector("[data-news-crop-error]");
let cropOffsetX = 0;
let cropOffsetY = 0;
let cropDragging = false;
let cropLastX = 0;
let cropLastY = 0;
let cropMode = "cover";
let cropFinish = null;
let cropSaved = false;

function cropClamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function cropProblem(file) {
  if (!file) return "Выберите картинку.";
  const named = /\.(jpe?g|png|webp)$/i.test(file.name);
  const typed = /image\/(jpeg|png|webp)/.test(file.type);
  if (!named && !typed) return "Нужен JPEG, PNG или WebP.";
  if (file.size > SOURCE_LIMIT) return "Файл больше 10 МБ.";
  return "";
}

function cropFrame() {
  if (!cropStage || !(cropImage instanceof HTMLImageElement) || !cropImage.naturalWidth) return null;
  const viewW = cropStage.clientWidth;
  const viewH = cropStage.clientHeight;
  const cover = Math.max(viewW / cropImage.naturalWidth, viewH / cropImage.naturalHeight);
  const factor = cover * Number(cropZoom instanceof HTMLInputElement ? cropZoom.value : 1);
  const shownW = cropImage.naturalWidth * factor;
  const shownH = cropImage.naturalHeight * factor;
  const limitX = Math.max(0, (shownW - viewW) / 2);
  const limitY = Math.max(0, (shownH - viewH) / 2);
  cropOffsetX = cropClamp(cropOffsetX, -limitX, limitX);
  cropOffsetY = cropClamp(cropOffsetY, -limitY, limitY);
  const left = viewW / 2 + cropOffsetX - shownW / 2;
  const top = viewH / 2 + cropOffsetY - shownH / 2;
  cropImage.style.width = `${shownW}px`;
  cropImage.style.height = `${shownH}px`;
  cropImage.style.left = `${left}px`;
  cropImage.style.top = `${top}px`;
  return { viewW, viewH, shownW, shownH, left, top };
}

function resetCropFrame() {
  cropOffsetX = 0;
  cropOffsetY = 0;
  if (cropZoom instanceof HTMLInputElement) cropZoom.value = "1";
  cropFrame();
}

function releaseCropImage() {
  if (!(cropImage instanceof HTMLImageElement)) return;
  cropImage.onload = null;
  cropImage.onerror = null;
  cropImage.removeAttribute("src");
}

function cropSay(text) {
  if (!(cropError instanceof HTMLElement)) return;
  cropError.textContent = text;
  cropError.hidden = !text;
}

async function croppedNewsFile() {
  const placed = cropFrame();
  if (!placed || !(cropImage instanceof HTMLImageElement)) return null;
  const srcX = (0 - placed.left) / placed.shownW * cropImage.naturalWidth;
  const srcY = (0 - placed.top) / placed.shownH * cropImage.naturalHeight;
  const srcW = placed.viewW / placed.shownW * cropImage.naturalWidth;
  const srcH = placed.viewH / placed.shownH * cropImage.naturalHeight;
  const longEdge = cropMode === "story" ? 1500 : 1600;
  const ratio = cropMode === "story" ? 3 / 2 : 16 / 9;
  const width = longEdge;
  const height = Math.round(width / ratio);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(cropImage, srcX, srcY, srcW, srcH, 0, 0, width, height);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.86));
  if (!blob) return null;
  const name = cropMode === "story" ? "story.jpg" : "cover.jpg";
  return new File([blob], name, { type: "image/jpeg" });
}

function openNewsCrop(file, mode) {
  const problem = cropProblem(file);
  if (problem) return Promise.reject(new Error(problem));
  if (!(cropDialog instanceof HTMLDialogElement) || !(cropImage instanceof HTMLImageElement)) {
    return Promise.reject(new Error("Кадрирование недоступно."));
  }
  return new Promise((resolve, reject) => {
    cropFinish = resolve;
    cropSaved = false;
    cropMode = mode;
    cropStage?.classList.toggle("is-story", mode === "story");
    cropStage?.classList.toggle("is-cover", mode !== "story");
    if (cropTitle) cropTitle.textContent = mode === "story" ? "Фрагмент картинки" : "Фрагмент обложки";
    if (cropNote) {
      cropNote.textContent = mode === "story"
        ? "Потяните снимок, чтобы сдвинуть его. Ползунок и колёсико меняют масштаб. В кадре останется картинка 3:2. Двойной щелчок возвращает кадр в центр."
        : "Потяните снимок, чтобы сдвинуть его. Ползунок и колёсико меняют масштаб. В кадре останется обложка 16:9. Двойной щелчок возвращает кадр в центр.";
    }
    cropSay("");
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Это изображение не открывается."));
    reader.onload = () => {
      cropImage.onload = () => {
        if (!cropDialog.open) cropDialog.showModal();
        resetCropFrame();
        cropStage?.focus();
      };
      cropImage.onerror = () => {
        releaseCropImage();
        reject(new Error("Это изображение не открывается."));
      };
      cropImage.src = String(reader.result || "");
    };
    reader.readAsDataURL(file);
  });
}

cropZoom?.addEventListener("input", () => cropFrame());
cropStage?.addEventListener("pointerdown", (event) => {
  cropDragging = true;
  cropLastX = event.clientX;
  cropLastY = event.clientY;
  cropStage.setPointerCapture(event.pointerId);
  cropStage.classList.add("is-dragging");
});
cropStage?.addEventListener("pointermove", (event) => {
  if (!cropDragging) return;
  cropOffsetX += event.clientX - cropLastX;
  cropOffsetY += event.clientY - cropLastY;
  cropLastX = event.clientX;
  cropLastY = event.clientY;
  cropFrame();
});
function stopCropDrag() {
  cropDragging = false;
  cropStage?.classList.remove("is-dragging");
}
cropStage?.addEventListener("pointerup", stopCropDrag);
cropStage?.addEventListener("pointercancel", stopCropDrag);
cropStage?.addEventListener("dblclick", () => resetCropFrame());
cropStage?.addEventListener("wheel", (event) => {
  event.preventDefault();
  if (!(cropZoom instanceof HTMLInputElement)) return;
  const next = Number(cropZoom.value) + (event.deltaY < 0 ? 0.08 : -0.08);
  cropZoom.value = String(cropClamp(next, 1, 4));
  cropFrame();
}, { passive: false });
cropStage?.addEventListener("keydown", (event) => {
  const step = event.shiftKey ? 24 : 8;
  if (event.key === "ArrowLeft") cropOffsetX -= step;
  else if (event.key === "ArrowRight") cropOffsetX += step;
  else if (event.key === "ArrowUp") cropOffsetY -= step;
  else if (event.key === "ArrowDown") cropOffsetY += step;
  else if ((event.key === "+" || event.key === "=") && cropZoom instanceof HTMLInputElement) {
    cropZoom.value = String(cropClamp(Number(cropZoom.value) + 0.08, 1, 4));
  } else if ((event.key === "-" || event.key === "_") && cropZoom instanceof HTMLInputElement) {
    cropZoom.value = String(cropClamp(Number(cropZoom.value) - 0.08, 1, 4));
  } else return;
  event.preventDefault();
  cropFrame();
});
document.querySelector("#news-crop-cancel")?.addEventListener("click", () => cropDialog?.close());
cropDialog?.addEventListener("close", () => {
  releaseCropImage();
  if (!cropSaved) cropFinish?.(null);
  cropFinish = null;
});
cropSave?.addEventListener("click", async () => {
  if (!(cropSave instanceof HTMLButtonElement)) return;
  cropSave.disabled = true;
  try {
    const file = await croppedNewsFile();
    if (!file) {
      cropSay("Не удалось собрать кадр.");
      return;
    }
    cropSaved = true;
    cropFinish?.(file);
    cropFinish = null;
    cropDialog?.close();
  } finally {
    cropSave.disabled = false;
  }
});
window.addEventListener("resize", () => {
  if (cropDialog instanceof HTMLDialogElement && cropDialog.open) cropFrame();
});

document.querySelectorAll("[data-wysiwyg]").forEach((root) => {
  const sheet = root.querySelector(".wysiwyg-sheet");
  const field = root.querySelector("textarea");
  const form = root.closest("form");
  const dialog = document.querySelector("#story-image");
  const linkDialog = document.querySelector("#story-link");
  const picker = dialog?.querySelector("[data-image-file]");
  const preview = dialog?.querySelector("[data-story-preview]");
  const empty = dialog?.querySelector("[data-story-empty]");
  const drop = dialog?.querySelector("[data-story-drop]");
  const caption = dialog?.querySelector("[data-story-alt]");
  const error = dialog?.querySelector("[data-story-error]");
  const insert = dialog?.querySelector("[data-story-insert]");
  const linkField = linkDialog?.querySelector("[data-story-href]");
  const linkError = linkDialog?.querySelector("[data-story-link-error]");
  if (!sheet || !field || !form) return;
  let chosen = null;
  let previewUrl = "";
  let savedRange = null;

  const sync = () => {
    field.value = sheet.innerHTML;
  };

  const rememberSelection = () => {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return;
    const range = selection.getRangeAt(0);
    if (sheet.contains(range.commonAncestorContainer)) savedRange = range.cloneRange();
  };

  const restoreSelection = () => {
    sheet.focus();
    if (!savedRange) return;
    const selection = window.getSelection();
    if (!selection) return;
    selection.removeAllRanges();
    selection.addRange(savedRange);
  };

  const insertImage = (src, alt) => {
    const html = `<img src="${escapeAttr(src)}" alt="${escapeAttr(alt)}">`;
    restoreSelection();
    if (!document.execCommand("insertHTML", false, html)) {
      sheet.insertAdjacentHTML("beforeend", html);
    }
    sync();
  };

  const fail = (message) => {
    if (!(error instanceof HTMLElement)) return;
    error.textContent = message;
    error.hidden = false;
  };

  const resetImage = () => {
    chosen = null;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = "";
    if (picker instanceof HTMLInputElement) picker.value = "";
    if (preview instanceof HTMLImageElement) {
      preview.hidden = true;
      preview.removeAttribute("src");
    }
    if (empty instanceof HTMLElement) empty.hidden = false;
    if (caption instanceof HTMLInputElement) caption.value = "";
    if (error instanceof HTMLElement) {
      error.hidden = true;
      error.textContent = "";
    }
    if (insert instanceof HTMLButtonElement) insert.disabled = false;
  };

  root.querySelectorAll("[data-cmd]").forEach((button) => {
    button.addEventListener("mousedown", (event) => {
      event.preventDefault();
      rememberSelection();
    });
    button.addEventListener("click", (event) => {
      event.preventDefault();
      const command = button.getAttribute("data-cmd") || "";
      if (command === "image") {
        rememberSelection();
        resetImage();
        if (dialog instanceof HTMLDialogElement && !dialog.open) dialog.showModal();
        return;
      }
      sheet.focus();
      if (command === "link") {
        rememberSelection();
        if (linkField instanceof HTMLInputElement) linkField.value = "https://";
        if (linkError instanceof HTMLElement) linkError.hidden = true;
        if (linkDialog instanceof HTMLDialogElement && !linkDialog.open) linkDialog.showModal();
        linkField instanceof HTMLInputElement && linkField.focus();
        return;
      } else if (command === "h2" || command === "h3" || command === "blockquote" || command === "p") {
        document.execCommand("formatBlock", false, command);
      } else {
        document.execCommand(command, false, null);
      }
      sync();
    });
  });

  const takeStoryFile = (file) => {
    if (!file || !(preview instanceof HTMLImageElement)) return;
    chosen = file;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    preview.src = previewUrl;
    preview.hidden = false;
    if (empty instanceof HTMLElement) empty.hidden = true;
    if (error instanceof HTMLElement) error.hidden = true;
  };
  const openStoryPicker = () => {
    if (picker instanceof HTMLInputElement) picker.click();
  };
  drop?.addEventListener("click", openStoryPicker);
  drop?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openStoryPicker();
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
  const chooseStoryFile = async (file) => {
    try {
      const cropped = await openNewsCrop(file, "story");
      if (cropped) takeStoryFile(cropped);
    } catch (failure) {
      fail(failure.message || "Это изображение не открывается.");
    }
  };
  drop?.addEventListener("drop", (event) => chooseStoryFile(event.dataTransfer?.files?.[0]));
  picker?.addEventListener("change", () => {
    const file = picker instanceof HTMLInputElement ? picker.files && picker.files[0] : null;
    if (picker instanceof HTMLInputElement) picker.value = "";
    chooseStoryFile(file);
  });
  insert?.addEventListener("click", async () => {
    if (!chosen) {
      fail("Выберите картинку.");
      return;
    }
    if (insert instanceof HTMLButtonElement) insert.disabled = true;
    try {
      const src = await uploadNewsImage(chosen);
      const alt = caption instanceof HTMLInputElement ? caption.value.trim() : "";
      insertImage(src, alt);
      if (dialog instanceof HTMLDialogElement) dialog.close();
      resetImage();
    } catch (failure) {
      fail(failure.message || "Картинку не удалось сохранить.");
      if (insert instanceof HTMLButtonElement) insert.disabled = false;
    }
  });
  dialog?.addEventListener("close", resetImage);
  linkDialog?.querySelector("[data-story-link-insert]")?.addEventListener("click", () => {
    const href = linkField instanceof HTMLInputElement ? linkField.value.trim() : "";
    const allowed = /^(https?:\/\/|mailto:|\/(?!\/))/i.test(href);
    if (!href || !allowed) {
      if (linkError instanceof HTMLElement) {
        linkError.textContent = "Нужен адрес https, почта или ссылка внутри гостиной.";
        linkError.hidden = false;
      }
      return;
    }
    restoreSelection();
    document.execCommand("createLink", false, href);
    sync();
    if (linkDialog instanceof HTMLDialogElement) linkDialog.close();
  });

  sheet.addEventListener("input", sync);
  form.addEventListener("submit", sync);
  if (!sheet.innerHTML.trim() && field.value.trim()) {
    sheet.innerHTML = field.value;
  }
  sync();
});

document.querySelectorAll("[data-cover-upload]").forEach((root) => {
  const hidden = root.querySelector("input[type='hidden']");
  const picker = root.querySelector("[data-cover-file]");
  const preview = root.querySelector("[data-cover-preview]");
  const empty = root.querySelector("[data-cover-empty]");
  const clear = root.querySelector("[data-cover-clear]");
  const error = root.querySelector("[data-cover-error]");
  const drop = root.querySelector("[data-cover-drop]");
  const preset = document.querySelector("[data-cover-preset]");
  if (!hidden || !picker || !preview || !drop) return;

  const show = (src) => {
    hidden.value = src.split("/").pop() || "";
    preview.src = src;
    preview.hidden = false;
    if (empty) empty.hidden = true;
    if (clear) clear.hidden = false;
    if (preset) preset.value = "";
    if (error) error.hidden = true;
  };
  const wipe = () => {
    hidden.value = "";
    preview.hidden = true;
    preview.removeAttribute("src");
    if (empty) empty.hidden = false;
    if (clear) clear.hidden = true;
  };

  const openPicker = () => picker.click();
  drop.addEventListener("click", openPicker);
  drop.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openPicker();
    }
  });
  ["dragenter", "dragover"].forEach((name) => {
    drop.addEventListener(name, (event) => {
      event.preventDefault();
      drop.classList.add("is-over");
    });
  });
  ["dragleave", "drop"].forEach((name) => {
    drop.addEventListener(name, (event) => {
      event.preventDefault();
      drop.classList.remove("is-over");
    });
  });
  clear?.addEventListener("click", wipe);
  preset?.addEventListener("change", () => {
    if (preset.value) wipe();
  });
  const accept = async (file) => {
    if (!file) return;
    try {
      const cropped = await openNewsCrop(file, "cover");
      if (!cropped) return;
      show(await uploadNewsImage(cropped));
    } catch (failure) {
      if (error) {
        error.textContent = failure.message;
        error.hidden = false;
      }
    }
  };
  drop.addEventListener("drop", (event) => accept(event.dataTransfer?.files?.[0]));
  picker.addEventListener("change", () => {
    const file = picker.files && picker.files[0];
    picker.value = "";
    accept(file);
  });
});
