const dialog = document.querySelector("#lightbox");
const photo = dialog?.querySelector("[data-lightbox-image]");
const caption = dialog?.querySelector("[data-lightbox-caption]");
const previous = dialog?.querySelector("[data-lightbox-prev]");
const next = dialog?.querySelector("[data-lightbox-next]");
const SELECTOR = ".news-grid .shot img, .article-cover img, .story img, [data-cover-preview], [data-story-preview]";

let pictures = [];
let index = 0;

function shown(img) {
  if (!(img instanceof HTMLImageElement) || !img.getAttribute("src")) return false;
  const style = getComputedStyle(img);
  return style.display !== "none" && style.visibility !== "hidden";
}

function groupOf(img) {
  const root = img.closest(".article-page, .news-grid article, .news-admin, .news-editor, .story-image-dialog") || document;
  const found = [...root.querySelectorAll(SELECTOR)].filter(shown);
  return found.length ? found : [img];
}

function paint() {
  const img = pictures[index];
  if (!(photo instanceof HTMLImageElement) || !img) return;
  photo.src = img.currentSrc || img.src;
  photo.alt = img.alt || "";
  const text = (img.alt || "").trim();
  if (caption instanceof HTMLElement) {
    caption.textContent = text;
    caption.hidden = !text;
  }
  const alone = pictures.length < 2;
  if (previous instanceof HTMLButtonElement) previous.hidden = alone;
  if (next instanceof HTMLButtonElement) next.hidden = alone;
}

function open(img) {
  if (!(dialog instanceof HTMLDialogElement)) return;
  pictures = groupOf(img);
  index = Math.max(0, pictures.indexOf(img));
  paint();
  if (!dialog.open) dialog.showModal();
}

function step(delta) {
  if (pictures.length < 2) return;
  index = (index + delta + pictures.length) % pictures.length;
  paint();
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const img = target.closest(SELECTOR);
  if (!(img instanceof HTMLImageElement) || !shown(img)) return;
  if (img.closest("#news, .admin-news")) return;
  event.preventDefault();
  event.stopPropagation();
  open(img);
}, true);

dialog?.querySelector("[data-lightbox-close]")?.addEventListener("click", () => dialog.close());
previous?.addEventListener("click", () => step(-1));
next?.addEventListener("click", () => step(1));
dialog?.addEventListener("click", (event) => {
  if (event.target === dialog) dialog.close();
});
dialog?.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    step(-1);
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    step(1);
  }
});
dialog?.addEventListener("close", () => {
  if (photo instanceof HTMLImageElement) photo.removeAttribute("src");
  pictures = [];
});
