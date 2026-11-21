"""Настройки гостиной и действия с гостями."""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.db.repositories import api_access, news, rate_limit, sessions, users
from app.errors import AppError
from app.names import shown
from app.news_html import sanitize_news, visible_text
from app.news_images import is_news_image, store_news_image
from app.paging import clamp_page, list_href, page_count, page_links, read_page
from app.site_policy import current, load_policy, normalize, remember, save_policy
from app.templating import render
from app.wallet import set_balance

router = APIRouter()

_DONE = {
    "saved": "Настройки сохранены.",
    "sessions": "Все сессии, кроме вашей, завершены.",
    "lockouts": "Блокировки входа сняты.",
    "messages": "Все сообщения удалены.",
    "stats": "Статистика игр очищена.",
}
_NEWS_DONE = {
    "created": "Новость опубликована.",
    "saved": "Новость сохранена.",
    "removed": "Новость убрана.",
}
_BODY_LIMIT = 20000
_NEWS_PAGE = 4
_COVERS = {"light-theme", "uno-evening", "welcome", "card-games", "go", "beta", "domino"}


def _admin(request: Request) -> Response | object:
    user = request.state.user
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not user.is_admin:
        raise AppError(404, "not_found", "Страница не найдена.")
    return user


async def _accounts(request: Request) -> list[object]:
    async with request.app.state.pool.acquire() as conn:
        rows = await users.list_users(conn)
    people: list[object] = []
    for row in rows:
        person = dict(row)
        person["full_name"] = shown(person.get("full_name"), "")
        people.append(person)
    return people


@router.get("/admin/site")
async def site_page(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    done = _DONE.get(request.query_params.get("done", ""), "")
    return render(request, "admin/site.html", await _site_context(request, message=done or None))


@router.post("/admin/site")
async def site_save(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    payload = {
        "registration_mode": form.get("registration_mode"),
        "registration_open": form.get("registration_open"),
        "maintenance": form.get("maintenance"),
        "username_min": form.get("username_min"),
        "username_max": form.get("username_max"),
        "password_min": form.get("password_min"),
        "password_needs_letter": form.get("password_needs_letter"),
        "password_needs_digit": form.get("password_needs_digit"),
        "session_hours": form.get("session_hours"),
        "login_failures": form.get("login_failures"),
        "login_window_minutes": form.get("login_window_minutes"),
        "starting_chips": form.get("starting_chips"),
        "referral_chips": form.get("referral_chips"),
        "notice": form.get("notice"),
        "games": form.getlist("game"),
    }
    try:
        policy = normalize(payload, local=request.app.state.settings.env == "local")
    except AppError as exc:
        return render(
            request,
            "admin/site.html",
            await _site_context(request, error=exc.message),
            status=exc.status,
        )
    async with request.app.state.pool.acquire() as conn:
        await load_policy(conn)
        await save_policy(conn, policy)
    remember(request.app, policy)
    return RedirectResponse("/admin/site?done=saved", status_code=303)


@router.post("/admin/site/sessions")
async def close_sessions(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    token_hash = getattr(request.state, "session_hash", None)
    if token_hash:
        async with request.app.state.pool.acquire() as conn:
            await sessions.revoke_other_sessions(conn, token_hash)
            await api_access.revoke_all(conn)
    return RedirectResponse("/admin/site?done=sessions", status_code=303)


@router.post("/admin/site/lockouts")
async def clear_lockouts(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    async with request.app.state.pool.acquire() as conn:
        await rate_limit.clear_login_failures(conn)
    await request.app.state.gate.clear_login_buckets()
    return RedirectResponse("/admin/site?done=lockouts", status_code=303)


@router.post("/admin/site/messages")
async def clear_messages(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    if form.get("confirm") != "yes":
        raise AppError(422, "confirm", "Подтвердите очистку сообщений.")
    async with request.app.state.pool.acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM messages")
        await conn.execute("DELETE FROM chat_reads")
    return RedirectResponse("/admin/site?done=messages", status_code=303)


@router.post("/admin/site/stats")
async def clear_game_stats(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    if form.get("confirm") != "yes":
        raise AppError(422, "confirm", "Подтвердите очистку статистики.")
    async with request.app.state.pool.acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM games")
    return RedirectResponse("/admin/site?done=stats", status_code=303)


@router.post("/admin/site/keys")
async def clear_keys(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    if form.get("confirm") != "yes":
        raise AppError(422, "confirm", "Подтвердите очистку ключей.")
    async with request.app.state.pool.acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM api_tokens")
        await conn.execute("DELETE FROM api_grants")
        await conn.execute("DELETE FROM sessions")
    return RedirectResponse("/login", status_code=303)


@router.get("/admin/news")
async def news_page(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    done = _NEWS_DONE.get(request.query_params.get("done", ""), "")
    return await _news_screen(request, message=done or None)


@router.get("/admin/news/new")
async def news_new(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    return await _news_form(request)


@router.post("/admin/news/images")
async def news_image_upload(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        return JSONResponse({"error": "Выберите картинку."}, status_code=422)
    payload = await upload.read()
    close = getattr(upload, "close", None)
    if close is not None:
        await close()
    try:
        name = store_news_image(
            Path(request.app.state.settings.news_image_dir),
            payload,
            limit=request.app.state.settings.news_image_bytes,
        )
    except ValueError:
        return JSONResponse({"error": "Подойдут JPEG, PNG и WebP до 4 МБ."}, status_code=422)
    return JSONResponse({"name": name, "src": f"/news-images/{name}"})


@router.post("/admin/news/preview")
async def news_preview(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    fields, _error = _news_fields(form, strict=False)
    if not fields["title"]:
        fields["title"] = "Без заголовка"
    if not fields["summary"]:
        fields["summary"] = ""
    if not fields["body"]:
        fields["body"] = "<p></p>"
    return render(
        request,
        "public/news.html",
        {"post": SimpleNamespace(**fields), "preview": True, "public_page": True},
    )


@router.get("/admin/news/{news_id}")
async def news_edit(request: Request, news_id: uuid.UUID) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    async with request.app.state.pool.acquire() as conn:
        post = await news.get_news(conn, news_id)
    if post is None:
        raise AppError(404, "not_found", "Новость не найдена.")
    return await _news_form(request, editing=post)


@router.post("/admin/news")
async def news_add(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    fields, error = _news_fields(form)
    if error:
        return await _news_form(request, error=error, draft=fields, status=422)
    async with request.app.state.pool.acquire() as conn:
        await news.add_news(conn, **fields)
    return RedirectResponse("/admin/news?done=created", status_code=303)


@router.post("/admin/news/{news_id}")
async def news_save(request: Request, news_id: uuid.UUID) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    fields, error = _news_fields(form)
    async with request.app.state.pool.acquire() as conn:
        post = await news.get_news(conn, news_id)
        if post is None:
            raise AppError(404, "not_found", "Новость не найдена.")
        if error:
            return await _news_form(request, error=error, editing=post, draft=fields, status=422)
        updated = await news.update_news(conn, news_id, **fields)
    if not updated:
        raise AppError(404, "not_found", "Новость не найдена.")
    return RedirectResponse("/admin/news?done=saved", status_code=303)


@router.post("/admin/news/{news_id}/delete")
async def news_delete(request: Request, news_id: uuid.UUID) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    async with request.app.state.pool.acquire() as conn:
        await news.delete_news(conn, news_id)
    return RedirectResponse("/admin/news?done=removed", status_code=303)


@router.post("/admin/users/{user_id}/active")
async def user_active(request: Request, user_id: uuid.UUID) -> Response:
    actor = _admin(request)
    if isinstance(actor, Response):
        return actor
    form = await request.form()
    active = str(form.get("active") or "") == "1"
    if user_id == actor.id and not active:
        return await _users_error(request, "Нельзя отключить свою учётную запись.")
    async with request.app.state.pool.acquire() as conn:
        account = await users.get_user(conn, user_id)
        if account is None:
            raise AppError(404, "not_found", "Гость не найден.")
        if account["role"] == "admin" and account["is_active"] and not active:
            others = await users.other_active_admins(conn, user_id)
            if others == 0:
                return await _users_error(request, "Нужен хотя бы один активный администратор.")
        await users.set_active(conn, user_id, active=active)
        if not active:
            await sessions.revoke_user_sessions(conn, user_id)
            await api_access.revoke_user(conn, user_id)
    return RedirectResponse(_users_back(form), status_code=303)


@router.post("/admin/users/{user_id}/role")
async def user_role(request: Request, user_id: uuid.UUID) -> Response:
    actor = _admin(request)
    if isinstance(actor, Response):
        return actor
    form = await request.form()
    if str(form.get("role") or "") != "admin":
        return await _users_error(request, "Гостя можно назначить администратором.")
    async with request.app.state.pool.acquire() as conn:
        account = await users.get_user(conn, user_id)
        if account is None:
            raise AppError(404, "not_found", "Гость не найден.")
        if account["role"] != "admin":
            await users.set_role(conn, user_id, "admin")
    return RedirectResponse(_users_back(form), status_code=303)


@router.post("/admin/users/{user_id}/chips")
async def user_chips(request: Request, user_id: uuid.UUID) -> Response:
    actor = _admin(request)
    if isinstance(actor, Response):
        return actor
    form = await request.form()
    try:
        amount = int(str(form.get("balance") or ""))
    except ValueError:
        return await _users_error(request, "Баланс фишек должен быть числом.")
    if not 0 <= amount <= 100_000:
        return await _users_error(request, "Баланс фишек: от 0 до 100 000.")
    async with request.app.state.pool.acquire() as conn:
        account = await users.get_user(conn, user_id)
        if account is None:
            raise AppError(404, "not_found", "Гость не найден.")
        await set_balance(conn, user_id, amount)
    request.app.state.gate.chips.pop(str(user_id), None)
    return RedirectResponse(_users_back(form), status_code=303)


def _users_back(form: object) -> str:
    getter = getattr(form, "get", lambda _key: None)
    page = read_page(getter("page"))
    query = " ".join(str(getter("q") or "").split())[:80]
    params: dict[str, str] = {}
    if query:
        params["q"] = query
    if page > 1:
        params["page"] = str(page)
    if not params:
        return "/admin/users"
    return "/admin/users?" + urlencode(params)


async def _users_error(request: Request, message: str) -> Response:
    from app.auth.routes import user_list_context

    context = user_list_context(await _accounts(request), message)
    return render(request, "admin/users.html", context, status=422)


def _news_fields(form: Any, *, strict: bool = True) -> tuple[dict[str, Any], str | None]:
    title = " ".join(str(form.get("title") or "").split())
    summary = " ".join(str(form.get("summary") or "").split())
    body = sanitize_news(str(form.get("body") or ""))
    kind = str(form.get("kind") or "announce")
    raw_day = str(form.get("published_on") or "")
    raw_cover = str(form.get("cover") or "").strip()
    raw_file = str(form.get("cover_file") or "").strip()
    published = date.today()
    day_error = False
    if raw_day:
        try:
            published = date.fromisoformat(raw_day)
        except ValueError:
            day_error = True
    if is_news_image(raw_file):
        cover = raw_file
    elif raw_cover in _COVERS or is_news_image(raw_cover):
        cover = raw_cover
    else:
        cover = None
    fields: dict[str, Any] = {
        "title": title,
        "summary": summary,
        "body": body,
        "kind": kind if kind in {"update", "event", "announce"} else "announce",
        "published_on": published,
        "cover": cover,
    }
    if not strict:
        return fields, None
    if kind not in {"update", "event", "announce"} or not 1 <= len(title) <= 120:
        return fields, "Проверьте заголовок и тип новости."
    if day_error:
        return fields, "Проверьте дату."
    if raw_file and not is_news_image(raw_file):
        return fields, "Своя обложка не подошла."
    if raw_cover and cover is None:
        return fields, "Выберите обложку из списка."
    if not 1 <= len(summary) <= 400 or not visible_text(body) or len(body) > _BODY_LIMIT:
        return fields, "Краткий текст до 400 символов, полный — до 20 000."
    return fields, None


async def _news_form(
    request: Request,
    *,
    error: str | None = None,
    editing: object | None = None,
    draft: dict[str, Any] | None = None,
    status: int = 200,
) -> Response:
    return render(
        request,
        "admin/news_form.html",
        {"error": error, "editing": editing, "draft": draft},
        status=status,
    )


async def _news_screen(request: Request, *, message: str | None = None) -> Response:
    asked = request.query_params.get("page")
    async with request.app.state.pool.acquire() as conn:
        total = await news.count_news(conn)
        pages = page_count(total, _NEWS_PAGE)
        current = clamp_page(read_page(asked), pages)
        posts = await news.list_news(conn, _NEWS_PAGE, (current - 1) * _NEWS_PAGE)
    if asked is not None and asked != str(current):
        target = list_href("/admin/news", current)
        if message:
            joiner = "&" if "?" in target else "?"
            done = request.query_params.get("done", "")
            if done:
                target = f"{target}{joiner}done={done}"
        return RedirectResponse(target, status_code=303)
    return render(
        request,
        "admin/news.html",
        {
            "posts": posts,
            "message": message,
            "pager_label": "Страницы новостей",
            "pager_page": current,
            "pager_pages": pages,
            "pager_links": page_links(current, pages),
            "pager_href": "/admin/news?page=__PAGE__",
        },
    )


async def _site_context(
    request: Request,
    *,
    message: str | None = None,
    error: str | None = None,
) -> dict[str, object]:
    async with request.app.state.pool.acquire() as conn:
        counts = await conn.fetchrow(
            """
            SELECT
                (SELECT count(*) FROM messages) AS messages,
                (SELECT count(*) FROM games) AS games,
                (SELECT count(*) FROM sessions WHERE revoked_at IS NULL AND expires_at > now()) AS sessions,
                (SELECT count(*) FROM api_tokens WHERE revoked_at IS NULL AND expires_at > now()) AS tokens
            """
        )
    return {
        "policy": await current(request),
        "message": message,
        "error": error,
        "local_rules": request.app.state.settings.env == "local",
        "sessions": int(counts["sessions"] or 0),
        "wipe_messages": int(counts["messages"] or 0),
        "wipe_games": int(counts["games"] or 0),
        "wipe_tokens": int(counts["tokens"] or 0),
    }
