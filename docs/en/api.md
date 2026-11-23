# Parlor Night API

The parlor guide is [in English](guide.md) and [на русском](../ru/guide.md).
The Russian API text is [mobile-api.md](../mobile-api.md).

The base address is the same as the website. Every method below starts with `/api/v1`, except third-party confirmation (`/oauth/authorize`), pictures, and the table socket.

The website still signs in with the `bm_session` cookie. An app does not use that cookie: it receives a token pair and then sends the short token in a header.

```http
Authorization: Bearer <access_token>
Content-Type: application/json
Accept: application/json
```

JSON bodies are UTF-8. Dates and times in responses are ISO 8601. Identifiers are UUID strings. Sentences inside responses (`message`, titles, notes) are Russian, the same sentences the website shows.

## Errors

A failed response looks like this:

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Нужно войти в систему.",
    "details": {}
  }
}
```

| HTTP | `code` | When |
| --- | --- | --- |
| 401 | `unauthorized` | No token, expired token, or a wrong password |
| 401 | `invalid_client` | Unknown `client_id` |
| 401 | `invalid_grant` | The third-party confirmation code was already used or is wrong |
| 403 | `forbidden` | A third-party app tries to sign in or register with a password |
| 403 | `registration_disabled` | Self-service registration is off |
| 403 | `referral_required` | Registration is only open through a live friend link |
| 409 | `username_taken` | That username is taken |
| 422 | `captcha` | The human check was not solved or was already used |
| 403 | `csrf` | A website-cookie request without the protection token. A Bearer app does not get this code |
| 409 | `name_required` | The account still has no name |
| 409 | `stale_position` | The position already changed; read the table again |
| 409 | `wrong_turn` | It is the other side's turn |
| 422 | `invalid_body` | The body did not match the schema. `details.fields` names the fields |
| 403 | `adult_only` | Poker, blackjack, or Preferans, and the person is under 18 or has no birth date |
| 403 | `game_closed` | The game is switched off in the parlor settings |
| 403 | `table_closed` | A closed table cannot be sat at or watched without the code |
| 403 | `not_player` | A watcher tries to move, resign, or offer a rematch |
| 403 | `stop_forbidden` | Only the creator can stop the game |
| 403 | `hint_forbidden` | The hint is available only to an administrator |
| 404 | `not_found` | No such game, player, news item, or request |
| 409 | `already_friends` | A friend request already exists |
| 409 | `game_full` | The table has no free seat |
| 409 | `finished` | The game is already over |
| 409 | `not_started` | The action is available only in a started game |
| 409 | `no_rematch` | A rematch cannot be offered or declined right now |
| 409 | `undo_rejected` | This move cannot be undone |
| 409 | `engine_rejected` | The computer cannot move right now |
| 409 | `table_done` | Only one poker seat still has chips |
| 422 | `illegal_move` | The move breaks the rules |
| 422 | `bad_date` | The birth date is incomplete or invalid |
| 422 | `bad_password` | The new password fails the rules or does not match the repeat |
| 422 | `bad_game` | Unknown or closed game, or the table is no longer waiting |
| 422 | `bad_message` | The text is empty or longer than 1000 characters |
| 422 | `bad_code` | A table code is exactly 8 characters |
| 422 | `bad_import` | The starting position does not fit the chosen game |
| 422 | `bad_mode` | This game does not accept that mode |
| 422 | `bad_board` | A Go board is 9, 13, or 19 |
| 422 | `bad_seats` | The card-table seat count does not match the rules |
| 422 | `bad_variant` | Durak needs podkidnoy or perevodnoy |
| 422 | `bad_image` | The portrait is not JPEG, PNG, or WebP, or it is over 10 MB |
| 422 | `bad_amount` | The chip amount was not given |
| 429 | `rate_limited` | Too many requests. A `Retry-After` header is set |
| 503 | `maintenance` | The parlor is closed |

The shared limit is 240 requests in 10 seconds from one address. Sign-in is also limited by failed attempts, the same way as the website.

Until the account has a name, every method except `/api/v1/auth/…` and `/api/v1/account…` answers `409 name_required`.

## Method index

Every JSON method of the project is listed here. The sections below give the bodies and the fields. The prefix is `/api/v1` unless the path starts with `/`.

| Method | Purpose |
| --- | --- |
| `GET /auth/register` | Whether registration is open, and the username and password rules |
| `GET /auth/captcha` | The human-check challenge |
| `POST /auth/register` | Create an account and sign in at once |
| `POST /auth/login` | Sign-in for a first-party app |
| `POST /auth/refresh` | A new token pair |
| `POST /auth/logout` | Revoke the chain |
| `POST /auth/token` | Exchange a third-party confirmation code |
| `GET /auth/me` | Who is signed in |
| `GET /catalog` | Games this person may start |
| `GET /home` | Home: continue a game, and recent tables |
| `GET /account` | Name, birth date, settings, invitation link |
| `PATCH /account` | Name and birth date |
| `PUT /account/settings` | Theme, board, default game, analysis |
| `POST /account/password` | Change the password |
| `POST /account/avatar` | Upload a portrait |
| `DELETE /account/avatar` | Remove the portrait |
| `GET /account/chips` | Chip ledger |
| `GET /friends` | Friends and requests |
| `POST /friends` | A request by username |
| `POST /friends/{id}/accept` | Accept a request |
| `POST /friends/{id}/decline` | Decline a request or remove a friendship |
| `POST /friends/{id}/challenge` | Create a table and send the friend the code |
| `GET /lobby` | Who is seeking a table, and who is online |
| `POST /lobby/seek` | Seek a table |
| `POST /lobby/cancel` | Withdraw your seek |
| `POST /lobby/accept/{user_id}` | Sit with the person who is seeking |
| `GET /chats` | Chat list |
| `GET /chats/{username}` | A thread, marked read |
| `POST /chats/{username}` | A line in a thread |
| `GET /notices` | Fresh messages, requests, and counts |
| `GET /live` | Tables that exist |
| `POST /live/{id}/watch` | Watch an open table |
| `POST /live/{id}/sit` | Sit at an open table |
| `GET /news`, `GET /news/{id}` | News, no sign-in |
| `GET /players` | Username search for an invitation |
| `GET /players/{username}` | Profile and statistics |
| `POST /players/{username}/friend` | The same request as `POST /friends` |
| `POST /players/{username}/chips` | Grant chips. Administrator only |
| `POST /games` | Create a game |
| `POST /games/join` | Sit by code |
| `POST /games/watch` | Watch by code |
| `GET /games/{id}` | Table state |
| `GET /games/{id}/legal-moves` | Moves the server accepts now |
| `GET /games/{id}/history` | Move list |
| `POST /games/{id}/moves` | A move in chess, checkers, and cards |
| `POST /games/{id}/go` | A Go command |
| `POST /games/{id}/undo` | Undo a move |
| `POST /games/{id}/resign` | Resign |
| `POST /games/{id}/step-aside` | In Durak, step aside to watch the computers or finish the table at once |
| `POST /games/{id}/stop` | Stop the game |
| `POST /games/{id}/engine-move` | Ask for the computer's move |
| `POST /games/{id}/hint` | Analysis. Administrator only |
| `POST /games/{id}/orientation` | Flip the board |
| `POST /games/{id}/save` | Mark the game fresh |
| `GET /games/{id}/export` | Download the record |
| `POST /games/{id}/rematch` | Rematch |
| `POST /games/{id}/rematch/decline` | Decline a rematch |
| `POST /games/{id}/invite` | Invite a player into a private chat |
| `GET /games/{id}/chat` | Table chat |
| `POST /games/{id}/chat` | A line at the table |
| `POST /settings` | The same body as `PUT /account/settings` |
| `POST /settings/theme` | Theme only |
| `GET /avatars/{file}` | A portrait. No sign-in |
| `GET /news-images/{file}` | A news cover. No sign-in |
| `GET /ws/tables/{id}` | Video and voice socket |
| `GET /oauth/authorize`, `POST /oauth/authorize` | Third-party confirmation on the website |

`/rules`, `/privacy`, `/contact`, and the whole admin area (overview, news editor, guest list, parlor settings) stay HTML. On the website a letter to an administrator is the `/contact` form. There is no JSON method for it. There is no separate JSON method to unfriend: `POST /friends/{id}/decline` removes an accepted friendship. The app stores the birth date at registration. Only an administrator can change it through `PATCH /account`. On the website the date is changed on the profile.

## Tokens

First-party apps use a public `client_id`:

- `parlor-ios`
- `parlor-android`

This is not a secret. The user's password is not built into the app binary. Registration from the app is available when the parlor allows it.

Sign-in, refresh, and code exchange return the same shape:

```json
{
  "token_type": "Bearer",
  "access_token": "...",
  "expires_in": 900,
  "refresh_token": "...",
  "refresh_expires_in": 1209600,
  "user": {
    "id": "uuid",
    "username": "mobile",
    "name": "Иванов Иван",
    "full_name": "Иванов Иван Иванович",
    "role": "user",
    "avatar": "",
    "ask_name": false,
    "chips": 500
  }
}
```

`expires_in` is the access-token lifetime in seconds, always 900 (15 minutes). `refresh_expires_in` is the refresh-token lifetime. It matches the website session. The default is 14 days.

Keep the access token in memory and send it in `Authorization`. Keep the refresh token in the iOS Keychain or the Android Keystore. Do not send the refresh token on ordinary requests. Do not write tokens into logs.

When the access token ends, call refresh once and retry the original request. If several requests get 401 at the same time, refresh once and let the others wait for the same new pair. The old refresh token dies after the exchange. Sending it again revokes the whole chain, including the new access token that was just issued: the token was stolen. The app then deletes both tokens and shows sign-in.

Refresh and logout do not need an `Authorization` header. If the access token is already expired, a header with that old token gets in the way: the server answers 401 before it reads the body. Those two methods only need JSON with `refresh_token`.

Changing the password in the app keeps the current chain and revokes the other sign-ins, including the website. Changing the password on the website revokes every app token.

### First-party sign-in

`POST /api/v1/auth/login`

```json
{ "username": "mobile", "password": "secret-pass-1", "client_id": "parlor-ios" }
```

The username is lowercased. A wrong password is 401 with the same text as the website. A third-party `client_id` with a password gets 403: that app is confirmed on the website and never sees the password.

### Registration

`GET /api/v1/auth/register` says whether an account can be created now. The `ref` parameter is an invitation code when the parlor is open only by link.

```json
{
  "mode": "open",
  "open": true,
  "referral_required": false,
  "username_min": 3,
  "username_max": 32,
  "password_min": 8,
  "password_letter": true,
  "password_digit": true,
  "password_rules": "Не меньше 8 символов, хотя бы одна буква, хотя бы одна цифра, не длиннее 128 символов.",
  "client_ids": ["parlor-ios", "parlor-android"]
}
```

`mode`: `open` means anyone, `referral` means only a live invitation code, `closed` means no. `open: false` means this `ref` cannot register. `closed`, and a referral link without a live code, still answer 200, so the app can show the reason.

Before creating an account the app solves the same check as the website.

`GET /api/v1/auth/captcha`. In referral mode add `?ref=code`. The response:

```json
{
  "algorithm": "SHA-256",
  "challenge": "hex",
  "maxnumber": 100000,
  "salt": "…?expires=…",
  "signature": "hex"
}
```

Find a number from 0 to `maxnumber` whose SHA-256 of the string `salt + number` equals `challenge`. Then build JSON and encode it as base64:

```json
{
  "algorithm": "SHA-256",
  "challenge": "…",
  "number": 12345,
  "salt": "…",
  "signature": "…"
}
```

That string is the `captcha` field. A challenge lives about 10 minutes and is accepted once. More than 30 challenges a minute from one address are refused.

`POST /api/v1/auth/register` creates the guest and signs in. Status `201` is the same token pair as sign-in. The name is not set yet, so `user.ask_name` is `true`: the next call is `PATCH /api/v1/account`.

```json
{
  "username": "newbie",
  "password": "secret-pass-1",
  "client_id": "parlor-ios",
  "born_day": "16",
  "born_month": "11",
  "born_year": "1990",
  "captcha": "base64 of the solved check",
  "referral": ""
}
```

The birth date is required in this request: it unlocks poker, blackjack, and Preferans. The website does not ask for it here. It asks in the window after the first sign-in, together with the given name. Family name and patronymic are optional. The website also asks for an email at registration. This request does not accept an email. `referral` is the code from `/?ref=`. Referral mode without a live code is `403 referral_required`. Closed registration is `403 registration_disabled`. A taken username is `409 username_taken`. A third-party `client_id` is `403`. That app does not create accounts.

When `user.ask_name` is `true`, save the name first. Until it exists, every other method, except Account and `/auth`, answers `409 name_required`.

### Who is signed in

`GET /api/v1/auth/me`

```json
{ "user": { "...": "the same card as sign-in" }, "client_id": "parlor-ios" }
```

### Refresh

`POST /api/v1/auth/refresh`

```json
{ "refresh_token": "..." }
```

The response is a new pair. The previous access token stops working too.

### Sign-out

`POST /api/v1/auth/logout`

```json
{ "refresh_token": "..." }
```

The response is `{ "logged_out": true }`. Signing out again with the same token also succeeds. The app then deletes both tokens.

### A third-party app

A third-party app never receives the password. The person confirms sign-in on the website, and the app exchanges a one-time code for the same token pair.

1. Register the client as a row in `api_clients`: `kind = third_party`, `secret_hash` is the SHA-256 of the secret in hex, `redirect_uris` are the exact return addresses, for example `https://app.example/callback`.
2. Open in a browser:

```text
GET /oauth/authorize?client_id=sample-app&redirect_uri=https%3A%2F%2Fapp.example%2Fcallback&state=xyz
```

`redirect_uri` must match one stored address. `state` is an arbitrary string from the app; the server returns it unchanged. If the person is not signed in, the site opens sign-in and returns them to the confirmation.

3. After consent the browser goes to:

```text
https://app.example/callback?code=...&state=xyz
```

A refusal is `?error=access_denied&state=xyz`. The code lives 60 seconds and is accepted once.

4. `POST /api/v1/auth/token`

```json
{
  "grant_type": "authorization_code",
  "code": "...",
  "client_id": "sample-app",
  "client_secret": "the client secret",
  "redirect_uri": "https://app.example/callback"
}
```

After that, the same access token, refresh token, sign-out, and the same rights this person has on the website.

## Account

These methods work before a name is set.

`GET /api/v1/account` — the card, the name parts, the birth date, settings, and the invitation link.

```json
{
  "user": {},
  "family": "Иванов",
  "given": "Иван",
  "patronymic": "Иванович",
  "birth": {
    "born": "1990-11-16",
    "age_years": 35,
    "adult": true,
    "born_label": "16 ноября 1990",
    "age_label": "35 лет"
  },
  "settings": {
    "theme": "system",
    "board_style": "classic",
    "default_game": "chess",
    "default_side": "white",
    "analysis_preferences": {
      "chess_depth": 12,
      "chess_time_ms": 1000,
      "chess_multipv": 3,
      "checkers_level": 3,
      "checkers_time_ms": 1000,
      "variety": false
    }
  },
  "referral_link": "http://127.0.0.1:8010/?ref=ab12cd34"
}
```

`theme`: `system`, `light`, `dark`. `board_style`: `classic`, `contrast`. `default_side`: `white`, `black`.

`PATCH /api/v1/account` changes only the fields that were sent.

```json
{
  "family": "Иванов",
  "given": "Иван",
  "patronymic": "Иванович",
  "born_day": "16",
  "born_month": "11",
  "born_year": "1990",
  "confirm": true
}
```

A regular guest who tries to change the date receives `403 forbidden`: an administrator changes it. An administrator sends the new date with `"confirm": true`, or the response is 422. Empty day, month, and year do not erase the date. The response is a fresh account.

`PUT /api/v1/account/settings`

```json
{
  "theme": "dark",
  "board_style": "classic",
  "default_game": "chess",
  "default_side": "white",
  "chess_depth": 12,
  "chess_time_ms": 1000,
  "chess_multipv": 3,
  "checkers_level": 3,
  "checkers_time_ms": 1000
}
```

`default_game`: `chess`, `checkers`, `go`, `domino`, `nardy`, `uno`, `poker`, `durak`, `blackjack`, `preferans`. Poker, blackjack, and Preferans are stored as the default only from age 18; otherwise the server keeps chess. The response is `{ "saved": true, "settings": {} }`.

`POST /api/v1/account/password`

```json
{
  "current_password": "old",
  "new_password": "new-password-1",
  "repeat_password": "new-password-1"
}
```

The password rules are the same as on the website. The response is `{ "saved": true }`.

`POST /api/v1/account/avatar` is `multipart/form-data`, field `file`. JPEG, PNG, or WebP up to 10 MB. The app crops the portrait and shrinks it to 512×512 before sending: the server stores the bytes it receives. The response is `{ "src": "/avatars/<file>" }`.

`DELETE /api/v1/account/avatar` returns `{ "src": "" }`.

Read a portrait with `GET /avatars/<file>`. The file name is unguessable, and the portrait is served without sign-in so the public pages can show it.

`GET /api/v1/account/chips?page=1` is the chip ledger. A page holds 50 rows.

```json
{
  "chips": 500,
  "page": 1,
  "pages": 1,
  "total": 1,
  "events": [
    {
      "kind": "game",
      "amount": 30,
      "at": "2026-11-17T06:00:00+00:00",
      "game_id": "uuid",
      "game_type": "chess",
      "note": "Победа",
      "person_name": null,
      "username": null,
      "avatar": null
    }
  ]
}
```

`kind` is `game` (a game), `referral` (a friend arrived through the link), or `grant` (an administrator's grant). Chips are for play. They are not money.

## Catalog and home

`GET /api/v1/catalog`

```json
{
  "games": [
    {
      "key": "chess",
      "title": "Шахматы",
      "family": "board",
      "adult": false,
      "blurb": "Классическая партия и разбор.",
      "open": true
    }
  ]
}
```

`family` is `board` or `cards`. `adult: true` is poker, blackjack, and Preferans; under 18 those games are absent from the list. `open: false` means the game is switched off in the parlor settings.

`GET /api/v1/home?page=1`

```json
{
  "greeting": "Добрый вечер, Иван",
  "chips": 500,
  "continue_id": "uuid or null",
  "continue_game": {},
  "recent": [],
  "page": 1,
  "pages": 1,
  "total": 0
}
```

`continue_game` and each `recent` item: `id`, `game_type`, `mode`, `player_side`, `status`, `result`, `updated_at`, `user_id`, `opponent_id`, `join_code`, `creator_name`, `opponent_name`, `creator_login`, `opponent_login`. `continue_id` is the game the Continue button opens. Names here are already the shown names: family and given name when they are filled in, otherwise the username. Profile links are built from `creator_login` and `opponent_login`.

## Friends

`GET /api/v1/friends`

```json
{
  "friends": [
    {
      "id": "friendship uuid",
      "other_id": "person uuid",
      "username": "player",
      "name": "Пётр",
      "avatar": "",
      "relation": "accepted",
      "asked": "сегодня",
      "label": "В сети",
      "live": true,
      "game": "Шахматы",
      "detail": "С человеком"
    }
  ],
  "incoming": [],
  "counts": { "all": 1, "online": 1, "requests": 0 },
  "online_phrase": "1 друг уже в сети",
  "games": []
}
```

`relation`: `accepted`, `incoming`, `outgoing`. `incoming` repeats the incoming requests. `games` is the same catalog, so the app can offer a friend a game.

`POST /api/v1/friends` — `{ "username": "player" }`. Status `201`: `{ "id": "uuid", "username": "player" }`. A repeat is `409 already_friends`.

`POST /api/v1/friends/{id}/accept` returns `{ "accepted": true }`. Only the recipient can accept.

`POST /api/v1/friends/{id}/decline` returns `{ "removed": true }`. It removes both a request and an accepted friendship when one of the two people does it.

`POST /api/v1/friends/{id}/challenge` — `{ "game_type": "chess" }`. The friendship must be accepted. The server creates a table and writes the friend a message with the code. The response is `{ "game_id": "uuid", "join_code": "ab12cd34" }`.

`POST /api/v1/players/{username}/friend` does the same thing as a friend request.

## Lobby

`GET /api/v1/lobby` is who has been seeking a table for the last 15 minutes and who was online in the last 2 minutes.

```json
{
  "seekers": [
    {
      "user_id": "uuid",
      "username": "player",
      "name": "Пётр",
      "avatar": "",
      "game_type": "chess",
      "seats": 2,
      "created_at": "2026-11-17T06:00:00+00:00",
      "mine": false
    }
  ],
  "online": [{ "username": "player", "name": "Пётр", "avatar": "", "live": true }],
  "live_count": 3,
  "games": []
}
```

Under 18, adult games are hidden from `seekers`.

`POST /api/v1/lobby/seek` — `{ "game_type": "uno", "seats": 4 }`. Chess, checkers, Go, and backgammon are always 2 seats. UNO, poker, Durak, and blackjack are 2 to 6. Preferans is 3. Dominoes are 2 to 4. The response is `{ "seeking": true, "game_type": "uno", "seats": 4 }`. A person has one seek: a new one replaces the old one.

`POST /api/v1/lobby/cancel` returns `{ "seeking": false }`.

`POST /api/v1/lobby/accept/{user_id}` seats you with the person who is seeking. The response is `{ "game_id": "uuid" }`. You cannot accept your own seek.

## Chats

`GET /api/v1/chats` is the thread list.

```json
{
  "inbox": [
    {
      "username": "player",
      "name": "Пётр",
      "avatar": "",
      "body": "Последняя реплика",
      "created_at": "2026-11-17T06:00:00+00:00",
      "when": "06:00",
      "live": true
    }
  ],
  "thread": null
}
```

`GET /api/v1/chats/{username}` marks the thread read and adds `thread`:

```json
{
  "username": "player",
  "name": "Пётр",
  "avatar": "",
  "live": true,
  "label": "В сети",
  "friendship_id": "uuid or null",
  "messages": [
    {
      "body": "Зову за стол: Шахматы. Код ab12cd34. Откройте /join?code=ab12cd34",
      "username": "player",
      "name": "Пётр",
      "mine": false,
      "clock": "06:00",
      "show_day": true,
      "day_label": "Сегодня",
      "code": "ab12cd34",
      "game_title": "Шахматы",
      "game_key": "chess"
    }
  ]
}
```

When the text contains a table invitation, `code` and `game_key` are filled. Otherwise they are empty. Accept the invitation with `POST /api/v1/games/join`.

`POST /api/v1/chats/{username}` — `{ "body": "Text" }`. From 1 to 1000 characters after whitespace is collapsed. The response is the same thread as GET.

`GET /api/v1/notices` is up to six fresh private messages and friend requests, plus counts.

```json
{
  "items": [
    {
      "kind": "message",
      "id": "uuid",
      "name": "Пётр",
      "username": "player",
      "avatar": "",
      "text": "Короткий текст",
      "action": "Прочитать",
      "href": "/chats/player"
    }
  ],
  "counts": { "requests": 0, "chats": 1, "live": 3 }
}
```

`kind: "request"` leads to friends. There is no push yet: the app polls this method.

`counts.live` is the number of live tables, not unread messages.

## Live tables

`GET /api/v1/live`

```json
{
  "tables": [
    {
      "id": "uuid",
      "game_type": "chess",
      "open": true,
      "mine": false,
      "players": "Иван",
      "creator": "Иван",
      "creator_login": "mobile",
      "creator_avatar": "",
      "opponent": "",
      "opponent_login": "",
      "opponent_avatar": "",
      "computer": false,
      "mode_label": "С человеком",
      "meta": "Ждёт соперника",
      "watch_label": "Без наблюдателей",
      "age_block": "",
      "can_sit": true,
      "can_watch": true,
      "vacancies": 1
    }
  ],
  "open_count": 1,
  "closed_count": 0
}
```

`POST /api/v1/live/{id}/watch` and `POST /api/v1/live/{id}/sit` return `{ "game_id": "uuid" }`. No body. If the game is 18+ and the date is missing or the person is under 18, the response is `403 adult_only`.

Sit by code: `POST /api/v1/games/join` with `{ "code": "ab12cd34" }`. Watch by code: `POST /api/v1/games/watch` with the same body. Both responses are the game state.

## News

No sign-in.

`GET /api/v1/news?page=1` returns 6 posts.

```json
{
  "posts": [
    {
      "id": "uuid",
      "title": "Заголовок",
      "summary": "Коротко",
      "body": "<p>HTML</p>",
      "kind": "news",
      "cover": "house",
      "cover_dark": null,
      "published_on": "2026-11-01"
    }
  ],
  "page": 1,
  "pages": 1,
  "total": 3
}
```

`body` is already sanitized HTML. `GET /api/v1/news/{id}` returns `{ "post": {} }`.

If `cover` looks like `32hex.jpg`, `32hex.png`, or `32hex.webp`, the picture is at `/news-images/{cover}` and needs no sign-in. Otherwise it is the name of a built-in site cover. `cover_dark` is a custom cover for the dark theme, or `null`. One uploaded file stays in `cover`, with `cover_dark` empty.

Rules, privacy, and contact stay website pages: `/rules`, `/privacy`, `/contact`.

## Profile

`GET /api/v1/players/{username}`

```json
{
  "username": "player",
  "name": "Пётр",
  "full_name": "Пётр",
  "avatar": "",
  "created_at": "2026-01-01T00:00:00+00:00",
  "online": true,
  "presence": "В сети",
  "chips": 500,
  "friend_state": "none",
  "stats": {
    "played": 4,
    "wins": 2,
    "losses": 1,
    "draws": 1,
    "rate": 50,
    "games": [
      { "key": "chess", "title": "Шахматы", "played": 4, "wins": 2, "losses": 1, "draws": 1, "width": 100 }
    ],
    "weeks": [{ "label": "17 ноя", "played": 1, "wins": 1 }]
  },
  "breakdown": {
    "chess": { "total": 4, "active": 0, "wins": 2, "losses": 1, "draws": 1 }
  }
}
```

`friend_state`: `self`, `none`, `outgoing`, `incoming`, `accepted`. `weeks` is eight weeks from Monday, enough for a chart. `stats` also has `line` and `donut` with the coordinates the website uses for its SVG. An app should chart from `weeks`, `games`, wins, losses, and draws.

`GET /api/v1/players?q=pet` searches for an invitation, up to 8 people: `{ "players": [{ "username", "name", "live" }] }`. This is not the profile page.

`POST /api/v1/players/{username}/chips` is administrator only, `{ "amount": 100 }`. Otherwise 404. The response is `{ "chips": 600 }`. The rest of the admin area stays on the website.

## A game

Read the whole state:

`GET /api/v1/games/{id}`

While a game is live, the app repeats this request. There is no socket for moves. The socket below is only for video and voice.

Create a table: `POST /api/v1/games`

```json
{
  "game_type": "chess",
  "mode": "vs_computer",
  "player_side": "white",
  "engine_level": 3,
  "engine_time_ms": 1000,
  "audience": "closed"
}
```

`player_side` is `white` or `black`. `audience` is `open` or `closed`. `engine_level` is 1 to 5. `engine_time_ms` is 100 to 10000.

Modes:

| `mode` | Where | What it is |
| --- | --- | --- |
| `vs_computer` | Every game | You against the computer. For cards the mode is chosen for you when no seat is open |
| `online` | Every game | The table waits for people. `join_code` is present while you are seated |
| `free` | Chess and checkers only | Both sides are yours, and the table is closed |
| `analysis` | Chess and checkers only | Study a position. Both sides are yours |
| `lesson` | Chess and checkers only | The same, suited to a pasted record |

Go, dominoes, and backgammon accept only `vs_computer` and `online`: `free`, `analysis`, and `lesson` are `422 bad_mode`. The other card games hide those three modes in the form. When cards are given `computers` and `open_seats`, the server sets `online` if a seat is open for a person, and `vs_computer` if none is.

Extra fields:

| Field | Rule |
| --- | --- |
| `board_size` | Go: `9`, `13`, or `19`. Empty means 19 |
| `durak_kind` | `podkidnoy` or `perevodnoy`. Empty means podkidnoy |
| `nardy_kind` | `long` or `short`. Empty means long. The doubling cube exists only in the short game |
| `pool` | Preferans, a pool from 6 to 20 |
| `computers` | Computers at a card table, 0 to 5. Preferans needs exactly two seats besides you, computers and open seats together. Blackjack allows at most five besides you. UNO, poker, and Durak need one to five seats besides you. Dominoes need one to three seats besides you, computers and open seats together |
| `open_seats` | Seats for people, by code or Sit. The same limits |
| `initial_fen` | Chess only, FEN |
| `pgn` | Chess only |
| `initial_position` | Checkers only, an RCP record |
| `moves` | A list of strings. Chess is UCI, one move each: `"e2e4"`. Checkers is `"22-18"` or a capture `"21:14:7"`. Go and cards ignore this field |

`audience` matters for `online` and `vs_computer`. Other modes force a closed table. An open table appears in `GET /live` and can be sat at and watched without a code. A closed table opens only with the code.

Status `201` is the game state. An online table includes `join_code` while you are seated. While `status` is `waiting`, the game has not started: pass the code or wait for someone to sit. A card table with open seats starts when no seat is left.

### Shared state fields

These exist for the board and for cards.

| Field | Meaning |
| --- | --- |
| `id`, `you` | The game and your user UUID |
| `game_type` | `chess`, `checkers`, `go`, `domino`, `nardy`, `uno`, `poker`, `durak`, `blackjack`, `preferans` |
| `table` | `board`, `cards`, or `go` |
| `variant`, `mode`, `status` | Kind, mode, and `waiting` / `active` / `finished`. During Go scoring, `status` is `scoring` |
| `version` | The position number. Send it back with a move |
| `your_side`, `side_to_move`, `your_turn` | Your side, whose turn it is, and whether you may move |
| `watching` | You are watching, not playing |
| `gallery` | In Durak your seat was given to a computer and you are watching the finish. While `true`, the next `engine-move` should use `steps: 1` |
| `legal_moves` | Moves the server will accept now. Empty on someone else's turn |
| `moves` | History: `ply`, `notation`, `algebraic`, `by` |
| `result`, `result_reason`, `result_message`, `result_tone` | The outcome. `result` is `white_win`, `black_win`, `draw`, or `{seat}_win`. `result_message` is the sentence for the screen. `result_tone` is `win`, `loss`, `draw`, `stop`, or `null` |
| `status_line` | A line to show above the table |
| `summary` | The end-of-game window, or `null` until the game is over |
| `can_move`, `can_stop`, `can_undo`, `can_hint`, `can_engine` | Which buttons are available |
| `join_code`, `audience`, `waiting` | The entry code, openness, and whether the table is waiting |
| `opponent_name`, `you_name`, `creator_name` | Names at the table |
| `in_call`, `call_roster` | Whether a video call is possible, and who is already at the table |
| `ice_servers` | The ICE list for `RTCPeerConnection`: STUN, and TURN plus TURNS when TURN is configured |
| `live` | While `true`, keep polling the table |
| `rematch` | `available`, `state` (`idle`, `outgoing`, `incoming`, `accepted`, `declined`), `game_id`, `note` |
| `white_name`, `black_name`, `white_login`, `black_login`, `white_avatar`, `black_avatar` | The two faces when the table is white and black |
| `login`, `avatar`, `opponent_login`, `opponent_avatar` | Your portrait and the opponent |
| `engine_level`, `engine_time_ms` | Computer strength and thinking time |
| `computer_turn` | Cards: the computer is to move. Then call `POST /engine-move` |
| `can_engine` | The server will accept a computer move |

While `live` is `true`, read `GET /games/{id}` about once every 1.5 seconds and redraw when `version`, `status`, or `rematch` changes. The table chat can be read separately, about once every 2 seconds. Moves do not arrive on the socket.

If `can_engine` and the game is active against the computer, or cards have `computer_turn`, call `POST /games/{id}/engine-move` with the current `version`. The body may include `steps` from 1 to 40. In cards, when `held` is already true, wait until the player has seen the table and only then ask for the next move: the server stops the series on that reply. In Go, do the same during scoring when `can_engine` is set. After your own move, the `/moves` response already contains the computer's reply when it arrived in time. `engine_error` then says the reply did not come out and must be requested separately.

`summary` appears when the game ends or is stopped. `summary.line` is the sentence of the summary window. `summary.seats` rows have `key`, `name`, `login`, `avatar`, `winner`. A board also has `pieces` and `kings`. Cards have `cards`, `count`, `action`. A poker row has `payout`, `invested`, `stack`, `made`, `busted`. UNO has `said`. `summary.kind` is `board`, `uno`, `poker`, or `parlor`.

A player's seat is `your_side` and `seats[].key`. A two-seat table uses `white` and `black`. When a card table is created with several computers or open seats, the seats are named `p0`, `p1`, `p2`…. The creator sits at `p0`. A three-player Preferans table also uses `p0`, `p1`, `p2`. Dominoes for three or four use the same `p0`… keys. A two-player domino table still uses `white` and `black`. The same keys appear in `stacks`, `committed`, `shown`, and `summary.seats`.

### Chess and checkers

`table` is `board`. The board is 64 cells in `cells`, rank by rank from the bottom, and left to right inside a rank. A cell has `square`, `file` (0 is the a-file), `rank` (0 is rank 1), `dark`, `piece`, `color`, `aria`, `number`.

A piece is an uppercase letter: `P` pawn, `N` knight, `B` bishop, `R` rook, `Q` queen, `K` king. In checkers `M` is a man and `K` is a king. `color` is `white` or `black`. An empty cell has both as `null`.

In chess `square` is a name such as `e4`, and `number` is empty. Checkers are played on the dark squares: those have `number` from 1 to 32, and `square` is that number as a string. Light squares are not used in moves.

`black_at_bottom` means draw black at the bottom. `POST /orientation` flips the board and returns the new state. `in_check` and `check_square` are check and the king's square. `last_move` is the squares of the last move; they can be highlighted.

A `legal_moves` item is `{ "path": ["e2", "e4"], "promotion": null, "notation": "e4" }`. In checkers `path` is square numbers as strings, for example `["22", "18"]`, or a capture across several squares. Promotion exists only in chess: if the chosen move has `promotion` other than `null`, send that letter (`q`, `r`, `b`, `n`) unchanged. The app shows `notation` and returns `path` and `promotion` to the server without rebuilding them. While a person is choosing a long capture, every move whose `path` starts with the squares already chosen is still legal.

`can_undo` exists only on a board. `can_hint` is for an administrator in an active game.

### Go

`table` is `go`. Moves go through `POST /go`. The `legal_moves` list is empty.

`size` is 9, 13, or 19. `board` is a string of length `size * size`, row by row from the top. `0` is empty, `1` is black, `2` is white. A point index is `row * size + col`, both starting at zero, `col` to the right and `row` downward. `komi` is the komi string, usually `7,5`. `captures` is `{ "black", "white" }`. `rules` is the area-rules identifier.

`legal` is the list of points where a stone may be played: `[[col, row], …]`. An empty list means a stone cannot be played now. `last` is the last stone `{ "kind": "move", "color", "col", "row" }` or a pass `{ "kind": "pass", "color" }`. `notice` is a sentence about a pass.

`phase` is `play` during the game and `score` during scoring. During scoring, `status` is `scoring`. `dead` is the removed groups, a list of `[col, row]` pairs. `tally` during scoring has the side scores, `komi`, and `territory`: `[{ "col", "row", "owner" }]`, where `owner` is `black` or `white`.

Go buttons follow these fields, not the shared `can_move` alone:

| Field | Command |
| --- | --- |
| `your_turn` | `action: "move"` with `col` and `row` from `legal` |
| `can_pass` | `action: "pass"` |
| `can_resign` | `action: "resign"` |
| `can_mark` | `action: "mark"` — mark a dead group at `col`, `row` |
| `can_agree` | `action: "agree"` — accept the score |
| `can_resume` | `action: "resume"` — return to play |

`command_id` is new for every press. Repeating the same command does not place a second stone. `pass`, `resign`, `agree`, and `resume` do not need coordinates.

### Cards

`table` is `cards`. The hand is `hand`, an array of codes. Other players' cards are not sent until they are shown: the size of another hand is `seats[].count` and `opponent_count`.

An ordinary card is two characters. The first is the rank: `2`–`9`, `T` for ten, `J`, `Q`, `K`, `A`. The second is the suit: `C` clubs, `D` diamonds, `H` hearts, `S` spades. Example: `AH` is the ace of hearts. Durak starts at the six. Preferans starts at the seven.

UNO uses a different code. A color `R`, `Y`, `G`, `B` plus a sign: a digit `0`–`9`, `S` skip, `D` draw two. `W` is wild. Examples: `R7`, `YD`, `W`.

A move is a whole `legal_moves` item. Show the person `notation`, and send its `path` and `promotion` (null for cards). Do not build `path` yourself, except for one case: a poker bet or raise.

| Game | What `path` looks like |
| --- | --- |
| UNO | `["play", "R7"]`, a wild `["play", "W", "R"]`, draw `["draw", "1"]`, call UNO `["uno"]`. A play that also calls UNO ends with `"uno"` |
| Poker | `["act", "check"]`, `["act", "call"]`, `["act", "fold"]`, an exchange `["draw", "-"]` or `["draw", "AH,KD"]`. If the item has `min` and `max`, it is a bet or a raise: append the chosen total as a string, for example `["act", "raise", "40"]`. The total is from `min` to `max`. Without a number the server uses `min`. `put` is what this seat has already committed |
| Durak | Attack, beat, and throw-in: `["play", "7H"]`. Take: `["act", "take"]`. Beat: `["act", "pass"]` |
| Blackjack | A bet `["bet", "10"]`, then `["act", "hit"]`, `["act", "stand"]`, `["act", "double"]` |
| Preferans | Bidding `["bid", "pass"]`, `["bid", "miser"]`, or a contract taken from `notation`. Whist `["whist", "yes"]` and `["whist", "no"]`. Discarding the talon `["discard", "7C", "8D"]`. A trick `["play", "AH"]` |
| Dominoes | A tile on the right end `["play", "6-1", "R"]`, on the left end `["play", "6-1", "L"]`. Draw from the boneyard `["draw", "1"]`. Pass when the boneyard is empty `["pass", "1"]`. A tile code is `high-low`, from `6-6` down to `0-0`. On the opening turn `legal_moves` contains only the tile the rules require |

Shared table fields: `phase`, `pot`, `deck` (cards left in the deck), `board` (community cards, the trick, or the dealer's cards), `last_move`. `seats` is who sits: `key`, `name`, `login`, `avatar`, `kind` (`you`, `human`, `computer`, `open`), `count`, `you`, `turn`, `cpu`, `stack`, `bet`, `folded`, `busted`, `dealer`, `winner`, `mark`. In Preferans a seat also has `taken`, the tricks already taken, and `order_need`: how many were ordered, only for the declarer during play, otherwise `null`.

Then, by game:

| Field | Where to look |
| --- | --- |
| `stacks`, `committed`, `button`, `shown`, `winner_hand` | Poker. `shown` is revealed hands by seat key. `phase`: `waiting`, `preflop`, `flop`, `turn`, `river`, `done` |
| `top`, `color`, `deck`, `said` | UNO. `top` is the discard, `color` is the current color `R`/`Y`/`G`/`B`/`W`, `said` is who called UNO |
| `trump`, `trump_card`, `pairs`, `held` | Durak. `trump` is the trump suit, `trump_card` is the face-up trump while it is still in the deck. `pairs` are `{ "attack", "defense" }` on the table. `held` means this is an already beaten table, not a new attack. While `held`, the site keeps the cards for about two and a half seconds before it asks for the computer's next move |
| `hole`, `board`, `stacks`, `committed` | Blackjack. `board` is the dealer's cards. `hole: true` means the dealer's second card is still hidden and is not in `board`. Bets are in `committed` |
| `contract`, `contract_need`, `declarer`, `tricks`, `sheet`, `scored`, `note`, `talon`, `held` | Preferans. `contract` is the current bid in words. `contract_need` is the number of tricks in the contract, `0` for a miser, `null` for raspasy. `declarer` is the seat that ordered the game. `tricks` is how many tricks each seat already has. `sheet`: `pool`, `closed`, `seats`, `bullet`, `mountain`, `whists`, `total`. `board` is the trick. `held` is the previous trick, and it also stays on the table before the next lead |
| `chain`, `deck`, `hand` | Dominoes. `hand` is your tiles, coded `6-1`. Other tiles are not sent, only `seats[].count`. `deck` is how many tiles remain in the boneyard. `chain` is the play order from the opening tile: `tile`, `spin` (a double lies across the line), `hi_left` (the higher half faces back toward the start). On the table a long line is drawn as one snake, horizontal then a vertical turn, but the `chain` order does not change. `phase` is `play` or `done`. A result reason `empty` means a hand ran out, `blocked` means the line is closed, `left` means an opponent left. `summary.kind` for dominoes is `parlor` |
| `nardy` | Backgammon. `points` is 24 points, positive for white and negative for black. `bar` and `off` are the bar and the borne-off checkers. `dice` is the last roll and `remaining` is the dice still to play. `cube` and `cube_owner` are the doubling cube, only in the short game. `targets` lists the moves you may play: `from`, `die`, `to`, `hit`. A move is `["dice","roll"]`, `["dice","double"]`, `["dice","take"]`, `["dice","drop"]`, or `["move", point, die]`. The point `bar` re-enters. Ask `engine-move` with `steps: 1` so the dice and each checker arrive separately. `summary.kind` is `parlor` |

`note` and `status_line` can be shown above the table. A Preferans `summary` also has `sheet`.

### Sending a move

`POST /api/v1/games/{id}/moves`

```json
{ "version": 3, "path": ["e2", "e4"], "promotion": null }
```

The response is `{ "state": {}, "engine_error": null }`. If the computer could not answer, `engine_error` is text, and `state` already contains your move. On `409 stale_position`, read the game again and take the new `version`.

Go does not move through `/moves`. `POST /api/v1/games/{id}/go`

```json
{
  "command_id": "a unique string of 8–80 characters",
  "version": 3,
  "action": "move",
  "col": 3,
  "row": 4
}
```

`action`: `move`, `pass`, `resign`, `mark`, `agree`, `resume`. `pass` does not need coordinates. `command_id` is new for every press. Repeating the same command does not place a second stone. The response is the state.

Other actions at the table:

| Method | Body | Response |
| --- | --- | --- |
| `GET /games/{id}/legal-moves` | — | `{ "version", "moves" }` |
| `GET /games/{id}/history` | — | `{ "version", "moves" }` |
| `POST /games/{id}/undo` | `{ "version" }` | state |
| `POST /games/{id}/resign` | `{ "version" }` | state |
| `POST /games/{id}/step-aside` | `{ "version", "pace" }` | Only a started Durak where two or more computers sit with you and no other person or empty seat remains. `pace`: `watch` gives your seat to a computer and returns a state with `gallery: true`; `fast` finishes the game at once. Otherwise `409 stay` |
| `POST /games/{id}/stop` | `{ "version" }` | state. Only the creator can stop the game |
| `POST /games/{id}/engine-move` | `{ "version", "steps" }` | state, when it is time to ask for the computer. `steps` is 1 to 40, and 40 is the default. In cards the series stops at `held`, so the client can show the finished table |
| `POST /games/{id}/hint` | `{ "version" }` | Administrator only. `{ "version", "private": true, "engine", "nodes", "lines" }`. A line has `notation`, `path`, `promotion`, `score_white`, `mate`, `pv`, `depth`. Go has no hint |
| `POST /games/{id}/orientation` | empty | The new state with the board flipped |
| `POST /games/{id}/save` | empty | `{ "saved": true, "updated_at" }`. The game rises into Continue |
| `GET /games/{id}/export` | — | A file, not JSON. Chess is `text/plain`, `game.pgn`. Go is `application/x-go-sgf`, `game.sgf`. Checkers is `text/plain`, `checkers.txt`. Cards are the move text, `{game}.txt` |
| `POST /games/{id}/rematch` | empty | Against the computer, `{ "game_id", "rematch" }` at once. Against a person, an offer; when both agree, `game_id` of the new game is there too |
| `POST /games/{id}/rematch/decline` | empty | `{ "game_id": null, "rematch" }` |
| `POST /games/{id}/invite` | `{ "username" }` | `{ "sent": "player" }`. Writes the table code into a private chat. At most 20 times a minute. The table must still be waiting, and the inviter must be seated |

A rematch exists after a win or a loss in a game against a person or the computer. A draw and a stopped board do not have one. Cards still have one after a stop, until the table is closed for lack of chips: then `note` says the chips are gone. When `rematch.state` is `accepted`, open `rematch.game_id`.

The table chat is not a private thread:

`GET /api/v1/games/{id}/chat` — up to 80 lines: `{ "messages": [{ "body", "username", "login", "avatar", "at" }] }`. Here `username` is the shown name and `login` is the account name. A seated player and a watcher of an open table may write. At most 30 lines a minute.

`POST /api/v1/games/{id}/chat` — `{ "body": "Text" }`, response `{ "saved": true }`.

Theme alone, without the other settings: `POST /api/v1/settings/theme` with `{ "theme": "dark" }` returns `{ "theme": "dark" }`. Full settings are `PUT /api/v1/account/settings`. The older `POST /api/v1/settings` accepts the same body as `PUT /api/v1/account/settings` and returns `{ "saved": true }`.

## Video and voice

The socket does not carry moves. It only introduces players who are already seated at one online table. The streams go between the phones. The ICE list is the `ice_servers` field of the game state. On the public parlor it contains STUN, TURN, and TURNS. When Valkey is available, the signal reaches a player on another site pod.

```text
GET /ws/tables/{game_id}
Authorization: Bearer <access_token>
```

An app with a token does not have to send an `Origin` header. The website still admits only its own cookie and only from its own address.

The server sends:

| `type` | Meaning |
| --- | --- |
| `peers` | `{ "ids": ["uuid", ...] }` — who is already in the room |
| `peer-joined` | `{ "id": "uuid" }` |
| `peer-left` | `{ "id": "uuid" }` |
| `signal` | `{ "from": "uuid", "data": {} }` — someone else's WebRTC message |
| `full` | six people are already in the room, then the socket closes |

The app sends a signal to one person:

```json
{ "type": "signal", "to": "the other person's uuid", "data": { "sdp": "..." } }
```

`data` is your WebRTC payload. The server does not inspect it. A message is at most 8192 characters. A watcher is closed with `1000` and `{ "type": "watch" }`: the game can be watched, and talking at the table cannot.

Close codes: `4401` not signed in, `4403` a foreign site or maintenance, `4404` no such game, `4408` the room is full.

## What to build first

1. Read `GET /auth/register`. If `open`, solve the check, call `POST /auth/register`, and store the tokens. If the name is missing, call `PATCH /account` at once.
2. Otherwise sign in with `parlor-ios` or `parlor-android`, store the refresh token, and exchange it quietly on 401.
3. Home with `GET /home`, the catalog, creating a game, and reading `GET /games/{id}`.
4. A move from `legal_moves` through `POST /moves`. In Go, `POST /go`. If `can_engine`, ask for the computer's move.
5. Friends, the lobby, chats, live tables, the table chat, and the profile.
6. Portrait, settings, chips, news.
7. Video separately, once a table is already being played.

Rules, privacy, and contact stay website pages: `/rules`, `/privacy`, `/contact`. The admin overview stays on the website. The parlor does not push notifications to a phone.
