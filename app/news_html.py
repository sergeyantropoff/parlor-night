"""Безопасная разметка новостей: небольшой набор тегов, без скриптов."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_ALLOWED = {"p", "br", "strong", "em", "h2", "h3", "ul", "ol", "li", "blockquote", "a", "img"}
_SKIP = {"script", "style", "iframe", "object", "embed", "noscript"}
_RENAME = {"b": "strong", "i": "em", "div": "p"}
_IMAGE = re.compile(r"^/news-images/[0-9a-f]{32}\.(jpg|png|webp)$")
_TAG = re.compile(r"<[^>]+>")


def _safe_image(src: str) -> bool:
    return _IMAGE.fullmatch(src) is not None


def _attr(attrs: list[tuple[str, str | None]], name: str) -> str:
    for key, value in attrs:
        if key.lower() == name and value:
            return value.strip()
    return ""


def _safe_href(href: str) -> bool:
    if any(char in href for char in "\n\r\t "):
        return False
    lowered = href.lower()
    if lowered.startswith(("https://", "http://", "mailto:")):
        return "javascript:" not in lowered and "data:" not in lowered
    return href.startswith("/") and not href.startswith("//") and not href.startswith("/\\")


class _Clean(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = _RENAME.get(tag.lower(), tag.lower())
        if name in _SKIP:
            self.skip += 1
            return
        if self.skip or name not in _ALLOWED:
            return
        if name == "br":
            self.parts.append("<br>")
            return
        if name == "img":
            src = _attr(attrs, "src")
            if not _safe_image(src):
                return
            alt = _attr(attrs, "alt").replace("\n", " ")[:180]
            self.parts.append(f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(alt, quote=True)}">')
            return
        extra = ""
        if name == "a":
            href = ""
            for key, value in attrs:
                if key.lower() == "href" and value:
                    href = value.strip()
            if not _safe_href(href):
                return
            extra = f' href="{html.escape(href, quote=True)}"'
        self.parts.append(f"<{name}{extra}>")
        self.stack.append(name)

    def handle_endtag(self, tag: str) -> None:
        name = _RENAME.get(tag.lower(), tag.lower())
        if name in _SKIP and self.skip:
            self.skip -= 1
            return
        if self.skip or not self.stack or self.stack[-1] != name:
            return
        self.stack.pop()
        self.parts.append(f"</{name}>")

    def handle_data(self, data: str) -> None:
        if self.skip or not data:
            return
        self.parts.append(html.escape(data))

    def close(self) -> None:
        super().close()
        while self.stack:
            self.parts.append(f"</{self.stack.pop()}>")


def visible_text(markup: str) -> str:
    plain = _TAG.sub("", markup)
    return html.unescape(plain).replace("\xa0", " ").strip()


def sanitize_news(raw: str) -> str:
    text = raw.replace("\r\n", "\n").strip()
    if not text:
        return ""
    if "<" not in text:
        blocks = []
        for block in text.split("\n\n"):
            lines = "<br>".join(html.escape(line) for line in block.split("\n") if line.strip())
            if lines:
                blocks.append(f"<p>{lines}</p>")
        return "".join(blocks)
    parser = _Clean()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts).strip()
