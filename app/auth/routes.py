"""Вход, выход и учётные записи."""

from __future__ import annotations

import uuid
from datetime import date
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import asyncpg
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.auth.attempts import authenticate
from app.auth.captcha import issue as issue_captcha
from app.auth.captcha import proof as captcha_proof
from app.auth.csrf import issue_login_csrf, issue_welcome, read_welcome
from app.auth.validation import clean_email, normalize_username, validate_password, validate_username
from app.db.repositories import api_access, sessions, users
from app.errors import AppError
from app.errors_page import error_response
from app.names import parse_full_name, shown, split_full_name
from app.site_policy import SitePolicy, current, referral_is_live, visitor_may_register
from app.templating import render
from app.wallet import born_from_parts

router = APIRouter()


def _cookie_flags(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "path": "/",
    }


def _entry_page(
    request: Request,
    template: str,
    error: str | None = None,
    status: int = 200,
    *,
    cookie_path: str,
    next_url: str = "",
    locked: bool = False,
    limited: bool = False,
    maintenance: bool = False,
    welcome: bool = False,
    name_error: str | None = None,
    family: str = "",
    given: str = "",
    patronymic: str = "",
    username: str = "",
    email: str = "",
) -> Response:
    token, signed = issue_login_csrf(request.app.state.settings.secret_key)
    response = render(
        request,
        template,
        {
            "error": error,
            "locked": locked,
            "limited": limited,
            "maintenance": maintenance,
            "welcome": welcome,
            "name_error": name_error,
            "family": family,
            "given": given,
            "patronymic": patronymic,
            "username": username,
            "email": email,
            "login_csrf": token,
            "year_now": date.today().year,
            "next": next_url,
        },
        status=status,
    )
    response.set_cookie(
        "bm_login_csrf",
        signed,
        max_age=3600,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
        path=cookie_path,
    )
    return response


def _login_page(
    request: Request,
    error: str | None = None,
    status: int = 200,
    next_url: str = "",
    locked: bool = False,
    limited: bool = False,
    maintenance: bool = False,
) -> Response:
    return _entry_page(
        request,
        "auth/login.html",
        error,
        status,
        cookie_path="/login",
        next_url=next_url,
        locked=locked,
        limited=limited,
        maintenance=maintenance,
    )


def _oauth_next(value: str) -> str:
    if len(value) > 1500 or any(char in value for char in "\r\n\\"):
        return ""
    if not value.startswith("/oauth/authorize?"):
        return ""
    return value


@router.get("/login")
async def login_form(request: Request) -> Response:
    if request.state.user is not None:
        return RedirectResponse("/", status_code=303)
    return _login_page(request, next_url=_oauth_next(request.query_params.get("next", "")))


@router.get("/login/captcha")
async def login_captcha(request: Request) -> JSONResponse:
    ip_address = request.state.client_ip
    if not await request.app.state.gate.allow(f"captcha:{ip_address}", 30, 60):
        raise AppError(429, "rate_limited", "Слишком много проверок. Подождите минуту.")
    return JSONResponse(issue_captcha(request.app.state.settings.secret_key))


@router.post("/login")
async def login_submit(request: Request) -> Response:
    form = await request.form()
    nxt = _oauth_next(str(form.get("next") or ""))
    try:
        await _require_human(request, str(form.get("captcha") or ""))
    except AppError as exc:
        if "application/json" in request.headers.get("accept", ""):
            raise
        return _login_page(request, exc.message, exc.status, next_url=nxt)
    username = normalize_username(str(form.get("username", "")))
    password = str(form.get("password", ""))
    try:
        record = await authenticate(request, username, password)
    except AppError as exc:
        if "application/json" in request.headers.get("accept", ""):
            raise
        locked = exc.code == "account_disabled"
        limited = exc.code == "rate_limited"
        quiet = locked or limited
        return _login_page(
            request,
            None if quiet else exc.message,
            200 if quiet else exc.status,
            next_url=nxt,
            locked=locked,
            limited=limited,
        )
    policy = await current(request)
    if policy.maintenance and record.role != "admin":
        if "application/json" in request.headers.get("accept", ""):
            raise AppError(503, "maintenance", "Сайт находится в режиме технического обслуживания. Вход невозможен.")
        return _login_page(request, status=200, next_url=nxt, maintenance=True)
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        old_hash = getattr(request.state, "session_hash", None)
        if old_hash:
            await sessions.revoke_token(conn, old_hash)
        token, _csrf = await sessions.create_session(
            conn,
            user_id=record.id,
            ttl_seconds=policy.session_ttl_seconds,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.state.client_ip,
        )
    response = RedirectResponse(nxt or "/", status_code=303)
    response.set_cookie("bm_session", token, max_age=policy.session_ttl_seconds, **_cookie_flags(request))
    return response


@router.post("/logout")
async def logout(request: Request) -> Response:
    pool = request.app.state.pool
    old_hash = getattr(request.state, "session_hash", None)
    if old_hash:
        async with pool.acquire() as conn:
            await sessions.revoke_token(conn, old_hash)
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("bm_session", path="/")
    return response


@router.get("/name")
async def name_form(request: Request) -> Response:
    user = request.state.user
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not user.ask_name or user.full_name:
        return RedirectResponse("/", status_code=303)
    family, given, patronymic = split_full_name(user.full_name)
    return render(
        request,
        "auth/name.html",
        {"error": None, "family": family, "given": given, "patronymic": patronymic},
    )


@router.post("/name")
async def name_save(request: Request) -> Response:
    user = request.state.user
    if user is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    try:
        full_name = parse_full_name(form.get("family"), form.get("given"), form.get("patronymic"))
    except AppError as exc:
        return render(
            request,
            "auth/name.html",
            {
                "error": exc.message,
                "family": str(form.get("family") or ""),
                "given": str(form.get("given") or ""),
                "patronymic": str(form.get("patronymic") or ""),
            },
            status=exc.status,
        )
    async with request.app.state.pool.acquire() as conn:
        await users.set_full_name(conn, user.id, full_name)
    return RedirectResponse("/", status_code=303)


@router.get("/register")
async def register_form(request: Request) -> Response:
    if request.state.user is not None:
        return RedirectResponse("/", status_code=303)
    policy = await current(request)
    if not await visitor_may_register(request, policy):
        return RedirectResponse("/login", status_code=303)
    return _entry_page(
        request,
        "auth/register.html",
        cookie_path="/register",
        welcome=_welcome_id(request) is not None,
    )


@router.get("/register/captcha")
async def register_captcha(request: Request) -> JSONResponse:
    policy = await current(request)
    await _guard_signup(request, policy)
    ip_address = request.state.client_ip
    if not await request.app.state.gate.allow(f"captcha:{ip_address}", 30, 60):
        raise AppError(429, "rate_limited", "Слишком много проверок. Подождите минуту.")
    return JSONResponse(issue_captcha(request.app.state.settings.secret_key))


@router.post("/register")
async def register(request: Request) -> Response:
    policy = await current(request)
    await _guard_signup(request, policy)
    form = await request.form()
    username = str(form.get("username") or "")
    email_raw = str(form.get("email") or "")
    password = str(form.get("password") or "")
    try:
        email = _clean_email(email_raw)
        if password != str(form.get("password_repeat") or ""):
            raise AppError(422, "bad_password", "Пароли не совпадают.")
        await _require_human(request, str(form.get("captcha") or ""))
        created_id = await _create_account(
            request,
            username=username,
            password=password,
            role="user",
            referral=True,
            ask_name=True,
            email=email,
        )
    except AppError as exc:
        if "application/json" in request.headers.get("accept", ""):
            raise
        return _entry_page(
            request,
            "auth/register.html",
            exc.message,
            exc.status,
            cookie_path="/register",
            username=username,
            email=email_raw,
        )
    return await _open_session(request, created_id)


@router.post("/intake")
async def intake_save(request: Request) -> Response:
    user = request.state.user
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not user.needs_intake:
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    family = str(form.get("family") or "")
    given = str(form.get("given") or "")
    patronymic = str(form.get("patronymic") or "")
    day = str(form.get("born_day") or "")
    month = str(form.get("born_month") or "")
    year = str(form.get("born_year") or "")
    try:
        if not given.strip():
            raise AppError(422, "bad_name", "Укажите имя.")
        full_name = parse_full_name(family, given, patronymic)
        born = _required_born(form)
    except AppError as exc:
        return render(
            request,
            "auth/intake.html",
            {
                "intake_error": exc.message,
                "intake_family": family,
                "intake_given": given,
                "intake_patronymic": patronymic,
                "intake_day": day,
                "intake_month": month,
                "intake_year": year,
            },
            status=exc.status,
        )
    async with request.app.state.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE users SET born_on = $2, updated_at = now() WHERE id = $1",
                user.id,
                born,
            )
            await users.set_full_name(conn, user.id, full_name)
    return RedirectResponse("/", status_code=303)


@router.post("/register/welcome")
async def register_welcome(request: Request) -> Response:
    if request.state.user is not None:
        return RedirectResponse("/", status_code=303)
    user_id = _welcome_id(request)
    if user_id is None:
        return RedirectResponse("/register", status_code=303)
    form = await request.form()
    family = str(form.get("family") or "")
    given = str(form.get("given") or "")
    patronymic = str(form.get("patronymic") or "")
    try:
        full_name = parse_full_name(family, given, patronymic)
    except AppError as exc:
        return _entry_page(
            request,
            "auth/register.html",
            cookie_path="/register",
            welcome=True,
            name_error=exc.message,
            family=family,
            given=given,
            patronymic=patronymic,
        )
    pool = request.app.state.pool
    policy = await current(request)
    async with pool.acquire() as conn:
        account = await conn.fetchrow(
            "SELECT id, is_active FROM users WHERE id = $1",
            uuid.UUID(user_id),
        )
        if account is None or not account["is_active"]:
            response = RedirectResponse("/register", status_code=303)
            _clear_welcome(response)
            return response
        if full_name:
            await users.set_full_name(conn, account["id"], full_name)
        else:
            await conn.execute(
                "UPDATE users SET ask_name = FALSE, updated_at = now() WHERE id = $1",
                account["id"],
            )
        old_hash = getattr(request.state, "session_hash", None)
        if old_hash:
            await sessions.revoke_token(conn, old_hash)
        token, _csrf = await sessions.create_session(
            conn,
            user_id=account["id"],
            ttl_seconds=policy.session_ttl_seconds,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.state.client_ip,
        )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("bm_session", token, max_age=policy.session_ttl_seconds, **_cookie_flags(request))
    _clear_welcome(response)
    return response


def user_list_context(
    rows: list[object],
    error: str | None,
    *,
    create_error: str | None = None,
    create_username: str = "",
    create_role: str = "user",
    create_family: str = "",
    create_given: str = "",
    create_patronymic: str = "",
    create_day: str = "",
    create_month: str = "",
    create_year: str = "",
) -> dict[str, object]:
    people: list[object] = []
    for row in rows:
        person = dict(row)
        person["name"] = shown(person.get("full_name"), person.get("username"))
        people.append(person)
    return {
        "accounts": people,
        "error": error,
        "year_now": date.today().year,
        "create_error": create_error,
        "create_username": create_username,
        "create_role": "admin" if create_role == "admin" else "user",
        "create_family": create_family,
        "create_given": create_given,
        "create_patronymic": create_patronymic,
        "create_day": create_day,
        "create_month": create_month,
        "create_year": create_year,
    }


@router.get("/admin/users")
async def admin_users(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    async with request.app.state.pool.acquire() as conn:
        rows = await users.list_users(conn)
    return render(request, "admin/users.html", user_list_context(list(rows), None))


@router.post("/admin/users")
async def admin_create(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    draft = {
        "create_username": str(form.get("username") or ""),
        "create_role": str(form.get("role") or "user"),
        "create_family": str(form.get("family") or ""),
        "create_given": str(form.get("given") or ""),
        "create_patronymic": str(form.get("patronymic") or ""),
        "create_day": str(form.get("born_day") or ""),
        "create_month": str(form.get("born_month") or ""),
        "create_year": str(form.get("born_year") or ""),
    }
    try:
        full_name = parse_full_name(form.get("family"), form.get("given"), form.get("patronymic"))
        born = _required_born(form)
        await _create_account(
            request,
            username=draft["create_username"],
            password=str(form.get("password", "")),
            role=draft["create_role"],
            born_on=born,
            full_name=full_name,
        )
    except AppError as exc:
        async with request.app.state.pool.acquire() as conn:
            rows = await users.list_users(conn)
        context = user_list_context(list(rows), None, create_error=exc.message, **draft)
        return render(request, "admin/users.html", context, status=exc.status)
    return RedirectResponse("/admin/users?tail=1", status_code=303)


def _admin(request: Request) -> Response | object:
    user = request.state.user
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not user.is_admin:
        raise AppError(404, "not_found", "Страница не найдена.")
    return user


async def _signup_code(request: Request, policy: SitePolicy, referral: str = "") -> str:
    code = referral.strip().lower()
    if not code:
        code = str(request.cookies.get("pn_ref") or request.query_params.get("ref") or "")
    if policy.registration_mode == "open":
        return code
    if policy.registration_mode == "referral" and await referral_is_live(request, code):
        return code
    if policy.registration_mode == "referral":
        raise AppError(403, "referral_required", "Регистрация открыта только по ссылке друга.")
    raise AppError(403, "registration_disabled", "Самостоятельная регистрация отключена.")


async def _guard_signup(request: Request, policy: SitePolicy) -> None:
    await _signup_code(request, policy)


async def _require_human(request: Request, payload: str) -> None:
    signature = captcha_proof(request.app.state.settings.secret_key, payload)
    if signature is None or not await request.app.state.gate.once(f"captcha:{signature}", 600):
        raise AppError(422, "captcha", "Подтвердите, что вы не робот.")


def _clean_email(value: str) -> str:
    try:
        return clean_email(value)
    except ValueError as exc:
        raise AppError(422, "bad_email", str(exc)) from exc


def _required_born(form) -> date:
    try:
        born = born_from_parts(
            str(form.get("born_day") or ""),
            str(form.get("born_month") or ""),
            str(form.get("born_year") or ""),
        )
    except ValueError as exc:
        raise AppError(422, "bad_date", str(exc)) from exc
    if born is None:
        raise AppError(422, "bad_date", "Укажите дату рождения.")
    return born


def _welcome_id(request: Request) -> str | None:
    return read_welcome(request.app.state.settings.secret_key, request.cookies.get("pn_welcome", ""))


def _set_welcome(request: Request, response: Response, user_id: uuid.UUID) -> None:
    response.set_cookie(
        "pn_welcome",
        issue_welcome(request.app.state.settings.secret_key, str(user_id)),
        max_age=900,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
        path="/register",
    )


def _clear_welcome(response: Response) -> None:
    response.delete_cookie("pn_welcome", path="/register")


async def _create_account(
    request: Request,
    *,
    username: str,
    password: str,
    role: str,
    referral: bool = False,
    born_on: date | None = None,
    ask_name: bool = False,
    full_name: str = "",
    referral_code: str | None = None,
    email: str | None = None,
) -> uuid.UUID:
    if role not in {"admin", "user"}:
        raise AppError(422, "bad_role", "Неизвестная роль.")
    policy = await current(request)
    normalized = normalize_username(username)
    username_error = validate_username(
        normalized,
        minimum=policy.username_min,
        maximum=policy.username_max,
    )
    password_error = validate_password(
        password,
        minimum=policy.password_min,
        letter=policy.password_needs_letter,
        digit=policy.password_needs_digit,
    )
    if username_error or password_error:
        raise AppError(422, "bad_account", username_error or password_error or "Проверьте данные.")
    password_hash = request.app.state.passwords.hash_password(password)
    try:
        async with request.app.state.pool.acquire() as conn:
            created = await users.create_user(
                conn,
                username=normalized,
                password_hash=password_hash,
                role=role,
                starting_chips=policy.starting_chips,
                born_on=born_on,
                ask_name=ask_name,
                email=email,
            )
            if full_name:
                await users.set_full_name(conn, created.id, full_name)
            if referral:
                code = request.cookies.get("pn_ref", "") if referral_code is None else referral_code
                await users.attach_referral(conn, created.id, code, policy.referral_chips)
            return created.id
    except asyncpg.UniqueViolationError as exc:
        constraint = str(getattr(exc, "constraint_name", "") or "")
        if "email" in constraint:
            raise AppError(409, "email_taken", "Эта почта уже указана у другого игрока.") from exc
        raise AppError(409, "username_taken", "Такой логин уже занят.") from exc


async def _open_session(request: Request, user_id: uuid.UUID) -> Response:
    policy = await current(request)
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        account = await conn.fetchrow("SELECT id, is_active FROM users WHERE id = $1", user_id)
        if account is None or not account["is_active"]:
            return RedirectResponse("/register", status_code=303)
        old_hash = getattr(request.state, "session_hash", None)
        if old_hash:
            await sessions.revoke_token(conn, old_hash)
        token, _csrf = await sessions.create_session(
            conn,
            user_id=account["id"],
            ttl_seconds=policy.session_ttl_seconds,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.state.client_ip,
        )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("bm_session", token, max_age=policy.session_ttl_seconds, **_cookie_flags(request))
    return response


def _callback(uri: str, **extra: str) -> str:
    parts = urlsplit(uri)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(extra)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


async def _oauth_client(request: Request, client_id: str, redirect_uri: str):
    async with request.app.state.pool.acquire() as conn:
        client = await api_access.get_client(conn, client_id.strip().lower())
    if client is None or not client.is_active or client.kind != "third_party":
        return None
    if redirect_uri not in client.redirect_uris:
        return None
    return client


@router.get("/oauth/authorize")
async def oauth_authorize(request: Request) -> Response:
    client_id = request.query_params.get("client_id", "")
    redirect_uri = request.query_params.get("redirect_uri", "")
    state = request.query_params.get("state", "")[:256]
    client = await _oauth_client(request, client_id, redirect_uri)
    if client is None:
        return error_response(request, 400, note="Приложение не может запросить вход.")
    if request.state.user is None:
        nxt = "/oauth/authorize?" + urlencode(
            {"client_id": client.id, "redirect_uri": redirect_uri, "state": state}
        )
        return RedirectResponse("/login?next=" + quote(nxt, safe=""), status_code=303)
    return render(
        request,
        "auth/authorize.html",
        {"client_name": client.name, "client_id": client.id, "redirect_uri": redirect_uri, "state": state},
    )


@router.post("/oauth/authorize")
async def oauth_decide(request: Request) -> Response:
    user = request.state.user
    if user is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    client_id = str(form.get("client_id") or "")
    redirect_uri = str(form.get("redirect_uri") or "")
    state = str(form.get("state") or "")[:256]
    client = await _oauth_client(request, client_id, redirect_uri)
    if client is None:
        return error_response(request, 400, note="Приложение не может запросить вход.")
    if str(form.get("decision") or "") != "allow":
        return RedirectResponse(_callback(redirect_uri, error="access_denied", state=state), status_code=303)
    async with request.app.state.pool.acquire() as conn:
        code = await api_access.issue_code(
            conn,
            client_id=client.id,
            user_id=user.id,
            redirect_uri=redirect_uri,
        )
    return RedirectResponse(_callback(redirect_uri, code=code, state=state), status_code=303)
