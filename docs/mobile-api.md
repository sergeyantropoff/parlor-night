# Parlor Night API для мобильного приложения

Руководство по гостиной: [на русском](ru/guide.md) · [in English](en/guide.md).
English API: [API reference](en/api.md).

Базовый адрес — тот же, что у сайта. Локально это `http://127.0.0.1:8010`. Все методы ниже начинаются с `/api/v1`, кроме подтверждения чужого приложения (`/oauth/authorize`), картинок и сокета стола.

Сайт по-прежнему входит через куку `bm_session`. Приложение куку не использует: оно получает пару токенов и дальше передаёт короткий токен в заголовке.

```http
Authorization: Bearer <access_token>
Content-Type: application/json
Accept: application/json
```

Тело JSON-запросов — UTF-8. Даты и время в ответах — ISO 8601. Идентификаторы — строки UUID.

## Ошибки

Неуспешный ответ выглядит так:

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Нужно войти в систему.",
    "details": {}
  }
}
```

| Код HTTP | `code` | Когда |
| --- | --- | --- |
| 401 | `unauthorized` | Нет токена, токен просрочен или неверный пароль |
| 401 | `invalid_client` | Неизвестный `client_id` |
| 401 | `invalid_grant` | Код подтверждения чужого приложения уже использован или неверен |
| 403 | `forbidden` | Чужое приложение пытается войти или зарегистрироваться паролем |
| 403 | `registration_disabled` | Самостоятельная регистрация выключена |
| 403 | `referral_required` | Регистрация только по живой ссылке друга |
| 409 | `username_taken` | Такой логин уже занят |
| 422 | `captcha` | Проверка «не робот» не решена или уже использована |
| 403 | `csrf` | Запрос с кукой сайта без защитного токена. Приложение с Bearer этот код не получает |
| 409 | `name_required` | Учётная запись ещё без имени |
| 409 | `stale_position` | Позиция партии уже изменилась, нужно заново прочитать стол |
| 409 | `wrong_turn` | Сейчас ход другой стороны |
| 422 | `invalid_body` | Тело не совпало со схемой. В `details.fields` имена полей |
| 403 | `adult_only` | Покер, блэкджек или преферанс, а человеку нет 18 или дата не указана |
| 403 | `game_closed` | Игра выключена в настройках гостиной |
| 403 | `table_closed` | Сесть или смотреть закрытый стол без кода нельзя |
| 403 | `not_player` | Наблюдатель пытается ходить, сдаться или предложить реванш |
| 403 | `stop_forbidden` | Остановить партию может только тот, кто её создал |
| 403 | `hint_forbidden` | Подсказка доступна только администратору |
| 404 | `not_found` | Нет партии, игрока, новости или заявки |
| 409 | `already_friends` | Заявка в друзья уже есть |
| 409 | `game_full` | Свободных мест за столом нет |
| 409 | `finished` | Партия уже завершена |
| 409 | `not_started` | Действие доступно только в начатой партии |
| 409 | `no_rematch` | Реванш сейчас предложить или отклонить нельзя |
| 409 | `undo_rejected` | Этот ход отменить нельзя |
| 409 | `engine_rejected` | Компьютер сейчас не ходит |
| 409 | `table_done` | За покерным столом фишки остались у одного |
| 422 | `illegal_move` | Ход против правил |
| 422 | `bad_date` | Дата рождения неполная или неверная |
| 422 | `bad_password` | Новый пароль не проходит правила или не совпал с повтором |
| 422 | `bad_game` | Неизвестная или закрытая игра, стол уже не ждёт |
| 422 | `bad_message` | Текст пустой или длиннее 1000 символов |
| 422 | `bad_code` | Код стола — ровно 8 символов |
| 422 | `bad_import` | Стартовая позиция не подошла к выбранной игре |
| 422 | `bad_mode` | Режим партии этой игре не подходит |
| 422 | `bad_board` | Размер доски го не 9, 13 и не 19 |
| 422 | `bad_seats` | Число мест за карточным столом не сходится с правилами |
| 422 | `bad_variant` | У дурака нужен подкидной или переводной |
| 422 | `bad_image` | Портрет не JPEG, PNG или WebP, либо больше 10 МБ |
| 422 | `bad_amount` | Сумма фишек не задана |
| 429 | `rate_limited` | Слишком много запросов. Есть заголовок `Retry-After` |
| 503 | `maintenance` | Гостиная закрыта |

Общий предел — 240 запросов за 10 секунд с одного адреса. Вход дополнительно ограничен неудачными попытками, как на сайте.

Пока у записи нет имени, любой метод, кроме `/api/v1/auth/…` и `/api/v1/account…`, отвечает `409 name_required`.

## Список методов

Все JSON-методы проекта перечислены здесь. Подробности — в разделах ниже. Префикс `/api/v1`, если путь не начинается с `/`.

| Метод | Назначение |
| --- | --- |
| `GET /auth/register` | Можно ли регистрироваться и какие правила у логина и пароля |
| `GET /auth/captcha` | Задание «не робот» |
| `POST /auth/register` | Создать учётную запись и сразу войти |
| `POST /auth/login` | Вход нашего приложения |
| `POST /auth/refresh` | Новая пара токенов |
| `POST /auth/logout` | Погасить цепочку |
| `POST /auth/token` | Обмен кода чужого приложения |
| `GET /auth/me` | Кто вошёл |
| `GET /catalog` | Игры, которые этому человеку можно начать |
| `GET /home` | Кабинет: продолжить партию и недавние столы |
| `GET /account` | Имя, дата, настройки, ссылка приглашения |
| `PATCH /account` | Имя и дата рождения |
| `PUT /account/settings` | Тема, доска, игра по умолчанию, разбор |
| `POST /account/password` | Смена пароля |
| `POST /account/avatar` | Загрузить портрет |
| `DELETE /account/avatar` | Убрать портрет |
| `GET /account/chips` | История фишек |
| `GET /friends` | Друзья и заявки |
| `POST /friends` | Заявка по логину |
| `POST /friends/{id}/accept` | Принять заявку |
| `POST /friends/{id}/decline` | Отклонить заявку или удалить дружбу |
| `POST /friends/{id}/challenge` | Создать стол и написать другу код |
| `GET /lobby` | Кто ищет стол и кто в сети |
| `POST /lobby/seek` | Искать стол |
| `POST /lobby/cancel` | Снять свою заявку |
| `POST /lobby/accept/{user_id}` | Сесть к тому, кто ищет |
| `GET /chats` | Список бесед |
| `GET /chats/{username}` | Диалог, помечается прочитанным |
| `POST /chats/{username}` | Реплика в диалог |
| `GET /notices` | Свежие сообщения, заявки и счётчики |
| `GET /live` | Открытые столы |
| `POST /live/{id}/watch` | Смотреть открытый стол |
| `POST /live/{id}/sit` | Сесть за открытый стол |
| `GET /news`, `GET /news/{id}` | Новости, без входа |
| `GET /players` | Поиск логина для приглашения |
| `GET /players/{username}` | Профиль и статистика |
| `POST /players/{username}/friend` | Та же заявка, что `POST /friends` |
| `POST /players/{username}/chips` | Начислить фишки. Только администратор |
| `POST /games` | Создать партию |
| `POST /games/join` | Сесть по коду |
| `POST /games/watch` | Смотреть по коду |
| `GET /games/{id}` | Состояние стола |
| `GET /games/{id}/legal-moves` | Текущие ходы |
| `GET /games/{id}/history` | Журнал ходов |
| `POST /games/{id}/moves` | Ход в шахматах, шашках и картах |
| `POST /games/{id}/go` | Команда го |
| `POST /games/{id}/undo` | Отменить ход |
| `POST /games/{id}/resign` | Сдаться |
| `POST /games/{id}/step-aside` | В дураке отойти и досмотреть компьютеры или закончить стол сразу |
| `POST /games/{id}/stop` | Остановить партию |
| `POST /games/{id}/engine-move` | Попросить ход компьютера |
| `POST /games/{id}/hint` | Разбор. Только администратор |
| `POST /games/{id}/orientation` | Перевернуть доску |
| `POST /games/{id}/save` | Отметить партию свежей |
| `GET /games/{id}/export` | Скачать запись партии |
| `POST /games/{id}/rematch` | Реванш |
| `POST /games/{id}/rematch/decline` | Отклонить реванш |
| `POST /games/{id}/invite` | Пригласить игрока в беседу |
| `GET /games/{id}/chat` | Чат стола |
| `POST /games/{id}/chat` | Реплика за столом |
| `POST /settings` | То же тело, что у `PUT /account/settings` |
| `POST /settings/theme` | Только тема |
| `GET /avatars/{файл}` | Портрет, нужен вход |
| `GET /news-images/{файл}` | Обложка новости, без входа |
| `GET /ws/tables/{id}` | Сокет видео и голоса |
| `GET /oauth/authorize`, `POST /oauth/authorize` | Подтверждение чужого приложения на сайте |

Страницы `/rules`, `/privacy`, `/contact` и вся админка (обзор, новости, список гостей, настройки гостиной) остаются HTML сайта. Отдельной JSON-ручки «удалить друга» нет: принятую дружбу снимает `POST /friends/{id}/decline`. Дату рождения для взрослых игр сохраняет `PATCH /account`, отдельной ручки возраста нет.

## Токены

Наши приложения ходят с публичным `client_id`:

- `parlor-ios`
- `parlor-android`

Это не секрет. Пароль пользователя в бинарник приложения не вшивается. Зарегистрироваться можно из приложения, если гостиная это разрешает.

Ответ входа, обновления и обмена кода один и тот же:

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

`expires_in` — срок access-токена в секундах, всегда 900 (15 минут). `refresh_expires_in` — срок refresh-токена, он совпадает с сессией сайта. По умолчанию это 14 суток.

Access кладётся в память и подставляется в `Authorization`. Refresh хранится в Keychain на iOS и в Keystore на Android. В обычные запросы refresh не подставляется. В логи токены не пишутся.

Когда access кончается, приложение один раз вызывает обновление и повторяет исходный запрос. Если несколько запросов получили 401 одновременно, обновление выполняется один раз, остальные ждут ту же новую пару. Старый refresh после обмена гаснет. Если прислать его ещё раз, сервер гасит всю цепочку, включая уже выданный новый access: это значит, что токен увели. Тогда приложение стирает оба токена и показывает вход.

На обновление и выход заголовок `Authorization` можно не ставить. Если access уже просрочен, заголовок со старым токеном как раз мешает: сервер ответит 401 раньше, чем прочитает тело. Для этих двух методов достаточно JSON с `refresh_token`.

Смена пароля в приложении оставляет текущую цепочку и гасит остальные входы, включая сайт. Смена пароля на сайте гасит все токены приложений.

### Вход нашего приложения

`POST /api/v1/auth/login`

```json
{ "username": "mobile", "password": "secret-pass-1", "client_id": "parlor-ios" }
```

Логин приводится к нижнему регистру. Неверный пароль — 401 с тем же текстом, что и на сайте. Чужой `client_id` с паролем получает 403: такое приложение подтверждается на сайте и пароль не видит.

### Регистрация

`GET /api/v1/auth/register` говорит, можно ли сейчас создать учётную запись. Параметр `ref` — код приглашения, если гостиная открыта только по ссылке.

```json
{
  "mode": "open",
  "open": true,
  "referral_required": false,
  "username_min": 3,
  "username_max": 32,
  "password_min": 10,
  "password_letter": true,
  "password_digit": true,
  "password_rules": "Не меньше 10 символов, хотя бы одна буква, хотя бы одна цифра, не длиннее 128 символов.",
  "client_ids": ["parlor-ios", "parlor-android"]
}
```

`mode`: `open` — можно всем, `referral` — только с живым кодом приглашения, `closed` — нельзя. `open: false` значит, что с этим `ref` регистрироваться нельзя. При `closed` и при ссылке без кода ответ всё равно 200, чтобы приложение показало причину, а не ошибку сети.

Перед созданием учётной записи приложение решает ту же проверку, что и сайт.

`GET /api/v1/auth/captcha` — в режиме ссылки добавьте `?ref=код`. Ответ:

```json
{
  "algorithm": "SHA-256",
  "challenge": "hex",
  "maxnumber": 100000,
  "salt": "…?expires=…",
  "signature": "hex"
}
```

Нужно найти число от 0 до `maxnumber`, у которого SHA-256 от строки `salt + число` совпадает с `challenge`. Затем собрать JSON и закодировать его в base64:

```json
{
  "algorithm": "SHA-256",
  "challenge": "…",
  "number": 12345,
  "salt": "…",
  "signature": "…"
}
```

Это поле `captcha`. Задание живёт около 10 минут и принимается один раз. Чаще 30 запросов задания в минуту с одного адреса нельзя.

`POST /api/v1/auth/register` создаёт гостя и сразу входит. Ответ `201` — та же пара токенов, что у входа. Имя ещё не задано, поэтому `user.ask_name` равен `true`: следующим шагом вызовите `PATCH /api/v1/account`.

```json
{
  "username": "newbie",
  "password": "secret-pass-1",
  "client_id": "parlor-ios",
  "born_day": "16",
  "born_month": "11",
  "born_year": "1990",
  "captcha": "base64 из проверки",
  "referral": ""
}
```

Дата рождения обязательна, как на сайте: по ней открываются покер, блэкджек и преферанс. `referral` — код из ссылки `/?ref=`. В режиме `referral` без живого кода будет `403 referral_required`. При закрытой регистрации — `403 registration_disabled`. Занятый логин — `409 username_taken`. Чужой `client_id` — `403`, такое приложение учётные записи не создаёт.

Если в `user.ask_name` стоит `true`, сначала сохраните имя. Пока его нет, остальные методы, кроме перечисленных в разделе «Аккаунт» и методов `/auth`, отвечают `409 name_required`.

### Кто вошёл

`GET /api/v1/auth/me`

```json
{ "user": { "...": "та же карточка, что при входе" }, "client_id": "parlor-ios" }
```

### Обновление

`POST /api/v1/auth/refresh`

```json
{ "refresh_token": "..." }
```

Ответ — новая пара. Прежний access тоже перестаёт действовать.

### Выход

`POST /api/v1/auth/logout`

```json
{ "refresh_token": "..." }
```

Ответ: `{ "logged_out": true }`. Повторный выход с тем же токеном тоже успешен. После этого приложение удаляет оба токена.

### Чужое приложение

Чужое приложение не получает пароль. Человек подтверждает вход на сайте, приложение меняет одноразовый код на ту же пару токенов.

1. Зарегистрировать клиента строкой в `api_clients`: `kind = third_party`, `secret_hash` — SHA-256 секрета в hex, `redirect_uris` — точные адреса возврата, например `https://app.example/callback`.
2. Открыть в браузере:

```text
GET /oauth/authorize?client_id=sample-app&redirect_uri=https%3A%2F%2Fapp.example%2Fcallback&state=xyz
```

`redirect_uri` должен совпасть с одним из сохранённых адресов. `state` — произвольная строка приложения, сервер вернёт её как есть. Если человек ещё не вошёл, сайт откроет страницу входа и вернёт его к подтверждению.

3. После согласия браузер переходит на:

```text
https://app.example/callback?code=...&state=xyz
```

Отказ: `?error=access_denied&state=xyz`. Код живёт 60 секунд и принимается один раз.

4. `POST /api/v1/auth/token`

```json
{
  "grant_type": "authorization_code",
  "code": "...",
  "client_id": "sample-app",
  "client_secret": "секрет клиента",
  "redirect_uri": "https://app.example/callback"
}
```

Дальше те же access, refresh, выход и те же права, что у этого человека на сайте.

## Аккаунт

Эти методы доступны и до того, как указано имя.

`GET /api/v1/account` — карточка, части имени, дата рождения, настройки, ссылка приглашения.

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

`PATCH /api/v1/account` меняет только переданные поля.

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

Новая дата рождения без `"confirm": true` получает 422. Пустые день, месяц и год дату не стирают. Ответ — свежий аккаунт.

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

`default_game`: `chess`, `checkers`, `go`, `domino`, `uno`, `poker`, `durak`, `blackjack`, `preferans`. Покер, блэкджек и преферанс в качестве игры по умолчанию сохраняются только с 18 лет, иначе сервер оставляет шахматы. Ответ: `{ "saved": true, "settings": {} }`.

`POST /api/v1/account/password`

```json
{
  "current_password": "старый",
  "new_password": "новый-пароль-1",
  "repeat_password": "новый-пароль-1"
}
```

Правила пароля те же, что на сайте. Ответ: `{ "saved": true }`.

`POST /api/v1/account/avatar` — `multipart/form-data`, поле `file`. JPEG, PNG или WebP до 10 МБ. Приложение само обрезает портрет и уменьшает его до 512×512 перед отправкой: сервер хранит присланные байты. Ответ: `{ "src": "/avatars/<файл>" }`.

`DELETE /api/v1/account/avatar` — `{ "src": "" }`.

Портрет читается так: `GET /avatars/<файл>` с тем же Bearer. Без входа сервер портрет не отдаёт.

`GET /api/v1/account/chips?page=1` — начисления фишек. Страница по 50 записей.

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

`kind` бывает `game` (партия), `referral` (друг пришёл по ссылке) или `grant` (начисление администратора). Фишки игровые, это не деньги.

## Каталог и кабинет

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

`family` — `board` или `cards`. `adult: true` у покера, блэкджека и преферанса; до 18 лет этих игр в списке нет. `open: false` — игра выключена в настройках гостиной.

`GET /api/v1/home?page=1`

```json
{
  "greeting": "Добрый вечер, Иван",
  "chips": 500,
  "continue_id": "uuid или null",
  "continue_game": {},
  "recent": [],
  "page": 1,
  "pages": 1,
  "total": 0
}
```

`continue_game` и элементы `recent`: `id`, `game_type`, `mode`, `player_side`, `status`, `result`, `updated_at`, `user_id`, `opponent_id`, `join_code`, `creator_name`, `opponent_name`, `creator_login`, `opponent_login`. `continue_id` — партия, которую можно открыть кнопкой «продолжить». Имена здесь уже показанные: фамилия и имя, если они заполнены, иначе логин. Ссылки на профиль строятся из `creator_login` и `opponent_login`.

## Друзья

`GET /api/v1/friends`

```json
{
  "friends": [
    {
      "id": "uuid дружбы",
      "other_id": "uuid человека",
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

`relation`: `accepted`, `incoming`, `outgoing`. `incoming` дублирует входящие заявки. `games` — тот же каталог, чтобы предложить игру другу.

`POST /api/v1/friends` — `{ "username": "player" }`. Ответ `201`: `{ "id": "uuid", "username": "player" }`. Повтор — `409 already_friends`.

`POST /api/v1/friends/{id}/accept` — `{ "accepted": true }`. Принять может только адресат заявки.

`POST /api/v1/friends/{id}/decline` — `{ "removed": true }`. Удаляет и заявку, и уже принятую дружбу, если это делает один из двоих.

`POST /api/v1/friends/{id}/challenge` — `{ "game_type": "chess" }`. Дружба должна быть принята. Сервер создаёт стол и пишет другу сообщение с кодом. Ответ: `{ "game_id": "uuid", "join_code": "ab12cd34" }`.

`POST /api/v1/players/{username}/friend` делает то же, что заявка в друзья.

## Гостиная

`GET /api/v1/lobby` — кто ищет стол последние 15 минут и кто был в сети последние 2 минуты.

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

До 18 лет взрослые игры из `seekers` скрыты.

`POST /api/v1/lobby/seek` — `{ "game_type": "uno", "seats": 4 }`. Для шахмат, шашек и го мест всегда 2. Уно, покер, дурак и блэкджек — от 2 до 6. Преферанс — 3. Домино — от 2 до 4. Ответ: `{ "seeking": true, "game_type": "uno", "seats": 4 }`. У человека одна заявка: новая заменяет старую.

`POST /api/v1/lobby/cancel` — `{ "seeking": false }`.

`POST /api/v1/lobby/accept/{user_id}` сажает за стол того, кто ищет. Ответ: `{ "game_id": "uuid" }`. Свою заявку принять нельзя.

## Беседы

`GET /api/v1/chats` — список диалогов.

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

`GET /api/v1/chats/{username}` помечает диалог прочитанным и добавляет `thread`:

```json
{
  "username": "player",
  "name": "Пётр",
  "avatar": "",
  "live": true,
  "label": "В сети",
  "friendship_id": "uuid или null",
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

Если в тексте есть приглашение за стол, `code` и `game_key` заполнены. Иначе они пустые. Приглашение принимается методом `POST /api/v1/games/join`.

`POST /api/v1/chats/{username}` — `{ "body": "Текст" }`. От 1 до 1000 символов после сжатия пробелов. Ответ — тот же диалог, что у GET.

`GET /api/v1/notices` — до шести свежих личных сообщений и заявок в друзья плюс счётчики.

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

`kind: "request"` ведёт к друзьям. Отдельных push-уведомлений пока нет: приложение само опрашивает этот метод.

## Живые столы

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

`POST /api/v1/live/{id}/watch` и `POST /api/v1/live/{id}/sit` отвечают `{ "game_id": "uuid" }`. Тело не нужно. Если игра с 18 лет и даты нет или человеку меньше 18, ответ `403 adult_only`.

Войти по коду: `POST /api/v1/games/join` с `{ "code": "ab12cd34" }`. Смотреть по коду: `POST /api/v1/games/watch` с тем же телом. Оба ответа — состояние партии.

## Новости

Без входа.

`GET /api/v1/news?page=1` — по 6 записей.

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
      "published_on": "2026-11-01"
    }
  ],
  "page": 1,
  "pages": 1,
  "total": 3
}
```

`body` — уже очищенный HTML. `GET /api/v1/news/{id}` отдаёт `{ "post": {} }`.

Если `cover` выглядит как `32hex.jpg`, `32hex.png` или `32hex.webp`, картинка лежит по `/news-images/{cover}` и доступна без входа. Иначе это имя готовой обложки сайта.

Правила, конфиденциальность и контакты остаются страницами сайта: `/rules`, `/privacy`, `/contact`.

## Профиль

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

`friend_state`: `self`, `none`, `outgoing`, `incoming`, `accepted`. `weeks` — восемь недель с понедельника, их достаточно для графика. В `stats` ещё есть `line` и `donut` с координатами, которыми сайт рисует свои SVG; приложению удобнее считать график из `weeks`, `games`, побед, поражений и ничьих.

`GET /api/v1/players?q=pet` — поиск для приглашения, до 8 человек: `{ "players": [{ "username", "name", "live" }] }`. Это не страница профиля.

`POST /api/v1/players/{username}/chips` — только администратор, `{ "amount": 100 }`. Иначе 404. Ответ: `{ "chips": 600 }`. Остальная админка остаётся на сайте.

## Партия

Состояние читается целиком:

`GET /api/v1/games/{id}`

Пока партия идёт, приложение повторяет этот запрос. Отдельного сокета для ходов нет. Сокет ниже нужен только для видео и голоса.

Создать стол: `POST /api/v1/games`

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

`player_side`: `white` или `black`. `audience`: `open` или `closed`. `engine_level` от 1 до 5, `engine_time_ms` от 100 до 10000.

Режимы:

| `mode` | Где | Что это |
| --- | --- | --- |
| `vs_computer` | Все игры | Вы против компьютера. У карт режим выбирается сам, если свободных мест нет |
| `online` | Все игры | Стол ждёт людей. Код в `join_code`, пока вы сидите за ним |
| `free` | Только шахматы и шашки | Обе стороны ваши, стол закрыт |
| `analysis` | Только шахматы и шашки | Разбор позиции, обе стороны ваши |
| `lesson` | Только шахматы и шашки | То же, удобно со своей стартовой записью |

Го принимает только `vs_computer` и `online`. Карты тоже: `free`, `analysis` и `lesson` для них — `422 bad_mode`. Если у карт заданы `computers` и `open_seats`, сервер сам ставит `online`, когда есть свободные места, и `vs_computer`, когда их нет.

Дополнительные поля:

| Поле | Правило |
| --- | --- |
| `board_size` | Го: `9`, `13` или `19`. Пустое значение — 19 |
| `durak_kind` | `podkidnoy` или `perevodnoy`. Пустое — подкидной |
| `pool` | Преферанс, пуля от 6 до 20 |
| `stake` | Преферанс, цена одного очка расписки: `1`, `2`, `5` или `10`. Пустое значение — 1. На стол садится стек в 100 таких очков: 100, 200, 500 или 1 000 фишек. Если на счёте меньше, ответ `409 no_chips`: в долг партия не идёт. Остальные фишки остаются на счёте. Остановка возвращает стек. Расписка закрывается с пулей и не забирает больше стека |
| `computers` | Компьютеры за карточным столом, от 0 до 5. В преферансе вместе со свободными местами ровно двое кроме вас. В блэкджеке вместе с ними не больше пяти. В уно, покере и дураке кроме вас от одного до пяти мест. В домино вместе со свободными местами от одного до трёх кроме вас |
| `open_seats` | Места для людей по коду или кнопке «Сесть». Те же пределы |
| `initial_fen` | Только шахматы, FEN |
| `pgn` | Только шахматы |
| `initial_position` | Только шашки, запись RCP |
| `moves` | Список строк. Шахматы — UCI, по ходу: `"e2e4"`. Шашки — `"22-18"` или взятие `"21:14:7"`. Для го и карт поле не используется |

`audience` имеет смысл у `online` и `vs_computer`. В остальных режимах стол закрытый. Открытый стол виден в `GET /live`, на него можно сесть и смотреть без кода. Закрытый стол открывается только кодом.

Ответ `201` — состояние партии. Для онлайн-стола в нём есть `join_code`, пока вы сидите за ним. Пока статус `waiting`, партия ещё не началась: передайте код или дождитесь, что кто-то сядет. У карт со свободными местами игра начинается, когда мест не осталось.

### Общие поля состояния

Они есть и у доски, и у карт.

| Поле | Смысл |
| --- | --- |
| `id`, `you` | Партия и UUID вашего пользователя |
| `game_type` | `chess`, `checkers`, `go`, `domino`, `uno`, `poker`, `durak`, `blackjack`, `preferans` |
| `table` | `board`, `cards` или `go` |
| `variant`, `mode`, `status` | Вид, режим и `waiting` / `active` / `finished`. У го во время подсчёта `status` равен `scoring` |
| `version` | Номер позиции. Его нужно возвращать в ходе |
| `your_side`, `side_to_move`, `your_turn` | Ваша сторона, чья очередь и можно ли ходить вам |
| `watching` | Вы смотрите, а не играете |
| `gallery` | В дураке место отдано компьютеру, и вы смотрите доигрывание. Пока `true`, следующий `engine-move` лучше просить с `steps: 1` |
| `legal_moves` | Ходы, которые сервер примет сейчас. На чужом ходе список пуст |
| `moves` | История: `ply`, `notation`, `algebraic`, `by` |
| `result`, `result_reason`, `result_message`, `result_tone` | Итог. `result`: `white_win`, `black_win`, `draw` или `{место}_win`. `result_message` — фраза для экрана. `result_tone`: `win`, `loss`, `draw`, `stop` или `null` |
| `status_line` | Строка, которую можно показать над столом |
| `summary` | Итог для окна статистики или `null`, пока партия не кончилась |
| `can_move`, `can_stop`, `can_undo`, `can_hint`, `can_engine` | Что можно нажать |
| `join_code`, `audience`, `waiting` | Код входа, открытость и ожидание соперника |
| `opponent_name`, `you_name`, `creator_name` | Имена за столом |
| `in_call`, `call_roster` | Можно ли звать в видео и кто уже за столом |
| `ice_servers` | Список ICE для `RTCPeerConnection`: STUN, а при настроенном TURN ещё TURN и TURNS |
| `live` | Пока `true`, стол стоит опрашивать |
| `rematch` | `available`, `state` (`idle`, `outgoing`, `incoming`, `accepted`, `declined`), `game_id`, `note` |
| `white_name`, `black_name`, `white_login`, `black_login`, `white_avatar`, `black_avatar` | Лица двух сторон, когда стол на белых и чёрных |
| `login`, `avatar`, `opponent_login`, `opponent_avatar` | Ваш портрет и соперник |
| `engine_level`, `engine_time_ms` | Сила и время компьютера |
| `computer_turn` | У карт: сейчас ходит компьютер. Тогда нужен `POST /engine-move` |
| `can_engine` | Сервер готов принять ход компьютера |

Пока `live` равен `true`, читайте `GET /games/{id}` примерно раз в полторы секунды и перерисовывайте стол, если изменились `version`, `status` или `rematch`. Чат стола можно читать отдельно, примерно раз в две секунды. Ходы по сокету не приходят.

Если `can_engine` и партия активна против компьютера, либо у карт `computer_turn`, вызовите `POST /games/{id}/engine-move` с текущим `version`. В теле можно передать `steps` от 1 до 40. В картах, когда `held` уже истина, подождите, пока игрок посмотрит стол, и только потом просите следующий ход: сервер на таком ответе останавливает серию. В го то же самое во время подсчёта, когда `can_engine`. После своего хода ответ `/moves` уже содержит ответ компьютера, если он успел; `engine_error` тогда говорит, что ответ не вышел и его нужно запросить отдельно.

`summary` появляется, когда партия кончилась или её остановили. `summary.line` — фраза окна итога. `summary.seats` — строки: `key`, `name`, `login`, `avatar`, `winner`. У доски ещё `pieces` и `kings`, у карт — `cards`, `count`, `action`. У покера в строке есть `payout`, `invested`, `stack`, `made`, `busted`. У уно — `said`. `summary.kind`: `board`, `uno`, `poker` или `parlor`.

Место игрока — строка `your_side` и `seats[].key`. За столом на двоих это `white` и `black`. Если при создании карт задано несколько компьютеров или свободных мест, места называются `p0`, `p1`, `p2`… Создатель сидит на `p0`. В преферансе на троих места тоже `p0`, `p1`, `p2`. В домино на троих и четверых — те же `p0`… За столом на двоих домино тоже сидит на `white` и `black`. Эти ключи совпадают в `stacks`, `committed`, `shown` и `summary.seats`.

### Шахматы и шашки

`table` равен `board`. Доска — 64 клетки в `cells`, по рядам снизу вверх, в ряду слева направо. У клетки: `square`, `file` (0 — линия a), `rank` (0 — первая горизонталь), `dark`, `piece`, `color`, `aria`, `number`.

Фигура — заглавная буква: `P` пешка, `N` конь, `B` слон, `R` ладья, `Q` ферзь, `K` король. В шашках `M` — простая, `K` — дамка. `color`: `white` или `black`, на пустой клетке оба поля `null`.

В шахматах `square` — клетка вроде `e4`, `number` пустой. В шашках игра идёт по тёмным полям: у них `number` от 1 до 32 и `square` равен этому номеру строкой. Светлые поля в ходах не участвуют.

`black_at_bottom` — рисовать чёрных снизу. `POST /orientation` переворачивает доску и возвращает новое состояние. `in_check` и `check_square` — шах и клетка короля. `last_move` — клетки последнего хода, их можно подсветить.

Элемент `legal_moves`: `{ "path": ["e2", "e4"], "promotion": null, "notation": "e4" }`. В шашках `path` — номера полей строками, например `["22", "18"]` или взятие из нескольких полей. Превращение есть только в шахматах: если в выбранном ходе `promotion` не `null`, отправьте эту букву (`q`, `r`, `b`, `n`) как есть. Приложение показывает `notation`, а на сервер возвращает `path` и `promotion` без переделки. Пока человек выбирает длинное взятие, подходят все ходы, у которых `path` начинается с уже выбранных клеток.

`can_undo` бывает только у доски. `can_hint` — у администратора в активной партии.

### Го

`table` равен `go`. Ходы идут через `POST /go`, список `legal_moves` пустой.

`size` — 9, 13 или 19. `board` — строка длины `size * size`, по рядам сверху вниз. Символ `0` — пусто, `1` — чёрный, `2` — белый. Индекс пересечения: `row * size + col`, оба с нуля, `col` вправо, `row` вниз. `komi` — строка форы, обычно `7,5`. `captures` — `{ "black", "white" }`. `rules` — идентификатор правил площади.

`legal` — список точек, куда можно поставить камень: `[[col, row], …]`. Пустой список значит, что ставить сейчас нельзя. `last` — последний камень `{ "kind": "move", "color", "col", "row" }` или пропуск `{ "kind": "pass", "color" }`. `notice` — фраза о пропуске.

`phase`: `play` во время партии и `score` на подсчёте. На подсчёте `status` равен `scoring`. `dead` — снятые группы, список пар `[col, row]`. `tally` на подсчёте: очки сторон, `komi` и `territory` — `[{ "col", "row", "owner" }]`, где `owner` это `black` или `white`.

Кнопки го смотрите по полям, а не по общему `can_move`:

| Поле | Команда |
| --- | --- |
| `your_turn` | `action: "move"` с `col` и `row` из `legal` |
| `can_pass` | `action: "pass"` |
| `can_resign` | `action: "resign"` |
| `can_mark` | `action: "mark"` — пометить мёртвую группу на `col`, `row` |
| `can_agree` | `action: "agree"` — согласиться со счётом |
| `can_resume` | `action: "resume"` — вернуться к игре |

`command_id` новый на каждое нажатие. Повтор той же команды не ставит второй камень. Для `pass`, `resign`, `agree` и `resume` координаты не нужны.

### Карты

`table` равен `cards`. Рука — `hand`, массив кодов. Чужие карты не приходят, пока их не вскрыли: чужой размер руки лежит в `seats[].count` и `opponent_count`.

Обычная карта — два символа. Первая буква достоинство: `2`–`9`, `T` десятка, `J`, `Q`, `K`, `A`. Вторая масть: `C` трефы, `D` бубны, `H` черви, `S` пики. Пример: `AH` — туз червей. Колоды короче в дураке (с шестёрки) и в преферансе (с семёрки).

Уно — другой код. Цвет `R`, `Y`, `G`, `B` и знак: цифра `0`–`9`, `S` пропуск, `D` «возьми две». `W` — дикая. Пример: `R7`, `YD`, `W`.

Ход — элемент `legal_moves` целиком. Покажите человеку `notation`, на сервер отправьте его `path` и `promotion` (у карт он `null`). Не собирайте `path` сами, кроме одного случая: ставка и повышение в покере.

| Игра | Как выглядит `path` |
| --- | --- |
| Уно | `["play", "R7"]`, дикая `["play", "W", "R"]`, взять `["draw", "1"]`, сказать уно `["uno"]`. Ход с объявлением уно заканчивается на `"uno"` |
| Покер | `["act", "check"]`, `["act", "call"]`, `["act", "fold"]`, обмен `["draw", "-"]` или `["draw", "AH,KD"]`. Если у элемента есть `min` и `max`, это ставка или повышение: к `path` добавьте выбранную сумму строкой, например `["act", "raise", "40"]`. Сумма от `min` до `max`. Без суммы сервер берёт `min`. `put` — уже поставленное этим местом |
| Дурак | Ход, отбой и подкидывание: `["play", "7H"]`. Забрать: `["act", "take"]`. Бито: `["act", "pass"]` |
| Блэкджек | Ставка `["bet", "10"]`, затем `["act", "hit"]`, `["act", "stand"]`, `["act", "double"]` |
| Преферанс | Торг `["bid", "pass"]`, `["bid", "miser"]` или заказ из `notation`. Вист `["whist", "yes"]` и `["whist", "no"]`. Сброс прикупа `["discard", "7C", "8D"]`. Ход во взятку `["play", "AH"]` |
| Домино | Кость к правому концу `["play", "6-1", "R"]`, к левому `["play", "6-1", "L"]`. Взять из базара `["draw", "1"]`. Пас, когда базар пуст, `["pass", "1"]`. Код кости — `старшая-младшая`, от `6-6` до `0-0`. На первом ходе в `legal_moves` остаётся только кость, которую правила велят положить |

Общие поля стола: `phase`, `pot`, `deck` (сколько карт в колоде), `board` (общие карты, взятка или карты дилера), `last_move`. `seats` — кто сидит: `key`, `name`, `login`, `avatar`, `kind` (`you`, `human`, `computer`, `open`), `count`, `you`, `turn`, `cpu`, `stack`, `bet`, `folded`, `busted`, `dealer`, `winner`, `mark`. В преферансе у места ещё есть `taken` — сколько взяток уже взято — и `order_need`: сколько заказано, только у объявившего во время розыгрыша, иначе `null`.

Дальше по играм:

| Поле | Где смотреть |
| --- | --- |
| `stacks`, `committed`, `button`, `shown`, `winner_hand` | Покер. `shown` — вскрытые руки по ключам мест. `phase`: `waiting`, `preflop`, `flop`, `turn`, `river`, `done` |
| `top`, `color`, `deck`, `said` | Уно. `top` — верх сброса, `color` — текущий цвет `R`/`Y`/`G`/`B`/`W`, `said` — кто сказал уно |
| `trump`, `trump_card`, `pairs`, `held` | Дурак. `trump` — масть козыря, `trump_card` — открытый козырь, пока он в колоде. `pairs` — пары `{ "attack", "defense" }` на столе. `held` — это уже битый стол, а не новая атака. Пока `held`, сайт держит карты около двух с половиной секунд и только потом просит следующий ход компьютера |
| `hole`, `board`, `stacks`, `committed` | Блэкджек. `board` — карты дилера. `hole: true` значит, вторая карта дилера ещё закрыта и в `board` её нет. Ставки в `committed` |
| `contract`, `contract_need`, `declarer`, `tricks`, `sheet`, `scored`, `note`, `talon`, `held` | Преферанс. `contract` — текущий заказ словами. `contract_need` — число взяток в заказе, у мизера `0`, у распасов `null`. `declarer` — место, которое заказало игру. `tricks` — сколько взяток уже у каждого места. `sheet`: `pool`, `closed`, `seats`, `bullet`, `mountain`, `whists`, `total`. `board` — карты взятки. `held` — это прошлая взятка, её тоже держат на столе перед следующим заходом |
| `chain`, `deck`, `hand` | Домино. `hand` — ваши кости, код `6-1`. Чужие кости не приходят, только `seats[].count`. `deck` — сколько костей в базаре. `chain` — линия слева направо: `tile`, `spin` (дубль стоит вертикально), `hi_left` (старшая половина смотрит влево). `phase`: `play` или `done`. Итог `empty` — рука кончилась, `blocked` — рыба, `left` — соперник вышел. `summary.kind` для домино — `parlor` |

`note` и `status_line` можно показать как подпись над столом. В `summary` у преферанса тоже есть `sheet`.

### Ход

`POST /api/v1/games/{id}/moves`

```json
{ "version": 3, "path": ["e2", "e4"], "promotion": null }
```

Ответ: `{ "state": {}, "engine_error": null }`. Если компьютер не смог ответить, `engine_error` — текст, а `state` уже с вашим ходом. При `409 stale_position` заново прочитайте партию и возьмите новый `version`.

Го не ходит через `/moves`. `POST /api/v1/games/{id}/go`

```json
{
  "command_id": "уникальная строка 8–80 символов",
  "version": 3,
  "action": "move",
  "col": 3,
  "row": 4
}
```

`action`: `move`, `pass`, `resign`, `mark`, `agree`, `resume`. Для `pass` координаты не нужны. `command_id` новый на каждое нажатие, повтор той же команды не ставит второй камень. Ответ — состояние.

Остальные действия за столом:

| Метод | Тело | Ответ |
| --- | --- | --- |
| `GET /games/{id}/legal-moves` | — | `{ "version", "moves" }` |
| `GET /games/{id}/history` | — | `{ "version", "moves" }` |
| `POST /games/{id}/undo` | `{ "version" }` | состояние |
| `POST /games/{id}/resign` | `{ "version" }` | состояние |
| `POST /games/{id}/step-aside` | `{ "version", "pace" }` | Только начатый дурак, где кроме вас двое или больше компьютеров и нет других людей и пустых мест. `pace`: `watch` отдаёт место компьютеру и возвращает состояние с `gallery: true`; `fast` доигрывает партию сразу. Иначе `409 stay` |
| `POST /games/{id}/stop` | `{ "version" }` | состояние. Остановить может создатель стола |
| `POST /games/{id}/engine-move` | `{ "version", "steps" }` | состояние, когда ход компьютера пора запросить. `steps` от 1 до 40, по умолчанию 40. В картах серия останавливается на `held`, чтобы клиент показал собранный стол |
| `POST /games/{id}/hint` | `{ "version" }` | Только администратор. `{ "version", "private": true, "engine", "nodes", "lines" }`. Строка разбора: `notation`, `path`, `promotion`, `score_white`, `mate`, `pv`, `depth`. В го подсказки нет |
| `POST /games/{id}/orientation` | пусто | Новое состояние с перевёрнутой доской |
| `POST /games/{id}/save` | пусто | `{ "saved": true, "updated_at" }`. Партия поднимается в «продолжить» |
| `GET /games/{id}/export` | — | Файл, не JSON. Шахматы — `text/plain`, `game.pgn`. Го — `application/x-go-sgf`, `game.sgf`. Шашки — `text/plain`, `checkers.txt`. Карты — текст ходов, `{игра}.txt` |
| `POST /games/{id}/rematch` | пусто | Против компьютера сразу `{ "game_id", "rematch" }`. С человеком — предложение, а когда оба согласны, там же `game_id` новой партии |
| `POST /games/{id}/rematch/decline` | пусто | `{ "game_id": null, "rematch" }` |
| `POST /games/{id}/invite` | `{ "username" }` | `{ "sent": "player" }`. Пишет в личную беседу код стола. Не чаще 20 раз в минуту. Стол должен ждать игрока, приглашает тот, кто за ним сидит |

Реванш есть после победы или поражения в партии с человеком или компьютером. У ничьей и остановленной доски его нет. У карт он есть и после остановки, пока стол не закрыт по фишкам: тогда `note` объясняет, что фишки кончились. Когда `rematch.state` равен `accepted`, откройте `rematch.game_id`.

Чат стола, не личная беседа:

`GET /api/v1/games/{id}/chat` — до 80 реплик: `{ "messages": [{ "body", "username", "login", "avatar", "at" }] }`. Здесь `username` — показанное имя, `login` — логин учётки. Писать может игрок и наблюдатель открытого стола. Не чаще 30 реплик в минуту.

`POST /api/v1/games/{id}/chat` — `{ "body": "Текст" }`, ответ `{ "saved": true }`.

Тема только экрана, без остальных настроек: `POST /api/v1/settings/theme` с `{ "theme": "dark" }` отвечает `{ "theme": "dark" }`. Полные настройки — `PUT /api/v1/account/settings`. Старый `POST /api/v1/settings` принимает то же тело, что и `PUT /api/v1/account/settings`, и отвечает `{ "saved": true }`.

## Видео и голос

Сокет не передаёт ходы. Он только знакомит игроков, которые уже сидят за одним онлайн-столом. Потоки идут между телефонами. Список ICE лежит в поле `ice_servers` состояния партии. На публичной гостиной там STUN, TURN и TURNS. Если Valkey доступен, сигнал доходит до игрока и на другом поде сайта.

```text
GET /ws/tables/{game_id}
Authorization: Bearer <access_token>
```

Приложение с токеном не обязано присылать заголовок `Origin`. Сайт по-прежнему пускает сюда только свою куку и только со своего адреса.

Сервер присылает:

| `type` | Смысл |
| --- | --- |
| `peers` | `{ "ids": ["uuid", ...] }` — кто уже в комнате |
| `peer-joined` | `{ "id": "uuid" }` |
| `peer-left` | `{ "id": "uuid" }` |
| `signal` | `{ "from": "uuid", "data": {} }` — чужое WebRTC-сообщение |
| `full` | в комнате уже шестеро, затем сокет закроется |

Приложение посылает сигнал конкретному человеку:

```json
{ "type": "signal", "to": "uuid собеседника", "data": { "sdp": "..." } }
```

`data` — ваш WebRTC payload, сервер его не разбирает. Сообщение не длиннее 8192 символов. Наблюдатель получает закрытие `1000` и `{ "type": "watch" }`: смотреть партию можно, говорить за столом — нет.

Коды закрытия: `4401` нет входа, `4403` чужой сайт или обслуживание, `4404` партии нет, `4408` комната полна.

## Что собирать первым

1. Узнать `GET /auth/register`. Если `open`, решить проверку, вызвать `POST /auth/register` и сохранить токены. Если имя не указано, сразу `PATCH /account`.
2. Иначе вход `parlor-ios` или `parlor-android`, сохранение refresh, тихий обмен по 401.
3. Кабинет `GET /home`, каталог, создание партии и чтение `GET /games/{id}`.
4. Ход из `legal_moves` через `POST /moves`. В го — `POST /go`. Если `can_engine`, запросите ход компьютера.
5. Друзья, гостиная, беседы, живые столы, чат стола и профиль.
6. Портрет, настройки, фишки, новости.
7. Видео — отдельно, когда стол уже играется.

Правила, конфиденциальность и контакты остаются страницами сайта: `/rules`, `/privacy`, `/contact`. Админский обзор тоже остаётся на сайте. Уведомления на телефон пока не отправляются.
