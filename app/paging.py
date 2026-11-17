"""Общая нарезка списков на страницы."""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def page_links(page: int, pages: int) -> list[int | None]:
    if pages <= 7:
        return list(range(1, pages + 1))
    wanted = {1, pages, page - 1, page, page + 1}
    ordered = sorted(number for number in wanted if 1 <= number <= pages)
    links: list[int | None] = []
    previous = 0
    for number in ordered:
        if previous and number - previous > 1:
            links.append(None)
        links.append(number)
        previous = number
    return links


def read_page(value: object) -> int:
    raw = str(value or "1")
    if not raw.isdigit() or len(raw) > 6:
        return 1
    return int(raw)


def page_count(total: int, size: int) -> int:
    if size < 1:
        return 1
    return max(1, (total + size - 1) // size)


def clamp_page(page: int, pages: int) -> int:
    return min(max(page, 1), max(pages, 1))


def window(items: list[T], page: int, size: int) -> dict[str, object]:
    pages = page_count(len(items), size)
    current = clamp_page(page, pages)
    start = (current - 1) * size
    return {
        "items": items[start : start + size],
        "page": current,
        "pages": pages,
        "links": page_links(current, pages),
        "total": len(items),
    }


def list_href(path: str, page: int) -> str:
    return path if page <= 1 else f"{path}?page={page}"
