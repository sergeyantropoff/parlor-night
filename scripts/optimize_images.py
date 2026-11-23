"""Ужимает декоративные картинки до нужного размера на большом экране плюс 40%.

Большой экран — окно 2560px. Публичные блоки шире 1280 не становятся.
Пиксели файла = CSS-ширина этого места × 1.4, чтобы картинка оставалась
чёткой и не весила лишнего. Игровые спрайты, сукно и логотип не трогаем:
их рисуют крупно и в разном масштабе. Логотип шапки остаётся PNG.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "app" / "static"
HEADROOM = 1.4


def css_px(rel: str) -> int | None:
    """Ширина в CSS-пикселях на большом экране. None — файл не уменьшаем."""
    name = rel.rsplit("/", 1)[-1]
    if name.startswith("game-") and rel.startswith("parlor/"):
        return 533
    if name.startswith("news-") or "hero-parlor" in name:
        return 1280 if name.startswith("news-") else 680
    if "hero-background" in name:
        return 2560
    if "footer-still" in name:
        return 520
    if name.startswith("plans"):
        return 640
    if name.startswith("github-star"):
        return 186
    if "/call/" in rel:
        return 125
    if "invite-still" in name:
        return 949
    if name.startswith("error-"):
        return 600
    if "images/podium/" in rel:
        return 233
    if "images/games/" in rel:
        return 311
    return None


def quality(rel: str) -> int:
    if any(part in rel for part in ("/pieces/", "logo-", "card-back", "chips-stack", "chip-coin", "go-stone", "table-tools/")):
        return 88
    return 82


def fit(image: Image.Image, max_width: int) -> Image.Image:
    if image.width <= max_width:
        return image
    height = max(1, round(image.height * max_width / image.width))
    return image.resize((max_width, height), Image.Resampling.LANCZOS)


def main() -> None:
    before = 0
    after = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        size = path.stat().st_size
        name = path.name
        if name.startswith("ongoing-") and not name.endswith("-480.webp"):
            path.unlink()
            print(f"drop  {size / 1024:7.0f}K  {rel}", flush=True)
            continue
        if name == "sidebar-walnut.png":
            path.unlink()
            print(f"drop  {size / 1024:7.0f}K  {rel}", flush=True)
            continue
        needed = css_px(rel)
        if needed is None:
            continue
        limit = max(1, round(needed * HEADROOM))
        image = Image.open(path)
        image.load()
        if image.width <= limit:
            continue
        before += size
        resized = fit(image, limit)
        keep_png = "logo-mark" in name
        dest = path if keep_png or path.suffix.lower() == ".webp" else path.with_suffix(".webp")
        if keep_png:
            resized.save(dest, "PNG", optimize=True, compress_level=9)
        else:
            resized.save(dest, "WEBP", quality=quality(rel), method=6)
        if dest != path:
            path.unlink()
        new_size = dest.stat().st_size
        after += new_size
        note = f"{image.width}x{image.height} -> {resized.width}x{resized.height}"
        print(f"{size / 1024:7.0f}K -> {new_size / 1024:6.0f}K  {note:22}  {dest.relative_to(ROOT).as_posix()}", flush=True)
    print(f"TOTAL {before / 1024 / 1024:.1f}MB -> {after / 1024 / 1024:.1f}MB")


if __name__ == "__main__":
    main()
