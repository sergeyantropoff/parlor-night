"""Собирает картинки домино и анонс нард из присланных кадров и ровных костей."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path("/Users/inecs/.cursor/projects/Users-inecs-Parlor-Night/assets")
STATIC = ROOT / "app" / "static"


def find(token: str) -> Path:
    matches = list(ASSETS.glob(f"*{token}*"))
    if len(matches) != 1:
        raise SystemExit(f"{token}: {len(matches)}")
    return matches[0]


def cover(image: Image.Image, width: int, height: int) -> Image.Image:
    image = image.convert("RGB")
    scale = max(width / image.width, height / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def fit_width(image: Image.Image, width: int) -> Image.Image:
    image = image.convert("RGB")
    if image.width <= width:
        return image
    height = max(1, round(image.height * width / image.width))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def save(image: Image.Image, path: Path, *, quality: int = 82) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "WEBP", quality=quality, method=6)


def photo(token: str, path: Path, width: int, height: int | None = None) -> None:
    image = Image.open(find(token))
    framed = cover(image, width, height) if height else fit_width(image, width)
    save(framed, path)


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: tuple[int, ...]) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def bone(hi: int, lo: int) -> Image.Image:
    width, height = 280, 560
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rounded(draw, (0, 0, width - 1, height - 1), 36, (243, 234, 215, 255))
    rounded(draw, (10, 10, width - 11, height - 11), 28, (236, 224, 200, 255))
    draw.rectangle((36, height // 2 - 3, width - 36, height // 2 + 3), fill=(176, 141, 79, 255))
    _pips(draw, hi, 0)
    _pips(draw, lo, height // 2)
    return image


def _pips(draw: ImageDraw.ImageDraw, count: int, top: int) -> None:
    if count <= 0:
        return
    cols = (78, 140, 202)
    rows = (top + 58, top + 140, top + 222)
    spots = {
        1: [(1, 1)],
        2: [(0, 0), (2, 2)],
        3: [(0, 0), (1, 1), (2, 2)],
        4: [(0, 0), (2, 0), (0, 2), (2, 2)],
        5: [(0, 0), (2, 0), (1, 1), (0, 2), (2, 2)],
        6: [(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2)],
    }
    for col, row in spots[count]:
        x, y = cols[col], rows[row]
        draw.ellipse((x - 24, y - 24, x + 24, y + 24), fill=(28, 24, 20, 255))


def tile_back() -> Image.Image:
    width, height = 280, 560
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rounded(draw, (0, 0, width - 1, height - 1), 36, (236, 224, 200, 255))
    rounded(draw, (16, 16, width - 17, height - 17), 28, (176, 141, 79, 255))
    rounded(draw, (24, 24, width - 25, height - 25), 24, (243, 234, 215, 255))
    for x, y in ((48, 48), (width - 48, 48), (48, height - 48), (width - 48, height - 48)):
        draw.line((x - 10, y, x + 10, y), fill=(176, 141, 79, 255), width=3)
        draw.line((x, y - 10, x, y + 10), fill=(176, 141, 79, 255), width=3)
    glyph = (112, 246, 168, 314)
    draw.rounded_rectangle(glyph, radius=8, outline=(176, 141, 79, 255), width=3)
    draw.line((112, 280, 168, 280), fill=(176, 141, 79, 255), width=3)
    draw.ellipse((132, 258, 148, 274), fill=(176, 141, 79, 255))
    draw.ellipse((132, 286, 148, 302), fill=(176, 141, 79, 255))
    return image


def mark(fill: tuple[int, int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((78, 28, 178, 228), radius=22, fill=fill)
    return image


def main() -> None:
    photo("6dbccddc", STATIC / "parlor/light/game-domino.webp", 1448, 1086)
    photo("870c6781", STATIC / "parlor/dark/game-domino.webp", 1448, 1086)
    photo("9ae57475", STATIC / "parlor/light/news-domino.webp", 1672, 941)
    photo("b2d9e9b6", STATIC / "parlor/dark/news-domino.webp", 1672, 941)
    photo("3bbbf4d8", STATIC / "images/tables/table-domino.webp", 1600)
    photo("def5b933", ROOT / "docs/images/games/domino.webp", 1600)
    photo("aa376922", STATIC / "parlor-ongoing/images/ongoing-domino-480.webp", 480, 320)
    photo("3f608c3a", STATIC / "parlor/light/soon-backgammon.webp", 1448, 1086)
    photo("3f608c3a", STATIC / "parlor/dark/soon-backgammon.webp", 1448, 1086)
    photo("3f608c3a", ROOT / "docs/images/games/backgammon-soon.webp", 1448, 1086)
    tiles = STATIC / "images/dominoes"
    for hi in range(6, -1, -1):
        for lo in range(hi, -1, -1):
            save(bone(hi, lo), tiles / f"{hi}-{lo}.webp", quality=88)
    save(tile_back(), tiles / "back.webp", quality=88)
    save(mark((58, 42, 34, 255)), STATIC / "images/games/game-domino-light.webp", quality=88)
    save(mark((244, 239, 230, 255)), STATIC / "images/games/game-domino-dark.webp", quality=88)
    print("domino assets ready")


if __name__ == "__main__":
    main()
