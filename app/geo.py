"""Страна по адресу без внешнего сервиса. Частные сети так и называются."""

from __future__ import annotations

import ipaddress


def country_for(ip: str | None) -> str:
    if not ip:
        return "не определена"
    try:
        address = ipaddress.ip_address(ip.strip())
    except ValueError:
        return "не определена"
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        return "Локальная сеть"
    return "не определена"


def device_label(user_agent: str | None) -> str:
    text = (user_agent or "").lower()
    if "ipad" in text or "tablet" in text:
        return "планшет"
    if "mobile" in text or "iphone" in text or "android" in text:
        return "телефон"
    if not text:
        return "неизвестно"
    return "компьютер"
