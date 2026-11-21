"""Собирает графику нард: выбивает чёрный фон и укладывает в размер экрана.

Крупные обложки не увеличиваем. Мелкие шашки, кости и куб считаем как
2× размера на столе и ещё 40% запаса. Исходники лежат вне репозитория.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path("/Users/inecs/.cursor/projects/Users-inecs-Parlor-Night/assets")
STATIC = ROOT / "app" / "static"
DOCS = ROOT / "docs" / "images" / "games"


def find(token: str) -> Path:
    found = list(ASSETS.glob(f"*{token}*"))
    if len(found) != 1:
        raise SystemExit(f"{token}: {len(found)} files")
    return found[0]


def knock(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            peak = max(red, green, blue)
            if peak < 28:
                pixels[x, y] = (red, green, blue, 0)
            elif peak < 48:
                fade = int(alpha * (peak - 28) / 20)
                pixels[x, y] = (red, green, blue, max(0, min(alpha, fade)))
    bbox = rgba.getbbox()
    return rgba.crop(bbox) if bbox else rgba


def fit(image: Image.Image, width: int) -> Image.Image:
    if image.width <= width:
        return image
    height = max(1, round(image.height * width / image.width))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def cover(image: Image.Image, width: int, height: int) -> Image.Image:
    image = image.convert("RGB")
    scale = max(width / image.width, height / image.height)
    if scale >= 1:
        aspect = width / height
        if image.width / image.height > aspect:
            crop_w = max(1, round(image.height * aspect))
            crop_h = image.height
        else:
            crop_w = image.width
            crop_h = max(1, round(image.width / aspect))
        left = max(0, (image.width - crop_w) // 2)
        top = max(0, (image.height - crop_h) // 2)
        return image.crop((left, top, left + crop_w, top + crop_h))
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def save(image: Image.Image, path: Path, quality: int = 82) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "WEBP", quality=quality, method=6)
    print(f"{image.width}x{image.height}  {path.stat().st_size / 1024:6.0f}K  {path.relative_to(ROOT)}")


def piece(token: str, name: str) -> None:
    image = knock(Image.open(find(token)))
    save(fit(image, 504), STATIC / "images" / "nardy" / name, 86)


def scene(token: str, width: int, height: int, *paths: Path) -> None:
    image = cover(Image.open(find(token)).convert("RGB"), width, height)
    for path in paths:
        save(image, path)


def main() -> None:
    board = Image.open(find("bf117a72")).convert("RGB")
    save(fit(board, 1024), STATIC / "images" / "nardy" / "board.webp", 82)
    for face, token in (
        (1, "6b37be7e"),
        (2, "4d0ae140"),
        (3, "f400bb1f"),
        (4, "5f5ec42c"),
        (5, "f36b6cb4"),
        (6, "f559a6a6"),
    ):
        piece(token, f"die-{face}.webp")
    for face, token in ((2, "01d1c958"), (4, "ee97b5c2"), (8, "884bbf9b"), (16, "844850dc"), (32, "698ac4e3"), (64, "bda66cda")):
        piece(token, f"cube-{face}.webp")
    piece("74cef9b5", "checker-light.webp")
    piece("1affcfe6", "checker-dark.webp")
    scene("214db232", 768, 576, STATIC / "parlor/light/game-nardy.webp", DOCS / "nardy.webp")
    scene("61f3a485", 768, 576, STATIC / "parlor/dark/game-nardy.webp")
    scene("214db232", 1024, 576, STATIC / "parlor/light/news-nardy.webp")
    scene("61f3a485", 1024, 576, STATIC / "parlor/dark/news-nardy.webp")
    scene("214db232", 480, 360, STATIC / "images/games/game-nardy-light.webp")
    scene("61f3a485", 480, 360, STATIC / "images/games/game-nardy-dark.webp")


if __name__ == "__main__":
    main()
