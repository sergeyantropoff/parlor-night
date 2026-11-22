"""Ужимает растровые картинки и сохраняет WebP.

Потолок вёрстки — окно около 2560×1600: стол, фон и обложки на таком экране
крупные, поэтому их пиксели не уменьшаем, только сжимаем. Мелкие значки
считаем как 2× их CSS-размера и ещё 40% запаса, чтобы картинку можно было
увеличить. Логотип шапки остаётся PNG. Крупные дубли «Идёт игра» не храним:
для карточки хватает варианта на 480px.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "app" / "static"
RETINA = 2 * 1.4


def css_px(rel: str) -> int:
    """Ширина картинки в CSS-пикселях на большом мониторе."""
    name = rel.rsplit("/", 1)[-1]
    if "logo-mark" in name:
        return 92
    if "logo-lockup" in name:
        return 480
    if name.startswith("table-"):
        return 2200
    if name.startswith("chips-stack") or name.startswith("chip-coin"):
        return 180
    if name.startswith("card-back") or "/cards/" in rel:
        return 240
    if name == "computer-avatar.jpg":
        return 128
    if name.startswith("go-board") or name == "go-felt.png":
        return 1600
    if name.startswith("go-bowl"):
        return 200
    if name.startswith("go-stone"):
        return 88
    if "pieces/" in rel or "/images/nardy/" in rel and not name.startswith("board"):
        return 180
    if name.startswith("board") and "/nardy/" in rel:
        return 1024
    if "images/games/" in rel:
        return 240
    if "images/podium/" in rel:
        return 460
    if "images/table-tools/" in rel:
        return 64
    if name.startswith("game-") and "/parlor/" in rel:
        return 720
    if name.startswith("news-"):
        return 1280
    if "hero-background" in name:
        return 2560
    if "hero-parlor" in name:
        return 960
    if "footer-still" in name:
        return 520
    if name.startswith("github-star"):
        return 186
    if "sidebar-walnut" in name:
        return 280
    if name.startswith("ongoing-"):
        return 200
    if "invite-still" in name:
        return 960
    if "/cats/" in rel:
        return 420
    if "/call/" in rel:
        return 320
    if name.startswith("error-"):
        return 720
    return 960


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
        before += size
        name = path.name
        if name.startswith("ongoing-") and not name.endswith("-480.webp"):
            path.unlink()
            print(f"drop  {size / 1024:7.0f}K  {rel}", flush=True)
            continue
        if name == "sidebar-walnut.png":
            path.unlink()
            print(f"drop  {size / 1024:7.0f}K  {rel}", flush=True)
            continue
        limit = max(1, round(css_px(rel) * RETINA))
        image = Image.open(path)
        image.load()
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
